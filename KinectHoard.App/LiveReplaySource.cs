using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Web.Script.Serialization;
using KinectHoard.Core;

namespace KinectHoard.App
{
    // Per-frame cost of the live pipeline while recording, against the
    // sensor's 30 fps budget.
    internal sealed class FrameTiming
    {
        internal const double BudgetMs = 1000.0 / 30;
        private readonly List<float> process = new List<float>(), track = new List<float>(), mask = new List<float>(), fusion = new List<float>(), render = new List<float>();

        internal void Add(double processMs, double trackMs, double maskMs = 0, double fusionMs = 0, double renderMs = 0)
        {
            lock (process) { process.Add((float)processMs); track.Add((float)trackMs); mask.Add((float)maskMs); fusion.Add((float)fusionMs); render.Add((float)renderMs); }
        }

        private static double Median(List<float> values) { var v = values.ToArray(); Array.Sort(v); return v.Length == 0 ? 0 : Math.Round(v[v.Length / 2], 2); }

        private static double Quantile(float[] sorted, double q) { return Math.Round(sorted[Math.Min(sorted.Length - 1, (int)(q * sorted.Length))], 2); }

        internal Dictionary<string, object> Summary()
        {
            float[] p, t; double maskMedian, fusionMedian, renderMedian;
            lock (process) { p = process.ToArray(); t = track.ToArray(); maskMedian = Median(mask); fusionMedian = Median(fusion); renderMedian = Median(render); }
            if (p.Length == 0) return null;
            int within = p.Count(v => v <= BudgetMs);
            Array.Sort(p); Array.Sort(t);
            return new Dictionary<string, object> {
                { "frames", p.Length }, { "budget_ms", Math.Round(BudgetMs, 1) },
                { "process_ms_median", Quantile(p, .5) }, { "process_ms_p95", Quantile(p, .95) }, { "process_ms_max", Math.Round(p[p.Length - 1], 2) },
                { "track_ms_median", Quantile(t, .5) }, { "track_ms_p95", Quantile(t, .95) }, { "track_ms_max", Math.Round(t[t.Length - 1], 2) },
                { "within_budget", Math.Round((double)within / p.Length, 4) },
                { "mask_ms_median", maskMedian }, { "fusion_ms_median", fusionMedian }, { "render_ms_median", renderMedian } };
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
                { "late_ms_max", Math.Round(LateMs, 1) } };
        }

        internal int[] Mask(CameraFrame frame) { int[] mask; masks.TryGetValue(frame.TimestampUtc.Ticks, out mask); return mask; }

        // Returns the last frame delivered, after queueing "finish" on it.
        internal CameraFrame Run(FusionScanner scanner, Func<bool> stop)
        {
            scanner.Command("start");
            CameraFrame last = null;
            var clock = Stopwatch.StartNew();
            long first = long.MinValue;
            using (var reader = new SessionReader(Session))
            {
                CameraFrame current;
                bool have = reader.TryRead(out current);
                while (have && !stop())
                {
                    if (first == long.MinValue) first = current.TimestampUtc.Ticks;
                    double due = Speed <= 0 ? 0 : (current.TimestampUtc.Ticks - first) / 1e4 / Speed;
                    while (Speed > 0 && clock.Elapsed.TotalMilliseconds < due && !stop())
                        Thread.Sleep((int)Math.Max(1, Math.Min(15, due - clock.Elapsed.TotalMilliseconds)));
                    CameraFrame next;
                    bool haveNext = reader.TryRead(out next);
                    double now = clock.Elapsed.TotalMilliseconds;
                    if (haveNext && Speed > 0 && (next.TimestampUtc.Ticks - first) / 1e4 / Speed <= now)
                    { Dropped++; current = next; continue; }
                    if (Speed > 0) LateMs = Math.Max(LateMs, now - due);
                    scanner.Process(current, Calibration, Mask(current));
                    Delivered++; last = current;
                    have = haveNext; current = next;
                }
            }
            Done = true;
            if (last != null && !stop()) { scanner.Command("finish"); scanner.Process(last, Calibration, Mask(last)); }
            return last;
        }
    }
}
