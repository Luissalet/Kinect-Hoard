using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Numerics;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using KinectHoard.Core;
using Microsoft.Kinect.Fusion;
using FusionMatrix = Microsoft.Kinect.Fusion.Matrix4;
using NumericMatrix = System.Numerics.Matrix4x4;
using NumericVector = System.Numerics.Vector3;

namespace KinectHoard.App
{
    // All Fusion calls and camera buffers belong to the capture worker. The UI
    // only posts commands and reads immutable snapshots.
    internal sealed class FusionScanner : IDisposable
    {
        internal readonly string Model, Mode, Target, DirectoryPath;
        private readonly bool inputMirrored;
        private readonly ReconstructionProcessor processor;
        private readonly object gate = new object();
        private readonly ConcurrentQueue<Tuple<string, double, double>> commands = new ConcurrentQueue<Tuple<string, double, double>>();
        private readonly BlockingCollection<Tuple<CameraFrame, double[][], int[]>> archive = new BlockingCollection<Tuple<CameraFrame, double[][], int[]>>(4);
        private readonly List<object> poses = new List<object>();
        private readonly Task archiveTask;
        private ColorReconstruction volume;
        private readonly RgbdFeatureTracker features = new RgbdFeatureTracker();
        private CameraPoseFinder finder;
        private FusionFloatImageFrame depth, smooth;
        private FusionColorImageFrame color, rendered;
        private FusionPointCloudImageFrame points;
        private FusionMatrix pose = FusionMatrix.Identity;
        private FusionMatrix recoveryPose = FusionMatrix.Identity;
        private DepthIntrinsics intrinsics;
        private bool recording, initialized, finished, lost, orbit;
        private int integrated, rejected, recoveries, confirmations, foreground;
        private ulong bodyId;
        private float energy, seedU = .5f, seedV = .5f, yaw, pitch;
        private NumericVector center;
        private DateTime nextArchive, nextRender;
        private byte[] previewPng, surfacePng;
        private string state = "connecting", detail = "Abriendo cámara...", error;
        private Task finishTask;
        private double fps;
        private DateTime fpsSince = DateTime.UtcNow;
        private int fpsCount;

        internal FusionScanner(string model, string mode, string target, string directory, bool cpu = false, bool? mirrored = null)
        {
            if (model != "one" && model != "360") throw new ArgumentException("Cámara desconocida.");
            if (mode != "moving" && mode != "fixed") throw new ArgumentException("Modo desconocido.");
            if (target != "person" && target != "object") throw new ArgumentException("Sujeto desconocido.");
            Model = model; Mode = mode; Target = target; DirectoryPath = directory;
            inputMirrored = mirrored ?? model == "one";
            processor = cpu ? ReconstructionProcessor.Cpu : ReconstructionProcessor.Amp;
            Directory.CreateDirectory(directory);
            archiveTask = Task.Run(() =>
            {
                using (var writer = new SessionWriter(Path.Combine(directory, "session.khr"), StreamKind.ColorDepth, true))
                    foreach (var item in archive.GetConsumingEnumerable())
                    {
                        writer.WriteFrame(item.Item1);
                        poses.Add(new { timestamp_ticks_utc = item.Item1.TimestampUtc.Ticks, camera_to_world = item.Item2, foreground_runs = item.Item3 });
                    }
            });
        }

        internal void Command(string action, double x = 0, double y = 0)
        {
            if (!new[] { "start", "pause", "finish", "select", "orbit", "follow" }.Contains(action))
                throw new ArgumentException("Acción desconocida.");
            commands.Enqueue(Tuple.Create(action, x, y));
        }

        internal object Status()
        {
            lock (gate) return new {
                format = "KINECT_HOARD_LIVE_SCAN_1", model = Model, mode = Mode, target = Target,
                state, detail, error, frames_integrated = integrated, frames_rejected = rejected,
                tracking_recoveries = recoveries, foreground_pixels = foreground, tracking_energy = energy,
                fps, rgbd_inliers = features.Matches, rgbd_error_metres = double.IsInfinity(features.ErrorMetres) ? (double?)null : features.ErrorMetres,
                directory = DirectoryPath, mesh = Path.Combine(DirectoryPath, "scan.ply"),
                obj = Path.Combine(DirectoryPath, "scan.obj"), nonrigid_correction = false
            };
        }

        internal byte[] Preview(bool surface) { lock (gate) return surface ? surfacePng : previewPng; }
        internal void SetError(string message) { lock (gate) { error = message; detail = message; state = "error"; } }

        internal void Process(CameraFrame raw, DepthIntrinsics calibration, int[] foregroundRuns = null)
        {
            if (raw.Values == null || calibration == null) return;
            var frame = CanonicalFrame(raw, inputMirrored);
            if (state == "connecting" || (state == "error" && !finished))
            { state = recording ? "scanning" : "ready"; error = null; detail = "Cámara lista. Colócate en la imagen y pulsa Iniciar."; }
            if (intrinsics == null)
            {
                intrinsics = new DepthIntrinsics { Width = calibration.Width, Height = calibration.Height,
                    Fx = calibration.Fx, Fy = calibration.Fy,
                    Cx = inputMirrored ? calibration.Width - 1 - calibration.Cx : calibration.Cx,
                    Cy = calibration.Cy, Method = calibration.Method };
                WriteJson(Path.Combine(DirectoryPath, "session.intrinsics.json"), new {
                    format = "KINECT_HOARD_RGBD_1", image_orientation = "camera", intrinsics = new {
                        width = intrinsics.Width, height = intrinsics.Height, fx = intrinsics.Fx,
                        fy = intrinsics.Fy, cx = intrinsics.Cx, cy = intrinsics.Cy, method = intrinsics.Method
                    }
                });
            }
            Tuple<string, double, double> command;
            while (commands.TryDequeue(out command))
            {
                if (command.Item1 == "select" && !recording && !initialized)
                { seedU = (float)Math.Max(0, Math.Min(.999, command.Item2)); seedV = (float)Math.Max(0, Math.Min(.999, command.Item3)); }
                if (command.Item1 == "start" && !finished) { recording = true; state = "scanning"; }
                if (command.Item1 == "pause") { recording = false; state = "paused"; detail = "En pausa. Puedes continuar desde una vista ya escaneada."; }
                if (command.Item1 == "finish" && !finished) Finish();
                if (command.Item1 == "orbit") { orbit = true; yaw += (float)command.Item2; pitch = Math.Max(-1.2f, Math.Min(1.2f, pitch + (float)command.Item3)); }
                if (command.Item1 == "follow") orbit = false;
            }
            ushort[] masked;
            if (foregroundRuns == null) masked = Mask(frame);
            else
            {
                masked = new ushort[frame.Values.Length];
                if (foregroundRuns.Length % 2 != 0) throw new InvalidDataException("Máscara incompleta.");
                for (int i = 0; i < foregroundRuns.Length; i += 2)
                {
                    if (foregroundRuns[i] < 0 || foregroundRuns[i+1] < 0 || (long)foregroundRuns[i] + foregroundRuns[i+1] > masked.Length) throw new InvalidDataException("Máscara fuera del fotograma.");
                    Array.Copy(frame.Values, foregroundRuns[i], masked, foregroundRuns[i], foregroundRuns[i+1]);
                }
            }
            foreground = masked.Count(value => value != 0);
            if (DateTime.UtcNow >= nextRender)
            {
                var preview = (byte[])frame.Bgra.Clone();
                if (foreground >= 1500)
                    for (int i = 0; i < masked.Length; i++) if (masked[i] == 0)
                        for (int c = 0; c < 3; c++) preview[i * 4 + c] = (byte)(preview[i * 4 + c] / 3);
                using (var bitmap = FrameImage.Create(new CameraFrame { Width = frame.Width, Height = frame.Height, Bgra = preview }))
                using (var stream = new MemoryStream())
                { bitmap.Save(stream, ImageFormat.Png); lock (gate) previewPng = stream.ToArray(); }
            }
            if (recording && !finished)
            {
                if (foreground < 1500)
                    detail = Target == "person" && Model == "one" ? "Esperando una persona visible en profundidad." : "Selecciona el sujeto en la imagen y comprueba su profundidad.";
                else
                {
                    EnsureVolume(frame, masked);
                    volume.DepthToDepthFloatFrame(masked, depth, .45f, 3.5f, false);
                    volume.SmoothDepthFloatFrame(depth, smooth, 1, .04f);
                    var pixels = new int[frame.Width * frame.Height];
                    Buffer.BlockCopy(frame.Bgra, 0, pixels, 0, frame.Bgra.Length);
                    for (int i = 0; i < pixels.Length; i++) if (masked[i] == 0) pixels[i] = 0;
                    color.CopyPixelDataFrom(pixels);
                    var view = features.Describe(frame, masked);
                    bool accepted = !initialized || Track(view);
                    if (accepted)
                    {
                        volume.IntegrateFrame(depth, color, 120, 60, pose);
                        initialized = true; integrated++;
                        features.Accept(view, pose);
                        state = "scanning";
                        detail = Mode == "moving" ? "Recorre el sujeto; la superficie se acumula en directo." : "Gira el sujeto; el fondo queda fuera del seguimiento.";
                        if (integrated == 1 || integrated % 12 == 0)
                        {
                            bool added, trimmed;
                            finder.ProcessFrame(smooth, color, pose, .12f, out added, out trimmed);
                        }
                        if (DateTime.UtcNow >= nextArchive && !archive.IsAddingCompleted)
                        {
                            var runs = new List<int>();
                            for (int i = 0; i < masked.Length; i++)
                            {
                                if (masked[i] == 0) continue;
                                int first = i; while (i + 1 < masked.Length && masked[i + 1] > 0) i++;
                                runs.Add(first); runs.Add(i - first + 1);
                            }
                            if (archive.TryAdd(Tuple.Create(CloneFrame(frame), CameraToWorld(pose), runs.ToArray())))
                                nextArchive = DateTime.UtcNow.AddMilliseconds(400);
                        }
                    }
                    else { view.Dispose(); rejected++; state = "tracking_lost"; detail = "Recuperando seguimiento. Vuelve hacia una zona ya vista; la malla se conserva."; }
                }
            }
            if (volume != null && initialized && DateTime.UtcNow >= nextRender)
            {
                volume.CalculatePointCloud(points, rendered, orbit ? OrbitPose() : pose);
                var pixels = new int[frame.Width * frame.Height];
                rendered.CopyPixelDataTo(pixels);
                var bytes = new byte[pixels.Length * 4]; Buffer.BlockCopy(pixels, 0, bytes, 0, bytes.Length);
                for (int i = 3; i < bytes.Length; i += 4) bytes[i] = 255;
                using (var bitmap = FrameImage.Create(new CameraFrame { Width = frame.Width, Height = frame.Height, Bgra = bytes }))
                using (var stream = new MemoryStream())
                { bitmap.Save(stream, ImageFormat.Png); lock (gate) surfacePng = stream.ToArray(); }
            }
            if (DateTime.UtcNow >= nextRender) nextRender = DateTime.UtcNow.AddMilliseconds(100);
            fpsCount++;
            double seconds = (DateTime.UtcNow - fpsSince).TotalSeconds;
            if (seconds >= 1) { fps = fpsCount / seconds; fpsCount = 0; fpsSince = DateTime.UtcNow; }
        }

        private void EnsureVolume(CameraFrame frame, ushort[] masked)
        {
            if (volume != null) return;
            var samples = masked.Where(z => z > 0).OrderBy(z => z).ToArray();
            float zCenter = samples[samples.Length / 2] / 1000f;
            double xTotal = 0, yTotal = 0; int count = 0;
            for (int i = 0; i < masked.Length; i += 4) if (masked[i] > 0)
            { xTotal += (i % frame.Width - intrinsics.Cx) * masked[i] / (1000 * intrinsics.Fx); yTotal += (i / frame.Width - intrinsics.Cy) * masked[i] / (1000 * intrinsics.Fy); count++; }
            center = new NumericVector((float)(xTotal / count), (float)(yTotal / count), zCenter);
            var camera = new CameraParameters(intrinsics.Fx / frame.Width, intrinsics.Fy / frame.Height,
                intrinsics.Cx / frame.Width, intrinsics.Cy / frame.Height);
            volume = ColorReconstruction.FusionCreateReconstruction(new ReconstructionParameters(256, 384, 384, 384), processor, processor == ReconstructionProcessor.Amp ? 0 : -1, pose);
            var transform = volume.GetCurrentWorldToVolumeTransform();
            transform.M41 = 192 - center.X * 256; transform.M42 = 192 - center.Y * 256;
            transform.M43 = 192 - center.Z * 256;
            volume.ResetReconstruction(pose, transform);
            depth = new FusionFloatImageFrame(frame.Width, frame.Height, camera);
            smooth = new FusionFloatImageFrame(frame.Width, frame.Height, camera);
            color = new FusionColorImageFrame(frame.Width, frame.Height, camera);
            rendered = new FusionColorImageFrame(frame.Width, frame.Height, camera);
            points = new FusionPointCloudImageFrame(frame.Width, frame.Height, camera);
            finder = CameraPoseFinder.FusionCreateCameraPoseFinder(new CameraPoseFinderParameters(500, 200, 3.5f));
        }

        private bool Track(RgbdFeatureTracker.View view)
        {
            var previous = pose;
            FusionMatrix guess;
            bool matched = features.Estimate(view, intrinsics, out guess);
            bool success = volume.AlignDepthFloatToReconstruction(smooth, 10, null, out energy, matched ? guess : previous);
            var candidate = volume.GetCurrentWorldToCameraTransform();
            if (matched)
            {
                // ICP may slide along a smooth surface even after a good RGBD
                // fit. Retain the pose verified by independent depth matches.
                candidate = guess;
                success = true;
            }
            bool local = Plausible(previous, candidate, .25f, .75f);
            bool verifiedRecovery = matched && features.Matches >= 16 && features.ErrorMetres <= .008;
            if ((!matched && (!success || !Finite(energy) || energy > .15f || energy <= 0)) || (!local && !verifiedRecovery))
            {
                success = false;
                if (finder.GetStoredPoseCount() > 0)
                    using (var matches = finder.FindCameraPose(smooth, color))
                        foreach (var recoveryGuess in matches.GetMatchPoses().Take(5))
                        {
                            if (!volume.AlignDepthFloatToReconstruction(smooth, 10, null, out energy, recoveryGuess) || energy <= 0 || energy > .15f || !Finite(energy)) continue;
                            candidate = volume.GetCurrentWorldToCameraTransform();
                            success = true; break;
                        }
            }
            if (!success) { lost = true; confirmations = 0; return false; }
            local = Plausible(previous, candidate, .25f, .75f);
            if (!local) lost = true;
            if (lost)
            {
                // Compare recovery candidates with one another, not with a
                // stale last pose. A genuine return after a large motion must
                // be recoverable without accepting the first proposed jump.
                confirmations = confirmations > 0 && Plausible(recoveryPose, candidate, .08f, .25f) ? confirmations + 1 : 1;
                recoveryPose = candidate;
                if (confirmations < 3) return false;
                lost = false; recoveries++;
            }
            pose = candidate;
            return true;
        }

        private ushort[] Mask(CameraFrame frame)
        {
            var result = new ushort[frame.Values.Length];
            if (Target == "person" && Model == "one")
            {
                var bodies = frame.Bodies ?? new TrackedBody[0];
                var body = bodies.FirstOrDefault(b => b.TrackingId == bodyId) ?? bodies.FirstOrDefault();
                if (body == null || frame.BodyIndices == null) return result;
                bodyId = body.TrackingId;
                for (int i = 0; i < result.Length; i++)
                    if (frame.BodyIndices[i] == body.BodyIndex && frame.Values[i] >= 500 && frame.Values[i] <= 3500) result[i] = frame.Values[i];
            }
            else
            {
                // Select a continuous foreground surface. Unlike a fixed image
                // crop, the seed follows its projected centroid as it moves.
                int sx = Math.Min(frame.Width - 1, (int)(seedU * frame.Width));
                int sy = Math.Min(frame.Height - 1, (int)(seedV * frame.Height));
                int seed = -1;
                for (int radius = 0; radius < 45 && seed < 0; radius += 3)
                    for (int y = Math.Max(0, sy - radius); y <= Math.Min(frame.Height - 1, sy + radius) && seed < 0; y += 3)
                        for (int x = Math.Max(0, sx - radius); x <= Math.Min(frame.Width - 1, sx + radius); x += 3)
                            if (frame.Values[y * frame.Width + x] >= 500 && frame.Values[y * frame.Width + x] <= 3000) { seed = y * frame.Width + x; break; }
                if (seed < 0) return result;
                var visited = new bool[result.Length]; var queue = new int[result.Length]; int head = 0, tail = 1;
                queue[0] = seed; visited[seed] = true;
                long sumX = 0, sumY = 0; int n = 0; ushort seedDepth = frame.Values[seed];
                while (head < tail)
                {
                    int i = queue[head++]; ushort z = frame.Values[i];
                    if (z < 500 || z > 3000 || Math.Abs(z - seedDepth) > 650) continue;
                    result[i] = z; sumX += i % frame.Width; sumY += i / frame.Width; n++;
                    for (int direction = 0; direction < 4; direction++)
                    {
                        int next = direction == 0 ? (i % frame.Width > 0 ? i - 1 : -1) :
                            direction == 1 ? (i % frame.Width < frame.Width - 1 ? i + 1 : -1) : direction == 2 ? i - frame.Width : i + frame.Width;
                        if (next >= 0 && next < result.Length && !visited[next])
                        { visited[next] = true; if (Math.Abs(frame.Values[next] - z) < 35) queue[tail++] = next; }
                    }
                }
                if (n > 0) { seedU = (float)sumX / n / frame.Width; seedV = (float)sumY / n / frame.Height; }
            }
            // Discontinuities are unreliable geometry, not surfaces to bridge.
            var source = (ushort[])result.Clone();
            for (int y = 1; y < frame.Height - 1; y++)
                for (int x = 1; x < frame.Width - 1; x++)
                {
                    int i = y * frame.Width + x; if (source[i] == 0) continue;
                    if (source[i - 1] == 0 || source[i + 1] == 0 || source[i - frame.Width] == 0 || source[i + frame.Width] == 0 ||
                        Math.Abs(source[i] - source[i - 1]) > 30 || Math.Abs(source[i] - source[i + 1]) > 30 ||
                        Math.Abs(source[i] - source[i - frame.Width]) > 30 || Math.Abs(source[i] - source[i + frame.Width]) > 30) result[i] = 0;
                }
            return result;
        }

        private void Finish()
        {
            if (integrated == 0) { detail = "Todavía no hay superficie capturada."; return; }
            recording = false; finished = true; state = "exporting"; detail = "Guardando malla y preparando textura...";
            using (var mesh = volume.CalculateMesh(1)) SaveMesh(Path.Combine(DirectoryPath, "scan.ply"), mesh);
            archive.CompleteAdding();
            finishTask = Task.Run(() =>
            {
                try
                {
                    archiveTask.GetAwaiter().GetResult();
                    WriteJson(Path.Combine(DirectoryPath, "live.scan.json"), new {
                        format = "KINECT_HOARD_LIVE_SCAN_1", model = Model, mode = Mode, target = Target,
                        coordinate_space = "X right, Y down, Z forward, metres", poses,
                        frames_integrated = integrated, frames_rejected = rejected, tracking_recoveries = recoveries,
                        nonrigid_correction = false
                    });
                    ScannerExport.Texture(DirectoryPath);
                    lock (gate) { state = "finished"; detail = "Malla y textura guardadas. Puedes abrir el OBJ o iniciar otra toma."; }
                }
                catch (Exception ex) { SetError("Exportación: " + ex.GetBaseException().Message); }
            });
        }

        internal static int Replay(string session, string model, string mode, string directory, bool cpu)
        {
            var metadata = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(Path.ChangeExtension(session, ".intrinsics.json")));
            var data = (Dictionary<string, object>)metadata["intrinsics"];
            var calibration = new DepthIntrinsics { Width = Convert.ToInt32(data["width"]), Height = Convert.ToInt32(data["height"]),
                Fx = Convert.ToSingle(data["fx"]), Fy = Convert.ToSingle(data["fy"]), Cx = Convert.ToSingle(data["cx"]), Cy = Convert.ToSingle(data["cy"]), Method = (string)data["method"] };
            bool mirrored = metadata.ContainsKey("image_orientation") ? (string)metadata["image_orientation"] == "mirrored_x" : model == "one";
            var masks = new Dictionary<long, int[]>();
            string journalPath = Path.Combine(Path.GetDirectoryName(session), "live.scan.json");
            if (File.Exists(journalPath))
            {
                var journal = new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Deserialize<Dictionary<string, object>>(File.ReadAllText(journalPath));
                foreach (Dictionary<string, object> entry in (System.Collections.IEnumerable)journal["poses"])
                    if (entry.ContainsKey("foreground_runs"))
                        masks[Convert.ToInt64(entry["timestamp_ticks_utc"])] = ((System.Collections.IEnumerable)entry["foreground_runs"]).Cast<object>().Select(Convert.ToInt32).ToArray();
            }
            var scanner = new FusionScanner(model, mode, "object", directory, cpu, mirrored);
            try
            {
                scanner.Command("start");
                CameraFrame last = null;
                using (var reader = new SessionReader(session))
                {
                    CameraFrame frame;
                    while (reader.TryRead(out frame)) { int[] mask; masks.TryGetValue(frame.TimestampUtc.Ticks, out mask); scanner.Process(frame, calibration, mask); last = frame; System.Threading.Thread.Sleep(40); }
                }
                if (last == null) throw new InvalidDataException("Sesión vacía.");
                int[] lastMask; masks.TryGetValue(last.TimestampUtc.Ticks, out lastMask);
                scanner.Command("finish"); scanner.Process(last, calibration, lastMask);
                if (scanner.finishTask != null) scanner.finishTask.GetAwaiter().GetResult();
                WriteJson(Path.Combine(directory, "replay-result.json"), scanner.Status());
                return scanner.integrated > 0 && scanner.state == "finished" ? 0 : 2;
            }
            finally { scanner.Dispose(); }
        }

        private FusionMatrix OrbitPose()
        {
            var position = center + new NumericVector((float)(1.5 * Math.Sin(yaw) * Math.Cos(pitch)), (float)(-1.5 * Math.Sin(pitch)), (float)(-1.5 * Math.Cos(yaw) * Math.Cos(pitch)));
            var forward = NumericVector.Normalize(center - position);
            var right = NumericVector.Normalize(NumericVector.Cross(NumericVector.UnitY, forward));
            var down = NumericVector.Cross(forward, right);
            return new FusionMatrix { M11 = right.X, M21 = right.Y, M31 = right.Z,
                M12 = down.X, M22 = down.Y, M32 = down.Z, M13 = forward.X, M23 = forward.Y, M33 = forward.Z,
                M41 = -NumericVector.Dot(position, right), M42 = -NumericVector.Dot(position, down), M43 = -NumericVector.Dot(position, forward), M44 = 1 };
        }

        private static bool Finite(float value) { return !float.IsNaN(value) && !float.IsInfinity(value); }
        private static bool Plausible(FusionMatrix a, FusionMatrix b, float metres, float radians)
        {
            NumericMatrix inverse; if (!NumericMatrix.Invert(ToNumeric(a), out inverse)) return false;
            var relative = inverse * ToNumeric(b);
            float angle = (float)Math.Acos(Math.Max(-1, Math.Min(1, (relative.M11 + relative.M22 + relative.M33 - 1) / 2)));
            return Finite(angle) && relative.Translation.Length() < metres && angle < radians;
        }
        private static NumericMatrix ToNumeric(FusionMatrix m) { return new NumericMatrix(m.M11,m.M12,m.M13,m.M14,m.M21,m.M22,m.M23,m.M24,m.M31,m.M32,m.M33,m.M34,m.M41,m.M42,m.M43,m.M44); }
        private static double[][] CameraToWorld(FusionMatrix m)
        {
            NumericMatrix p; if (!NumericMatrix.Invert(ToNumeric(m), out p)) throw new InvalidDataException("Pose no invertible.");
            return new[] { new double[] {p.M11,p.M21,p.M31,p.M41}, new double[] {p.M12,p.M22,p.M32,p.M42}, new double[] {p.M13,p.M23,p.M33,p.M43}, new double[] {p.M14,p.M24,p.M34,p.M44} };
        }

        internal static CameraFrame CanonicalFrame(CameraFrame input, bool flip)
        {
            var frame = CloneFrame(input, false);
            if (!flip) return frame;
            for (int y = 0; y < frame.Height; y++)
                for (int x = 0; x < frame.Width / 2; x++)
                {
                    int a = y * frame.Width + x, b = y * frame.Width + frame.Width - 1 - x;
                    ushort value = frame.Values[a]; frame.Values[a] = frame.Values[b]; frame.Values[b] = value;
                    for (int c = 0; c < 4; c++) { byte v = frame.Bgra[a * 4 + c]; frame.Bgra[a * 4 + c] = frame.Bgra[b * 4 + c]; frame.Bgra[b * 4 + c] = v; }
                    if (frame.BodyIndices != null) { byte v = frame.BodyIndices[a]; frame.BodyIndices[a] = frame.BodyIndices[b]; frame.BodyIndices[b] = v; }
                    if (frame.DepthToColorX != null) { float v = frame.DepthToColorX[a]; frame.DepthToColorX[a] = frame.DepthToColorX[b]; frame.DepthToColorX[b] = v; v = frame.DepthToColorY[a]; frame.DepthToColorY[a] = frame.DepthToColorY[b]; frame.DepthToColorY[b] = v; }
                }
            return frame;
        }
        private static CameraFrame CloneFrame(CameraFrame f, bool copyFullColor = true) { return new CameraFrame { Width=f.Width,Height=f.Height,Kind=f.Kind,TimestampUtc=f.TimestampUtc,Bgra=(byte[])f.Bgra.Clone(),Values=(ushort[])f.Values.Clone(),Bodies=f.Bodies,BodyIndices=f.BodyIndices == null ? null : (byte[])f.BodyIndices.Clone(),FullColorWidth=f.FullColorWidth,FullColorHeight=f.FullColorHeight,FullColorBgra=f.FullColorBgra == null ? null : copyFullColor ? (byte[])f.FullColorBgra.Clone() : f.FullColorBgra,DepthToColorX=f.DepthToColorX == null ? null : (float[])f.DepthToColorX.Clone(),DepthToColorY=f.DepthToColorY == null ? null : (float[])f.DepthToColorY.Clone() }; }
        private static void WriteJson(string path, object value) { File.WriteAllText(path, new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Serialize(value), new UTF8Encoding(false)); }
        private static void SaveMesh(string path, ColorMesh mesh)
        {
            var vertices = mesh.GetVertices(); var triangles = mesh.GetTriangleIndexes(); var colors = mesh.GetColors();
            using (var file = new FileStream(path, FileMode.Create))
            using (var writer = new BinaryWriter(file))
            {
                writer.Write(Encoding.ASCII.GetBytes("ply\nformat binary_little_endian 1.0\nelement vertex " + vertices.Count + "\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nelement face " + triangles.Count / 3 + "\nproperty list uchar int vertex_indices\nend_header\n"));
                for (int i = 0; i < vertices.Count; i++) { writer.Write(vertices[i].X); writer.Write(vertices[i].Y); writer.Write(vertices[i].Z); int c = colors[i]; writer.Write((byte)(c >> 16)); writer.Write((byte)(c >> 8)); writer.Write((byte)c); }
                for (int i = 0; i < triangles.Count; i += 3) { writer.Write((byte)3); writer.Write(triangles[i]); writer.Write(triangles[i+1]); writer.Write(triangles[i+2]); }
            }
        }

        public void Dispose()
        {
            recording = false;
            if (!archive.IsAddingCompleted) archive.CompleteAdding();
            archiveTask.GetAwaiter().GetResult();
            if (finishTask != null) finishTask.GetAwaiter().GetResult();
            else if (integrated > 0)
            {
                using (var mesh = volume.CalculateMesh(1)) SaveMesh(Path.Combine(DirectoryPath, "scan.ply"), mesh);
                WriteJson(Path.Combine(DirectoryPath, "live.scan.json"), new {
                    format = "KINECT_HOARD_LIVE_SCAN_1", model = Model, mode = Mode, target = Target,
                    poses, frames_integrated = integrated, interrupted = true, nonrigid_correction = false
                });
            }
            if (finder != null) finder.Dispose(); if (points != null) points.Dispose(); if (rendered != null) rendered.Dispose();
            features.Dispose();
            if (color != null) color.Dispose(); if (smooth != null) smooth.Dispose(); if (depth != null) depth.Dispose(); if (volume != null) volume.Dispose();
            archive.Dispose();
            lock (gate) state = "closed";
        }
    }
}
