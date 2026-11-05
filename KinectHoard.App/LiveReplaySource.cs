using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Web.Script.Serialization;
using KinectHoard.Core;

namespace KinectHoard.App
{
    // Per-frame cost of the live pipeline while recording, against the
    // sensor's 30 fps budget. Only frames that reach tracking are timed:
    // a frame without the subject costs the mask alone and would make the
    // share within budget look better than the tracking really is.
    internal sealed class FrameTiming
    {
        internal const double BudgetMs = 1000.0 / 30;
        private readonly List<float> process = new List<float>(), track = new List<float>(), mask = new List<float>(), fusion = new List<float>(), render = new List<float>(), rebuild = new List<float>();
        private int idle;

        // KINECT_HOARD_FRAME_LOG=file writes every timed frame's components (benchmarks).
        private static readonly TextWriter Log = string.IsNullOrEmpty(Environment.GetEnvironmentVariable("KINECT_HOARD_FRAME_LOG")) ? null
            : TextWriter.Synchronized(new StreamWriter(Environment.GetEnvironmentVariable("KINECT_HOARD_FRAME_LOG")) { AutoFlush = true });

        internal void Add(double processMs, double trackMs, double maskMs = 0, double fusionMs = 0, double renderMs = 0, double rebuildMs = 0)
        {
            lock (process) { process.Add((float)processMs); track.Add((float)trackMs); mask.Add((float)maskMs); fusion.Add((float)fusionMs); render.Add((float)renderMs); rebuild.Add((float)rebuildMs); }
            if (Log != null)
                Log.WriteLine(string.Format(System.Globalization.CultureInfo.InvariantCulture, "{0:0.00},{1:0.00},{2:0.00},{3:0.00},{4:0.00},{5:0.00},{6}",
                    processMs, trackMs, maskMs, fusionMs, renderMs, rebuildMs, GC.CollectionCount(2)));
        }

        // A recording frame that did not reach tracking (subject absent or too small).
        internal void AddIdle() { lock (process) idle++; }

        private static float[] Sorted(List<float> values) { var v = values.ToArray(); Array.Sort(v); return v; }

        private static double Quantile(float[] sorted, double q) { return sorted.Length == 0 ? 0 : Math.Round(sorted[Math.Min(sorted.Length - 1, (int)(q * sorted.Length))], 2); }

        internal Dictionary<string, object> Summary()
        {
            float[] p, t, m, f, r, b; int idleFrames;
            lock (process) { p = Sorted(process); t = Sorted(track); m = Sorted(mask); f = Sorted(fusion); r = Sorted(render); b = Sorted(rebuild); idleFrames = idle; }
            if (p.Length == 0) return idleFrames == 0 ? null : new Dictionary<string, object> { { "frames", 0 }, { "idle_frames", idleFrames }, { "budget_ms", Math.Round(BudgetMs, 1) } };
            int within = p.Count(v => v <= BudgetMs);
            return new Dictionary<string, object> {
                { "frames", p.Length }, { "idle_frames", idleFrames }, { "budget_ms", Math.Round(BudgetMs, 1) },
                { "process_ms_median", Quantile(p, .5) }, { "process_ms_p95", Quantile(p, .95) }, { "process_ms_p99", Quantile(p, .99) }, { "process_ms_max", Math.Round(p[p.Length - 1], 2) },
                { "track_ms_median", Quantile(t, .5) }, { "track_ms_p95", Quantile(t, .95) }, { "track_ms_max", Math.Round(t[t.Length - 1], 2) },
                { "within_budget", Math.Round((double)within / p.Length, 4) },
                { "frames_over_50ms", p.Count(v => v > 50) },
                { "mask_ms_median", Quantile(m, .5) }, { "mask_ms_p95", Quantile(m, .95) },
                { "fusion_ms_median", Quantile(f, .5) }, { "fusion_ms_p95", Quantile(f, .95) },
                { "render_ms_median", Quantile(r, .5) }, { "render_ms_p95", Quantile(r, .95) },
                { "rebuild_ms_p95", Quantile(b, .95) }, { "rebuild_ms_max", Math.Round(b[b.Length - 1], 2) } };
        }
    }

    // Feeds a recorded ColorDepth session through FusionScanner.Process at
    // the pace of its own timestamps, as the sensor would: when processing
    // falls behind, frames that a newer one has already replaced are dropped.
    // Archived foreground masks stand in for the body index of the live take.
    internal sealed class ReplaySource
    {
        internal readonly string Session, Source, Model, Mode, Target;
        internal readonly double Speed;
        internal readonly DepthIntrinsics Calibration;
        internal readonly bool Mirrored;
        internal readonly int Expected;
        private readonly Dictionary<long, int[]> masks = new Dictionary<long, int[]>();
        internal int Delivered, Dropped;
        internal bool Done;
        internal double LateMs;

        internal ReplaySource(string session, double speed)
        {
            Session = Path.GetFullPath(session); Speed = speed;
            Source = Path.GetDirectoryName(Session);
            var metadata = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(Path.ChangeExtension(Session, ".intrinsics.json")));
            var data = (Dictionary<string, object>)metadata["intrinsics"];
            Calibration = new DepthIntrinsics { Width = Convert.ToInt32(data["width"]), Height = Convert.ToInt32(data["height"]),
                Fx = Convert.ToSingle(data["fx"]), Fy = Convert.ToSingle(data["fy"]), Cx = Convert.ToSingle(data["cx"]), Cy = Convert.ToSingle(data["cy"]), Method = (string)data["method"] };
            string journalPath = Path.Combine(Source, "live.scan.json");
            Dictionary<string, object> journal = null;
            if (File.Exists(journalPath))
            {
                journal = new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Deserialize<Dictionary<string, object>>(File.ReadAllText(journalPath));
                foreach (Dictionary<string, object> entry in (System.Collections.IEnumerable)journal["poses"])
                {
                    Expected++;
                    if (entry.ContainsKey("foreground_runs"))
                        masks[Convert.ToInt64(entry["timestamp_ticks_utc"])] = ((System.Collections.IEnumerable)entry["foreground_runs"]).Cast<object>().Select(Convert.ToInt32).ToArray();
                }
            }
            Func<string, string, string> field = (name, fallback) => journal != null && journal.ContainsKey(name) && journal[name] is string ? (string)journal[name] : fallback;
            Model = field("model", "one"); Mode = field("mode", "fixed"); Target = field("target", "object");
            Mirrored = metadata.ContainsKey("image_orientation") ? (string)metadata["image_orientation"] == "mirrored_x" : Model == "one";
        }

        internal Dictionary<string, object> Status()
        {
            return new Dictionary<string, object> {
                { "source", Path.GetFileName(Source) }, { "source_directory", Source }, { "speed", Speed },
                { "frames", Expected }, { "delivered", Delivered }, { "dropped", Dropped }, { "done", Done },
                { "late_ms_median", LateQuantile(.5) }, { "late_ms_p95", LateQuantile(.95) },
                { "late_ms_max", Math.Round(LateMs, 1) } };
        }

        private readonly List<float> late = new List<float>();

        // How long after its timestamp each delivered frame reached the scanner.
        private double LateQuantile(double q)
        {
            float[] v; lock (late) v = late.ToArray();
            if (v.Length == 0) return 0;
            Array.Sort(v);
            return Math.Round(v[Math.Min(v.Length - 1, (int)(q * v.Length))], 1);
        }

        [System.Runtime.InteropServices.DllImport("winmm.dll", EntryPoint = "timeBeginPeriod")]
        private static extern uint TimeBeginPeriod(uint milliseconds);
        [System.Runtime.InteropServices.DllImport("winmm.dll", EntryPoint = "timeEndPeriod")]
        private static extern uint TimeEndPeriod(uint milliseconds);

        internal int[] Mask(CameraFrame frame) { int[] mask; masks.TryGetValue(frame.TimestampUtc.Ticks, out mask); return mask; }

        // Returns the last frame delivered, after queueing "finish" on it.
        internal CameraFrame Run(FusionScanner scanner, Func<bool> stop)
        {
            scanner.Command("start");
            CameraFrame last = null;
            bool period = Speed > 0 && TimeBeginPeriod(1) == 0;
            var clock = Stopwatch.StartNew();
            long first = long.MinValue;
            // Frames are decoded ahead on another thread, as a sensor delivers
            // them: decoding the next frame of a gzip session costs several
            // milliseconds that the live engine never pays, and on this thread
            // it made a 30 fps replay drop two frames out of three.
            var cancel = new CancellationTokenSource();
            var queue = new BlockingCollection<CameraFrame>(6);
            var producer = Task.Run(() =>
            {
                try
                {
                    using (var reader = new SessionReader(Session))
                    {
                        CameraFrame frame;
                        while (!cancel.IsCancellationRequested && reader.TryRead(out frame)) queue.Add(frame, cancel.Token);
                    }
                }
                catch (OperationCanceledException) { }
                finally { queue.CompleteAdding(); }
            });
            try
            {
            {
                CameraFrame current;
                bool have = queue.TryTake(out current, Timeout.Infinite);
                while (have && !stop())
                {
                    if (first == long.MinValue) first = current.TimestampUtc.Ticks;
                    double due = Speed <= 0 ? 0 : (current.TimestampUtc.Ticks - first) / 1e4 / Speed;
                    // With the default 15.6 ms Windows timer Sleep(1) would hand
                    // frames over late and count the delay as dropped frames; the
                    // 1 ms period is requested for the replay, the last
                    // millisecond is yielded.
                    while (Speed > 0 && clock.Elapsed.TotalMilliseconds < due && !stop())
                    {
                        double wait = due - clock.Elapsed.TotalMilliseconds;
                        if (wait > 2) Thread.Sleep((int)Math.Min(15, wait - 1.5));
                        else Thread.Yield();
                    }
                    CameraFrame next;
                    bool haveNext = queue.TryTake(out next, Timeout.Infinite);
                    double now = clock.Elapsed.TotalMilliseconds;
                    if (haveNext && Speed > 0 && (next.TimestampUtc.Ticks - first) / 1e4 / Speed <= now)
                    { Dropped++; current = next; continue; }
                    if (Speed > 0) { LateMs = Math.Max(LateMs, now - due); lock (late) late.Add((float)(now - due)); }
                    scanner.Process(current, Calibration, Mask(current));
                    Delivered++; last = current;
                    have = haveNext; current = next;
                }
            }
            }
            finally
            {
                if (period) TimeEndPeriod(1);
                cancel.Cancel();
                // A decoding error surfaces here instead of ending the replay silently.
                try { producer.GetAwaiter().GetResult(); } finally { queue.Dispose(); cancel.Dispose(); }
            }
            Done = true;
            if (last != null && !stop()) { scanner.Command("finish"); scanner.Process(last, Calibration, Mask(last)); }
            return last;
        }
    }
}
