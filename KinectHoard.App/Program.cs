using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Serialization.Json;
using System.Web.Script.Serialization;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using KinectHoard.Core;

namespace KinectHoard.App
{
    internal static class Program
    {
        [STAThread]
        private static int Main(string[] args)
        {
            if (args.Length == 4 && args[0] == "--scanner-server")
            {
                var scanner = new FusionScanner(ParseModel(args[2]), args[1], args[3], Path.Combine(ScannerExport.Root(), "captures", "live-" + DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")));
                return CameraStreamServer.Run(64320, StreamKind.ColorDepth, 0, scanner.Model, true, scanner);
            }
            if (args.Length == 6 && args[0] == "--scanner-replay")
            {
                try { return FusionScanner.Replay(args[1], ParseModel(args[2]), args[3], args[4], args[5] == "cpu"); }
                catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
            }
            if (args.Length == 4 && args[0] == "--scanner")
            {
                Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new LiveScannerForm(args[1], ParseModel(args[2]), args[3])); return 0;
            }
            if (args.Length == 6 && args[0] == "--scanner-probe")
            {
                var scanner = new FusionScanner(ParseModel(args[1]), args[2], args[3], args[4]);
                scanner.Command("start");
                return CameraStreamServer.Run(64320, StreamKind.ColorDepth, int.Parse(args[5]), ParseModel(args[1]), true, scanner);
            }
            if (args.Length == 4 && args[0] == "--rgbd-server")
                return CameraStreamServer.Run(int.Parse(args[2]), StreamKind.ColorDepth, int.Parse(args[3]), ParseModel(args[1]), true);
            if (args.Length == 2 && args[0] == "--diagnose") return Diagnose(args[1]);
            if (args.Length == 4 && args[0] == "--stress")
                return Stress(args[1], int.Parse(args[2]), ParseStream(args[3]));
            if (args.Length == 5 && args[0] == "--stress-model")
                return Stress(args[2], int.Parse(args[3]), ParseStream(args[4]), ParseModel(args[1]));
            if (args.Length == 5 && args[0] == "--stress-dual")
                return StressDual(args[1], int.Parse(args[2]), ParseStream(args[3]), ParseStream(args[4]));
            if (args.Length == 4 && args[0] == "--webserver")
                return CameraStreamServer.Run(int.Parse(args[1]), ParseStream(args[2]), int.Parse(args[3]));
            if (args.Length == 5 && args[0] == "--webserver-model")
                return CameraStreamServer.Run(int.Parse(args[2]), ParseStream(args[3]), int.Parse(args[4]), ParseModel(args[1]));
            if (args.Length == 4 && args[0] == "--face-image") return FaceAnalyzer.AnalyzeFile(args[1], args[2], args[3]);
            if (args.Length == 3 && args[0] == "--face-capture") return FaceAnalyzer.Capture(args[1], args[2]);
            if (args.Length == 4 && args[0] == "--face-capture-model") return FaceAnalyzer.Capture(args[2], args[3], ParseModel(args[1]));
            if (args.Length == 4 && args[0] == "--face3d") return CaptureFace3D(args[1], args[2], int.Parse(args[3]));
            if (args.Length == 4 && args[0] == "--headscan") return CaptureFace3D(args[1], args[2], int.Parse(args[3]), true);
            if (args.Length == 3 && args[0] == "--gestures-session") return GestureDemo.AnalyzeSession(args[1], args[2]);
            if (args.Length == 3 && args[0] == "--gestures-live") return GestureDemo.Capture(args[1], int.Parse(args[2]));
            if (args.Length == 4 && args[0] == "--gestures-live-model") return GestureDemo.Capture(args[2], int.Parse(args[3]), ParseModel(args[1]));
            if (args.Length == 2 && args[0] == "--point-cloud") return ExportPointCloud(args[1]);
            if (args.Length == 2 && args[0] == "--mesh") return ExportMesh(args[1]);
            if (args.Length == 3 && args[0] == "--point-cloud-model") return ExportGeometry(args[2], StreamKind.Depth, false, ParseModel(args[1]));
            if (args.Length == 3 && args[0] == "--mesh-model") return ExportGeometry(args[2], StreamKind.Depth, true, ParseModel(args[1]));
            if (args.Length == 2 && args[0] == "--color-cloud") return ExportGeometry(args[1], StreamKind.ColorDepth, false);
            if (args.Length == 2 && args[0] == "--color-mesh") return ExportGeometry(args[1], StreamKind.ColorDepth, true);
            if (args.Length == 3 && args[0] == "--color-cloud-model") return ExportGeometry(args[2], StreamKind.ColorDepth, false, ParseModel(args[1]));
            if (args.Length == 3 && args[0] == "--color-mesh-model") return ExportGeometry(args[2], StreamKind.ColorDepth, true, ParseModel(args[1]));
            if (args.Length == 2 && args[0] == "--bodies") return ExportBodies(args[1]);
            if (args.Length == 3 && args[0] == "--bodies-model") return ExportBodies(args[2], ParseModel(args[1]));
            if (args.Length == 3 && args[0] == "--audio-record") return RecordAudio(args[1], int.Parse(args[2]));
            if (args.Length == 3 && args[0] == "--speech-recognize")
                return SpeechCommands.RecognizeFile(args[1], args[2], Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "speech-commands.txt"));
            if (args.Length == 3 && args[0] == "--speech-live")
            {
                int recorded = RecordAudio(args[1], int.Parse(args[2]));
                if (new FileInfo(args[1]).Length <= 44) return 2;
                int recognized = SpeechCommands.RecognizeFile(args[1], Path.ChangeExtension(args[1], ".speech.json"), Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "speech-commands.txt"));
                return recorded == 0 ? recognized : 2;
            }
            if (args.Length == 4 && args[0] == "--record") return Record(args[1], int.Parse(args[2]), ParseStream(args[3]));
            if (args.Length == 5 && args[0] == "--record-model")
                return Record(args[2], int.Parse(args[3]), ParseStream(args[4]), ParseModel(args[1]));
            if (args.Length == 5 && args[0] == "--record-quality-model")
                return Record(args[2], int.Parse(args[3]), ParseStream(args[4]), ParseModel(args[1]), true);
            if (args.Length == 5 && args[0] == "--record-dual")
                return RecordDual(args[1], args[2], int.Parse(args[3]), ParseStream(args[4]));
            if (args.Length == 5 && args[0] == "--record-dual-quality")
                return RecordDual(args[1], args[2], int.Parse(args[3]), ParseStream(args[4]), true);
            if (args.Length == 3 && args[0] == "--replay-last") return ReplayLast(args[1], args[2]);
            if (args.Length == 3 && args[0] == "--session-info") return SessionInfo(args[1], args[2]);
            if ((args.Length == 2 || args.Length == 3) && (args[0] == "--capture" || args[0] == "--capture-raw"))
                return Capture(args[1], args.Length == 3 ? ParseStream(args[2]) : StreamKind.Color, args[0] == "--capture-raw");
            if (args.Length == 4 && (args[0] == "--capture-model" || args[0] == "--capture-raw-model"))
                return Capture(args[2], ParseStream(args[3]), args[0] == "--capture-raw-model", ParseModel(args[1]));
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
            return 0;
        }

        private static int Stress(string path, int seconds, StreamKind stream, string model = "one")
        {
            if (seconds < 1 || seconds > 600) throw new ArgumentOutOfRangeException("seconds");
            ICameraBackend backend = null;
            int frames = 0, losses = 0, reopenings = 0, timeouts = 0;
            bool presentBefore = false;
            DateTime lastFrame = DateTime.UtcNow;
            DateTime nextProbe = DateTime.MinValue;
            DateTime end = DateTime.UtcNow.AddSeconds(seconds);
            using (var writer = new StreamWriter(path, false))
            {
                writer.AutoFlush = true;
                writer.WriteLine("Kinect Hoard stress " + model + " " + stream + " " + DateTime.Now.ToString("O"));
                try
                {
                    while (DateTime.UtcNow < end)
                    {
                        if (DateTime.UtcNow >= nextProbe)
                        {
                            var usbStatus = UsbDiscovery.GetStatus(model);
                            bool present = usbStatus.Usable;
                            if (presentBefore && !present)
                            { losses++; writer.WriteLine(DateTime.Now.ToString("HH:mm:ss.fff") + " USB unavailable: " + usbStatus.Description); }
                            if (!presentBefore && present)
                                writer.WriteLine(DateTime.Now.ToString("HH:mm:ss.fff") + " USB ready: " + usbStatus.Description);
                            if (!present && !presentBefore && frames == 0 && nextProbe == DateTime.MinValue)
                                writer.WriteLine(DateTime.Now.ToString("HH:mm:ss.fff") + " USB unavailable: " + usbStatus.Description);
                            presentBefore = present;
                            nextProbe = DateTime.UtcNow.AddMilliseconds(500);
                        }
                        if (backend == null && presentBefore)
                        {
                            try
                            {
                                backend = LoadBackend(model);
                                backend.Open(stream);
                                reopenings++;
                                lastFrame = DateTime.UtcNow;
                                writer.WriteLine(DateTime.Now.ToString("HH:mm:ss.fff") + " stream opened");
                            }
                            catch (Exception ex)
                            {
                                writer.WriteLine(DateTime.Now.ToString("HH:mm:ss.fff") + " open error " + ex.GetBaseException().Message);
                                if (backend != null) { backend.Dispose(); backend = null; }
                                Thread.Sleep(500);
                            }
                        }
                        if (backend != null)
                        {
                            try
                            {
                                CameraFrame frame;
                                if (backend.TryRead(out frame)) { frames++; lastFrame = DateTime.UtcNow; }
                                else if ((DateTime.UtcNow - lastFrame).TotalSeconds > 3)
                                {
                                    timeouts++;
                                    bool sensorObjectPresent = backend.IsAvailable; // Refresh Detail with the SDK state at the timeout.
                                    writer.WriteLine(DateTime.Now.ToString("HH:mm:ss.fff") + " frame timeout; usb=" + UsbDiscovery.IsPresent(model) + "; sensor_object=" + sensorObjectPresent + "; detail=" + backend.Detail);
                                    backend.Dispose(); backend = null;
                                }
                            }
                            catch (Exception ex)
                            {
                                writer.WriteLine(DateTime.Now.ToString("HH:mm:ss.fff") + " stream error " + ex.GetBaseException().Message);
                                backend.Dispose(); backend = null;
                            }
                        }
                        Thread.Sleep(30);
                    }
                }
                finally { if (backend != null) backend.Dispose(); }
                writer.WriteLine("SUMMARY frames=" + frames + " usb_losses=" + losses + " openings=" + reopenings + " frame_timeouts=" + timeouts);
            }
            return losses == 0 && frames > 0 && reopenings == 1 && timeouts == 0 ? 0 : 2;
        }

        private static int StressDual(string directory, int seconds, StreamKind oneStream, StreamKind threeSixtyStream)
        {
            Directory.CreateDirectory(directory);
            // Separate AppDomains and backend instances keep the v1 and v2 readers independent.
            var one = Task.Run(() => Stress(Path.Combine(directory, "one.txt"), seconds, oneStream, "one"));
            var threeSixty = Task.Run(() => Stress(Path.Combine(directory, "360.txt"), seconds, threeSixtyStream, "360"));
            Task.WaitAll(one, threeSixty);
            return one.Result == 0 && threeSixty.Result == 0 ? 0 : 2;
        }

        private static int Diagnose(string path)
        {
            try
            {
                using (var writer = new StreamWriter(path, false))
                    foreach (string model in new[] { "one", "360" })
                    {
                        var usb = UsbDiscovery.GetStatus(model);
                        writer.WriteLine(model + " USB=" + usb.Usable + " detected=" + usb.Detected + " problem_code=" + usb.ProblemCode + " detail=" + usb.Description);
                        try
                        {
                            using (var backend = LoadBackend(model))
                                writer.WriteLine(model + " backend=" + backend.BackendName + " available=" + backend.IsAvailable + " detail=" + backend.Detail);
                        }
                        catch (Exception ex) { writer.WriteLine(model + " backend_error=" + ex); }
                    }
                return 0;
            }
            catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
        }

        private static int ExportPointCloud(string path) { return ExportGeometry(path, StreamKind.Depth, false); }
        private static int ExportMesh(string path) { return ExportGeometry(path, StreamKind.Depth, true); }

        private static int ExportGeometry(string path, StreamKind stream, bool mesh, string model = "one")
        {
            try
            {
                using (var backend = LoadBackend(model))
                {
                    backend.Open(stream);
                    DateTime deadline = DateTime.UtcNow.AddSeconds(12);
                    while (DateTime.UtcNow < deadline)
                    {
                        PointCloudFrame frame;
                        if (backend.TryReadPointCloud(out frame))
                        {
                            if (mesh)
                            {
                                FrameExporter.MeshResult result = FrameExporter.SaveMeshPly(path, frame);
                                Console.WriteLine("Malla PLY: " + result.Vertices + " vértices, " + result.Faces + " caras -> " + path);
                                return result.Faces > 0 ? 0 : 2;
                            }
                            int count = FrameExporter.SavePly(path, frame);
                            Console.WriteLine("Nube PLY: " + count + " puntos -> " + path);
                            return count > 0 ? 0 : 2;
                        }
                        Thread.Sleep(30);
                    }
                }
                Console.Error.WriteLine("No llegó un fotograma de profundidad para la geometría.");
                return 2;
            }
            catch (Exception ex) { Console.Error.WriteLine("Geometría: " + ex.GetBaseException().Message); return 1; }
        }

        private static int ExportBodies(string path, string model = "one")
        {
            try
            {
                using (var backend = LoadBackend(model))
                {
                    backend.Open(StreamKind.Skeleton);
                    DateTime deadline = DateTime.UtcNow.AddSeconds(12);
                    while (DateTime.UtcNow < deadline)
                    {
                        CameraFrame frame;
                        if (backend.TryRead(out frame))
                        {
                            using (var output = File.Create(path))
                                new DataContractJsonSerializer(typeof(TrackedBody[])).WriteObject(output, frame.Bodies ?? new TrackedBody[0]);
                            Console.WriteLine("Esqueletos: " + (frame.Bodies == null ? 0 : frame.Bodies.Length) + " -> " + path);
                            return 0;
                        }
                        Thread.Sleep(30);
                    }
                }
                Console.Error.WriteLine("No llegó un fotograma de seguimiento corporal.");
                return 2;
            }
            catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
        }

        internal static int RecordAudio(string path, int seconds)
        {
            if (seconds < 1 || seconds > 120) throw new ArgumentOutOfRangeException("seconds");
            IAudioBackend backend = null;
            int chunks = 0, openings = 0, absentPolls = 0;
            DateTime startupDeadline = DateTime.UtcNow.AddSeconds(15);
            DateTime deadline = DateTime.MaxValue;
            DateTime lastAudio = DateTime.UtcNow;
            DateTime nextMetadata = DateTime.MinValue;
            var direction = new List<Dictionary<string, object>>();
            using (var wave = new FloatWaveWriter(path))
            {
                try
                {
                    while (DateTime.UtcNow < (chunks == 0 ? startupDeadline : deadline))
                    {
                        try
                        {
                            if (!UsbDiscovery.IsPresent("one"))
                            {
                                absentPolls++;
                                if (backend != null) { backend.Dispose(); backend = null; }
                                Thread.Sleep(300);
                                continue;
                            }
                            if (backend == null)
                            {
                                backend = LoadAudioBackend();
                                backend.Open();
                                openings++;
                                lastAudio = DateTime.UtcNow;
                            }
                            AudioChunk chunk;
                            if (backend.TryRead(out chunk))
                            {
                                if (chunks == 0) deadline = DateTime.UtcNow.AddSeconds(seconds);
                                wave.Write(chunk);
                                chunks++;
                                lastAudio = DateTime.UtcNow;
                                if (DateTime.UtcNow >= nextMetadata)
                                {
                                    direction.Add(new Dictionary<string, object> {
                                        { "timestamp_utc", chunk.TimestampUtc.ToString("O") },
                                        { "beam_angle_radians", chunk.BeamAngleRadians },
                                        { "beam_confidence", chunk.BeamConfidence }
                                    });
                                    nextMetadata = DateTime.UtcNow.AddMilliseconds(200);
                                }
                            }
                            else if ((DateTime.UtcNow - lastAudio).TotalSeconds > 3)
                            { Console.Error.WriteLine("Audio sin muestras: " + backend.Detail); backend.Dispose(); backend = null; }
                        }
                        catch (Exception ex)
                        {
                            Console.Error.WriteLine("Audio: " + ex.GetBaseException().Message);
                            if (backend != null) { try { backend.Dispose(); } catch { } backend = null; }
                            Thread.Sleep(300);
                        }
                        Thread.Sleep(1);
                    }
                }
                finally { if (backend != null) backend.Dispose(); }
                var metadata = new Dictionary<string, object> {
                    { "sample_rate", 16000 }, { "channels", 1 }, { "format", "IEEE_FLOAT_32" },
                    { "audio_bytes", wave.DataBytes }, { "audio_seconds", wave.DataBytes / 64000.0 },
                    { "requested_seconds", seconds }, { "chunks", chunks }, { "direction", direction }
                };
                File.WriteAllText(Path.ChangeExtension(path, ".json"), new JavaScriptSerializer().Serialize(metadata));
                Console.WriteLine("Audio: " + wave.DataBytes + " bytes, aperturas=" + openings + ", USB ausente=" + absentPolls + " -> " + path);
                return wave.DataBytes >= seconds * 64000 * 0.8 ? 0 : 2;
            }
        }

        private static int Record(string path, int seconds, StreamKind stream, string model = "one", bool quality = false)
        {
            if (seconds < 1 || seconds > 120) throw new ArgumentOutOfRangeException("seconds");
            if (quality && stream != StreamKind.ColorDepth) throw new ArgumentException("La sesión de calidad requiere ColorDepth.");
            int count = 0;
            ICameraBackend backend = null;
            DateTime end = DateTime.UtcNow.AddSeconds(seconds);
            DateTime nextSample = DateTime.MinValue;
            DateTime lastFrame = DateTime.UtcNow;
            using (var writer = new SessionWriter(path, stream, quality))
            {
                try
                {
                    while (DateTime.UtcNow < end)
                    {
                        try
                        {
                            if (!UsbDiscovery.IsPresent(model))
                            {
                                if (backend != null) { backend.Dispose(); backend = null; }
                                Thread.Sleep(300);
                                continue;
                            }
                            if (backend == null)
                            {
                                backend = LoadBackend(model);
                                backend.Open(stream);
                                lastFrame = DateTime.UtcNow;
                            }
                            CameraFrame frame;
                            bool sampleReady = DateTime.UtcNow >= nextSample;
                            if (quality) backend.SetQualityColor(sampleReady);
                            if (backend.TryRead(out frame))
                            {
                                lastFrame = DateTime.UtcNow;
                                if (stream == StreamKind.ColorDepth && count == 0) WriteDepthMetadata(path, backend);
                                if (sampleReady)
                                {
                                    writer.WriteFrame(frame);
                                    count++;
                                    nextSample = DateTime.UtcNow.AddMilliseconds(200);
                                }
                            }
                            else if ((DateTime.UtcNow - lastFrame).TotalSeconds > 3)
                            { backend.Dispose(); backend = null; }
                        }
                        catch
                        {
                            if (backend != null) { try { backend.Dispose(); } catch { } backend = null; }
                            Thread.Sleep(300);
                        }
                        Thread.Sleep(25);
                    }
                }
                finally { if (backend != null) backend.Dispose(); }
            }
            Console.WriteLine("Sesión: " + count + " fotogramas -> " + path);
            return count > 0 ? 0 : 2;
        }

        private static int RecordDual(string onePath, string threeSixtyPath, int seconds, StreamKind stream, bool quality = false)
        {
            if (stream != StreamKind.ColorDepth) throw new ArgumentException("El escáner dual requiere ColorDepth.");
            if (Path.GetFullPath(onePath).Equals(Path.GetFullPath(threeSixtyPath), StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Las dos sesiones necesitan rutas distintas.");
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(onePath)));
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(threeSixtyPath)));
            var one = Task.Run(() => Record(onePath, seconds, stream, "one", quality));
            var threeSixty = Task.Run(() => Record(threeSixtyPath, seconds, stream, "360", quality));
            Task.WaitAll(one, threeSixty);
            return one.Result == 0 && threeSixty.Result == 0 ? 0 : 2;
        }

        internal static void WriteDepthMetadata(string sessionPath, ICameraBackend backend)
        {
            DepthIntrinsics intrinsics = backend.GetDepthIntrinsics();
            var metadata = new Dictionary<string, object> {
                { "format", "KINECT_HOARD_RGBD_1" }, { "depth_unit", "millimetres" },
                { "color_space", "RGB registered to depth pixels" },
                { "intrinsics", new Dictionary<string, object> {
                    { "width", intrinsics.Width }, { "height", intrinsics.Height },
                    { "fx", intrinsics.Fx }, { "fy", intrinsics.Fy },
                    { "cx", intrinsics.Cx }, { "cy", intrinsics.Cy },
                    { "k2", intrinsics.K2 }, { "k4", intrinsics.K4 }, { "k6", intrinsics.K6 },
                    { "method", intrinsics.Method }
                } }
            };
            File.WriteAllText(Path.ChangeExtension(sessionPath, ".intrinsics.json"), new JavaScriptSerializer().Serialize(metadata));
        }

        private static int ReplayLast(string sessionPath, string imagePath)
        {
            try
            {
                CameraFrame last = null, frame;
                using (var reader = new SessionReader(sessionPath))
                    while (reader.TryRead(out frame)) last = frame;
                if (last == null) return 2;
                using (var image = FrameImage.Create(last)) image.Save(imagePath, ImageFormat.Png);
                Console.WriteLine("Reproducción: " + imagePath);
                return 0;
            }
            catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
        }

        private static int SessionInfo(string sessionPath, string outputPath)
        {
            try
            {
                int count = 0, width = 0, height = 0, maxBodies = 0;
                DateTime first = DateTime.MinValue, last = DateTime.MinValue, started;
                StreamKind stream;
                string format;
                using (var reader = new SessionReader(sessionPath))
                {
                    started = reader.StartedUtc;
                    stream = reader.Stream;
                    format = reader.Format;
                    CameraFrame frame;
                    while (reader.TryRead(out frame))
                    {
                        if (count++ == 0) first = frame.TimestampUtc;
                        last = frame.TimestampUtc;
                        width = frame.Width; height = frame.Height;
                        maxBodies = Math.Max(maxBodies, frame.Bodies == null ? 0 : frame.Bodies.Length);
                    }
                }
                var info = new Dictionary<string, object> {
                    { "format", format }, { "stream", stream.ToString() },
                    { "started_utc", started.ToString("O") }, { "frames", count },
                    { "first_frame_utc", count == 0 ? null : first.ToString("O") },
                    { "last_frame_utc", count == 0 ? null : last.ToString("O") },
                    { "width", width }, { "height", height }, { "max_tracked_bodies", maxBodies }
                };
                File.WriteAllText(outputPath, new JavaScriptSerializer().Serialize(info));
                return 0;
            }
            catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
        }

        internal static ICameraBackend LoadBackend(string model)
        {
            bool native360 = model == "360" &&
                File.Exists(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "KinectHoard.Native360.dll"));
            string name = model == "one" ? "KinectHoard.Driver.One" :
                native360 ? "KinectHoard.Driver.ThreeSixty.Native" : "KinectHoard.Driver.ThreeSixty";
            string type = model == "one" ? "KinectHoard.Driver.One.OneCamera" :
                native360 ? "KinectHoard.Driver.ThreeSixty.Native.NativeThreeSixtyCamera" :
                    "KinectHoard.Driver.ThreeSixty.ThreeSixtyCamera";
            string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, name + ".dll");
            if (!File.Exists(path)) throw new FileNotFoundException("Falta el controlador de la aplicación: " + name + ".dll");
            // v1 and v2 have the same assembly name. Separate AppDomains keep their CLR bindings apart.
            var setup = new AppDomainSetup { ApplicationBase = AppDomain.CurrentDomain.BaseDirectory };
            var domain = AppDomain.CreateDomain("KinectHoard." + model + "." + Guid.NewGuid().ToString("N"), null, setup);
            try
            {
                var instance = (ICameraBackend)domain.CreateInstanceFromAndUnwrap(path, type);
                return new IsolatedCameraBackend(domain, instance);
            }
            catch { AppDomain.Unload(domain); throw; }
        }

        internal static IAudioBackend LoadAudioBackend()
        {
            string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "KinectHoard.Driver.One.dll");
            var setup = new AppDomainSetup { ApplicationBase = AppDomain.CurrentDomain.BaseDirectory };
            var domain = AppDomain.CreateDomain("KinectHoard.audio." + Guid.NewGuid().ToString("N"), null, setup);
            try
            {
                var instance = (IAudioBackend)domain.CreateInstanceFromAndUnwrap(path, "KinectHoard.Driver.One.OneAudio");
                return new IsolatedAudioBackend(domain, instance);
            }
            catch { AppDomain.Unload(domain); throw; }
        }

        private static IFaceBackend LoadFaceBackend()
        {
            string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "KinectHoard.Driver.One.dll");
            var setup = new AppDomainSetup { ApplicationBase = AppDomain.CurrentDomain.BaseDirectory };
            var domain = AppDomain.CreateDomain("KinectHoard.face." + Guid.NewGuid().ToString("N"), null, setup);
            try
            {
                var instance = (IFaceBackend)domain.CreateInstanceFromAndUnwrap(path, "KinectHoard.Driver.One.OneFace");
                return new IsolatedFaceBackend(domain, instance);
            }
            catch { AppDomain.Unload(domain); throw; }
        }

        private static int CaptureFace3D(string reportPath, string meshPath, int seconds, bool collectModel = false)
        {
            if (seconds < 1 || seconds > 120) throw new ArgumentOutOfRangeException("seconds");
            string progressPath = Path.ChangeExtension(reportPath, ".progress.json");
            try
            {
                FaceSnapshot latest = null;
                int faceFrames = 0;
                DateTime nextProgress = DateTime.MinValue;
                using (var backend = LoadFaceBackend())
                {
                    backend.Open();
                    if (collectModel) backend.StartModelCollection();
                    DateTime end = DateTime.UtcNow.AddSeconds(seconds);
                    while (DateTime.UtcNow < end)
                    {
                        FaceSnapshot next;
                        if (backend.TryRead(out next))
                        {
                            latest = next;
                            faceFrames++;
                            if (next.HighDefinitionTracked && next.VerticesMetres != null &&
                                (!collectModel || next.PersonalizedModel) &&
                                next.TriangleIndices != null && next.TriangleIndices.Length >= 3) break;
                        }
                        if (DateTime.UtcNow >= nextProgress)
                        {
                            WriteFaceProgress(progressPath, faceFrames, latest);
                            nextProgress = DateTime.UtcNow.AddSeconds(1);
                        }
                        Thread.Sleep(30);
                    }
                }
                WriteFaceProgress(progressPath, faceFrames, latest);
                var data = new Dictionary<string, object> {
                    { "format", "KINECT_HOARD_FACE3D_1" }, { "frames_with_face", faceFrames },
                    { "tracked", latest != null }, { "hd_tracked", latest != null && latest.HighDefinitionTracked },
                    { "model_collection_requested", collectModel },
                    { "personalized_model", latest != null && latest.PersonalizedModel },
                    { "coordinate_space", "Kinect camera metres: X right, Y up, Z forward" },
                    { "face", latest }
                };
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(reportPath)));
                File.WriteAllText(reportPath, new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Serialize(data));
                if (latest == null || latest.VerticesMetres == null || latest.TriangleIndices == null ||
                    (collectModel && !latest.PersonalizedModel))
                { Console.Error.WriteLine("No se completó el modelo facial solicitado; informe: " + reportPath); return 2; }
                SaveFacePly(meshPath, latest);
                Console.WriteLine("Rostro HD: " + (latest.VerticesMetres.Length / 3) + " vértices, " +
                    (latest.TriangleIndices.Length / 3) + " caras -> " + meshPath);
                return 0;
            }
            catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
        }

        private static void WriteFaceProgress(string path, int frames, FaceSnapshot face)
        {
            try
            {
                var data = new Dictionary<string, object> {
                    { "format", "KINECT_HOARD_FACE_PROGRESS_1" },
                    { "frames_with_face", frames },
                    { "hd_tracked", face != null && face.HighDefinitionTracked },
                    { "personalized_model", face != null && face.PersonalizedModel },
                    { "collection_status", face == null ? "WaitingForFace" : face.ModelCollectionStatus },
                    { "capture_status", face == null ? "WaitingForFace" : face.ModelCaptureStatus },
                    { "updated_utc", DateTime.UtcNow.ToString("O") }
                };
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path)));
                File.WriteAllText(path, new JavaScriptSerializer().Serialize(data));
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }

        private static void SaveFacePly(string path, FaceSnapshot face)
        {
            int vertices = face.VerticesMetres.Length / 3;
            int triangles = face.TriangleIndices.Length / 3;
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path)));
            using (var writer = new StreamWriter(path, false))
            {
                writer.WriteLine("ply\nformat ascii 1.0\ncomment Kinect camera coordinates in metres\nelement vertex " + vertices);
                writer.WriteLine("property float x\nproperty float y\nproperty float z\nelement face " + triangles);
                writer.WriteLine("property list uchar int vertex_indices\nend_header");
                var culture = System.Globalization.CultureInfo.InvariantCulture;
                for (int i = 0; i < face.VerticesMetres.Length; i += 3)
                    writer.WriteLine(face.VerticesMetres[i].ToString("R", culture) + " " +
                        face.VerticesMetres[i + 1].ToString("R", culture) + " " +
                        face.VerticesMetres[i + 2].ToString("R", culture));
                for (int i = 0; i < face.TriangleIndices.Length; i += 3)
                {
                    uint a = face.TriangleIndices[i], b = face.TriangleIndices[i + 1], c = face.TriangleIndices[i + 2];
                    if (a >= vertices || b >= vertices || c >= vertices)
                        throw new InvalidDataException("Índice de triángulo facial fuera de la malla.");
                    writer.WriteLine("3 " + a + " " + b + " " + c);
                }
            }
        }

        private static StreamKind ParseStream(string text)
        {
            StreamKind stream;
            if (!Enum.TryParse(text, true, out stream) || !Enum.IsDefined(typeof(StreamKind), stream))
                throw new ArgumentException("Flujo desconocido: " + text);
            return stream;
        }

        private static string ParseModel(string model)
        {
            if (model != "one" && model != "360") throw new ArgumentException("Modelo desconocido: " + model);
            return model;
        }

        private static int Capture(string path, StreamKind stream, bool raw, string model = "one")
        {
            // A transient USB disconnect should not make a one-shot capture fail immediately.
            DateTime deadline = DateTime.UtcNow.AddSeconds(25);
            string lastError = null;
            while (DateTime.UtcNow < deadline)
            {
                try
                {
                    if (!UsbDiscovery.IsPresent(model)) { Thread.Sleep(500); continue; }
                    using (var backend = LoadBackend(model))
                    {
                        backend.Open(stream);
                        DateTime frameDeadline = DateTime.UtcNow.AddSeconds(5);
                        while (DateTime.UtcNow < frameDeadline && DateTime.UtcNow < deadline)
                        {
                            CameraFrame frame;
                            if (backend.TryRead(out frame))
                            {
                                if (raw)
                                {
                                    if (frame.Values == null) throw new InvalidOperationException("El flujo RGB no contiene valores de 16 bits.");
                                    FrameExporter.SavePgm(path, frame.Width, frame.Height, frame.Values);
                                }
                                else using (var image = FrameImage.Create(frame)) image.Save(path, ImageFormat.Png);
                                Console.WriteLine("Captura: " + frame.Width + "x" + frame.Height + " -> " + path);
                                return 0;
                            }
                            if (!UsbDiscovery.IsPresent(model)) break;
                            Thread.Sleep(30);
                        }
                    }
                }
                catch (Exception ex) { lastError = ex.GetBaseException().Message; }
                Thread.Sleep(500);
            }
            Console.Error.WriteLine("No se obtuvo fotograma tras 25 segundos. " + lastError);
            return 2;
        }
    }

    internal sealed class IsolatedCameraBackend : ICameraBackend
    {
        private AppDomain domain;
        private readonly ICameraBackend inner;
        internal IsolatedCameraBackend(AppDomain domain, ICameraBackend inner) { this.domain = domain; this.inner = inner; }
        public string Model { get { return inner.Model; } }
        public string BackendName { get { return inner.BackendName; } }
        public bool IsAvailable { get { return inner.IsAvailable; } }
        public string Detail { get { return inner.Detail; } }
        public void Open(StreamKind stream) { inner.Open(stream); }
        public bool TryRead(out CameraFrame frame) { return inner.TryRead(out frame); }
        public bool TryReadPointCloud(out PointCloudFrame frame) { return inner.TryReadPointCloud(out frame); }
        public DepthIntrinsics GetDepthIntrinsics() { return inner.GetDepthIntrinsics(); }
        public void SetQualityColor(bool enabled) { inner.SetQualityColor(enabled); }
        public void Close() { inner.Close(); }
        public void Dispose()
        {
            if (domain == null) return;
            try { inner.Dispose(); }
            finally { AppDomain.Unload(domain); domain = null; }
        }
    }

    internal sealed class IsolatedAudioBackend : IAudioBackend
    {
        private AppDomain domain;
        private readonly IAudioBackend inner;
        internal IsolatedAudioBackend(AppDomain domain, IAudioBackend inner) { this.domain = domain; this.inner = inner; }
        public string Detail { get { return inner.Detail; } }
        public void Open() { inner.Open(); }
        public bool TryRead(out AudioChunk chunk) { return inner.TryRead(out chunk); }
        public void Close() { inner.Close(); }
        public void Dispose()
        {
            if (domain == null) return;
            try { inner.Dispose(); }
            finally { AppDomain.Unload(domain); domain = null; }
        }
    }

    internal sealed class IsolatedFaceBackend : IFaceBackend
    {
        private AppDomain domain;
        private readonly IFaceBackend inner;
        internal IsolatedFaceBackend(AppDomain domain, IFaceBackend inner) { this.domain = domain; this.inner = inner; }
        public void Open() { inner.Open(); }
        public void StartModelCollection() { inner.StartModelCollection(); }
        public bool TryRead(out FaceSnapshot snapshot) { return inner.TryRead(out snapshot); }
        public void Close() { inner.Close(); }
        public void Dispose()
        {
            if (domain == null) return;
            try { inner.Dispose(); }
            finally { AppDomain.Unload(domain); domain = null; }
        }
    }

    internal static class FrameImage
    {
        internal static Bitmap Create(CameraFrame frame)
        {
            var bitmap = new Bitmap(frame.Width, frame.Height, PixelFormat.Format32bppRgb);
            var rect = new Rectangle(0, 0, frame.Width, frame.Height);
            var data = bitmap.LockBits(rect, ImageLockMode.WriteOnly, PixelFormat.Format32bppRgb);
            try
            {
                int rowLength = frame.Width * 4;
                if (data.Stride == rowLength) Marshal.Copy(frame.Bgra, 0, data.Scan0, rowLength * frame.Height);
                else for (int row = 0; row < frame.Height; row++)
                    Marshal.Copy(frame.Bgra, row * rowLength, IntPtr.Add(data.Scan0, row * data.Stride), rowLength);
            }
            finally { bitmap.UnlockBits(data); }
            return bitmap;
        }
    }

    internal sealed class MainForm : Form
    {
        private readonly ComboBox devices = new ComboBox();
        private readonly ComboBox streams = new ComboBox();
        private readonly Button refresh = new Button();
        private readonly Button start = new Button();
        private readonly Button stop = new Button();
        private readonly Button save = new Button();
        private readonly Button saveRaw = new Button();
        private readonly Button saveCloud = new Button();
        private readonly MenuStrip menu = new MenuStrip();
        private readonly ToolStripMenuItem liveGestures = new ToolStripMenuItem("Mostrar eventos en directo") { CheckOnClick = true };
        private readonly PictureBox preview = new PictureBox();
        private readonly SplitContainer workspace = new SplitContainer();
        private readonly ListBox capabilityList = new ListBox();
        private readonly TextBox capabilityDetail = new TextBox();
        private readonly Label status = new Label();
        private readonly TextBox log = new TextBox();
        private readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
        private readonly System.Windows.Forms.Timer retryTimer = new System.Windows.Forms.Timer();
        private ICameraBackend camera;
        private SessionWriter recording;
        private SessionReader playback;
        private bool playbackPaused;
        private bool playbackStep;
        private readonly ToolStripMenuItem pausePlaybackMenu = new ToolStripMenuItem("Pausar reproducción") { Enabled = false };
        private readonly ToolStripMenuItem stepPlaybackMenu = new ToolStripMenuItem("Fotograma siguiente") { Enabled = false };
        private DateTime recordingUntil;
        private DateTime nextRecordedFrame;
        private bool wantsCamera;
        private bool speechRecording;
        private bool faceRecording;
        private volatile System.Diagnostics.Process faceProcess;
        private bool scanRunning;
        private volatile System.Diagnostics.Process scanProcess;
        private System.Diagnostics.Process webServerProcess;
        private bool resumeCameraAfterWebServer;
        private DateTime lastFrameAt;
        private string lastReconnectError;
        private Bitmap currentImage;
        private ushort[] currentValues;
        private TrackedBody[] currentBodies;
        private GestureEngine gestureEngine = new GestureEngine();
        private InteractionGallery interactionGallery;
        private AudioMonitorForm audioMonitor;
        private bool closing;
        private readonly ToolStripMenuItem avatarMode = new ToolStripMenuItem("Mostrar avatar 2D") { CheckOnClick = true };
        private int rawWidth;
        private int rawHeight;
        private StreamKind rawKind;
        private string pendingCloudPath;
        private string pendingMeshPath;
        private int frameCount;
        private DateTime fpsSince = DateTime.UtcNow;

        internal MainForm()
        {
            Text = "Kinect Hoard";
            ClientSize = new Size(1120, 790);
            MinimumSize = new Size(760, 570);
            BackColor = Color.FromArgb(22, 25, 31);
            ForeColor = Color.WhiteSmoke;
            Font = new Font("Segoe UI", 10);

            var title = new Label { Text = "KINECT HOARD", Font = new Font("Segoe UI Semibold", 13), ForeColor = Color.FromArgb(110, 224, 205), AutoSize = true, Margin = new Padding(1, 4, 10, 0) };
            var toolbar = new FlowLayoutPanel { Dock = DockStyle.Top, Height = 62, Padding = new Padding(14, 9, 14, 5), WrapContents = false, AutoScroll = true, BackColor = Color.FromArgb(31, 35, 43) };
            devices.DropDownStyle = ComboBoxStyle.DropDownList;
            devices.Width = 195;
            streams.DropDownStyle = ComboBoxStyle.DropDownList;
            streams.Width = 135;
            streams.Items.AddRange(new object[] { "Color RGB", "Profundidad", "Infrarrojos", "IR larga exposición", "Índice corporal", "Esqueleto", "Sin fondo", "RGB + profundidad" });
            streams.SelectedIndex = 0;
            refresh.Text = "Detectar";
            start.Text = "Abrir cámara";
            stop.Text = "Detener";
            save.Text = "Guardar PNG";
            saveRaw.Text = "Guardar datos";
            saveRaw.Enabled = false;
            saveCloud.Text = "Nube PLY";
            saveCloud.Enabled = false;
            foreach (var button in new[] { refresh, start, stop, save, saveRaw, saveCloud }) { button.AutoSize = true; button.Height = 34; button.Margin = new Padding(6, 1, 0, 0); }
            toolbar.Controls.Add(title);
            toolbar.Controls.Add(devices);
            toolbar.Controls.Add(streams);
            toolbar.Controls.Add(refresh);
            toolbar.Controls.Add(start);
            toolbar.Controls.Add(stop);
            toolbar.Controls.Add(save);
            toolbar.Controls.Add(saveRaw);
            toolbar.Controls.Add(saveCloud);
            var sessionMenu = new ToolStripMenuItem("Sesión");
            sessionMenu.DropDownItems.Add("Grabar 10 segundos...", null, (s, e) => StartRecording());
            sessionMenu.DropDownItems.Add("Reproducir archivo...", null, (s, e) => OpenRecording(false));
            sessionMenu.DropDownItems.Add("Abrir archivo en pausa...", null, (s, e) => OpenRecording(true));
            pausePlaybackMenu.ShortcutKeys = Keys.Control | Keys.Space;
            pausePlaybackMenu.Click += (s, e) => TogglePlaybackPause();
            stepPlaybackMenu.ShortcutKeys = Keys.Control | Keys.Right;
            stepPlaybackMenu.Click += (s, e) => { if (playback != null && playbackPaused) playbackStep = true; };
            sessionMenu.DropDownItems.Add(pausePlaybackMenu);
            sessionMenu.DropDownItems.Add(stepPlaybackMenu);
            sessionMenu.DropDownItems.Add("Detener grabación", null, (s, e) => StopRecording());
            menu.Items.Add(sessionMenu);
            var camerasMenu = new ToolStripMenuItem("Cámaras");
            camerasMenu.DropDownItems.Add("Ver ambas a la vez...", null, (s, e) => OpenDualPreview());
            menu.Items.Add(camerasMenu);
            var audioMenu = new ToolStripMenuItem("Audio y voz");
            audioMenu.DropDownItems.Add("Explorador: nivel y dirección...", null, (s, e) => OpenAudioMonitor());
            audioMenu.DropDownItems.Add("Grabar y reconocer 10 segundos...", null, async (s, e) => await CaptureSpeech());
            menu.Items.Add(audioMenu);
            var webMenu = new ToolStripMenuItem("Servidor local");
            webMenu.DropDownItems.Add("Iniciar vista web en 127.0.0.1:8765", null, (s, e) => StartWebServer());
            webMenu.DropDownItems.Add("Detener servidor", null, (s, e) => StopWebServer(true));
            menu.Items.Add(webMenu);
            var faceMenu = new ToolStripMenuItem("Rostro");
            faceMenu.DropDownItems.Add("Analizar imagen RGB actual...", null, (s, e) => AnalyzeCurrentFace());
            faceMenu.DropDownItems.Add("Capturar rostro HD (hasta 20 s)...", null, async (s, e) => await CaptureFace3DFromUi());
            faceMenu.DropDownItems.Add("Escanear modelo facial personalizado (hasta 90 s)...", null, async (s, e) => await CaptureFace3DFromUi(true));
            menu.Items.Add(faceMenu);
            var geometryMenu = new ToolStripMenuItem("Geometría");
            geometryMenu.DropDownItems.Add("Escáner en directo: cámara móvil...", null, (s, e) => OpenLiveScanner("moving"));
            geometryMenu.DropDownItems.Add("Escáner en directo: cámara fija...", null, (s, e) => OpenLiveScanner("fixed"));
            geometryMenu.DropDownItems.Add("Exportar malla PLY...", null, (s, e) => SaveMesh());
            geometryMenu.DropDownItems.Add("Fusion: escanear 15 segundos...", null, async (s, e) => await Scan3D());
            geometryMenu.DropDownItems.Add("Escáner con textura OBJ (15 segundos)...", null, async (s, e) => await Scan3D(true));
            geometryMenu.DropDownItems.Add("Escaneo dual con calibración (15 segundos)...", null, async (s, e) => await Scan3D(true, true));
            geometryMenu.DropDownItems.Add("Ver malla PLY u OBJ...", null, (s, e) => OpenMeshViewer());
            menu.Items.Add(geometryMenu);
            var gestureMenu = new ToolStripMenuItem("Gestos");
            gestureMenu.DropDownItems.Add(liveGestures);
            gestureMenu.DropDownItems.Add(avatarMode);
            gestureMenu.DropDownItems.Add("Analizar sesión de esqueleto...", null, (s, e) => AnalyzeGestureSession());
            gestureMenu.DropDownItems.Add("Galería: ShapeGame, TicTacToe y AdaptiveUI...", null, (s, e) => OpenInteractionGallery());
            menu.Items.Add(gestureMenu);
            menu.BackColor = Color.FromArgb(31, 35, 43);
            menu.ForeColor = Color.WhiteSmoke;
            MainMenuStrip = menu;

            workspace.Dock = DockStyle.Fill;
            workspace.Size = new Size(1120, 540);
            workspace.SplitterDistance = 730;
            workspace.Panel1MinSize = 360;
            workspace.Panel2MinSize = 240;
            workspace.BackColor = Color.FromArgb(31, 35, 43);
            preview.Dock = DockStyle.Fill;
            preview.SizeMode = PictureBoxSizeMode.Zoom;
            preview.BackColor = Color.Black;
            workspace.Panel1.Controls.Add(preview);
            capabilityList.Dock = DockStyle.Top;
            capabilityList.Height = 250;
            capabilityList.BackColor = Color.FromArgb(31, 35, 43);
            capabilityList.ForeColor = Color.WhiteSmoke;
            capabilityList.BorderStyle = BorderStyle.None;
            capabilityDetail.Dock = DockStyle.Fill;
            capabilityDetail.Multiline = true;
            capabilityDetail.ReadOnly = true;
            capabilityDetail.ScrollBars = ScrollBars.Vertical;
            capabilityDetail.BackColor = Color.FromArgb(25, 29, 35);
            capabilityDetail.ForeColor = Color.Gainsboro;
            capabilityDetail.BorderStyle = BorderStyle.None;
            capabilityDetail.Font = new Font("Consolas", 9);
            workspace.Panel2.Controls.Add(capabilityDetail);
            workspace.Panel2.Controls.Add(capabilityList);
            status.Dock = DockStyle.Bottom;
            status.Height = 34;
            status.Padding = new Padding(12, 7, 0, 0);
            status.BackColor = Color.FromArgb(31, 35, 43);
            log.Dock = DockStyle.Bottom;
            log.Height = 116;
            log.Multiline = true;
            log.ReadOnly = true;
            log.ScrollBars = ScrollBars.Vertical;
            log.BackColor = Color.FromArgb(26, 30, 37);
            log.ForeColor = Color.Gainsboro;
            log.BorderStyle = BorderStyle.None;
            log.Font = new Font("Consolas", 9);
            Controls.Add(workspace);
            Controls.Add(log);
            Controls.Add(status);
            Controls.Add(toolbar);
            Controls.Add(menu);

            refresh.Click += (s, e) => Scan();
            start.Click += (s, e) => OpenSelected();
            streams.SelectedIndexChanged += (s, e) => { if (wantsCamera) OpenSelected(); };
            stop.Click += (s, e) => StopCamera();
            save.Click += (s, e) => SaveImage();
            saveRaw.Click += (s, e) => SaveRaw();
            saveCloud.Click += (s, e) => SavePointCloud();
            capabilityList.SelectedIndexChanged += (s, e) => ShowCapability();
            timer.Interval = 33;
            timer.Tick += (s, e) => PollFrame();
            retryTimer.Interval = 1500;
            retryTimer.Tick += (s, e) => RetryOpen();
            Shown += (s, e) => { Scan(); if (devices.SelectedItem != null) OpenSelected(); };
            FormClosing += (s, e) => { closing = true; if (audioMonitor != null) audioMonitor.Close(); StopWebServer(false); StopScan(); StopFaceCapture(); StopCamera(); };
            LoadCapabilities();
            SetStatus("Esperando detección.");
        }

        private void Scan()
        {
            StopCamera();
            devices.Items.Clear();
            foreach (string model in new[] { "one", "360" })
            {
                string label = model == "one" ? "Kinect One / v2" : "Kinect 360 / v1";
                UsbDiscovery.DeviceStatus usbStatus = null;
                try { usbStatus = UsbDiscovery.GetStatus(model); } catch (Exception ex) { WriteLog("USB: " + ex.Message); }
                bool usb = usbStatus != null && usbStatus.Usable;
                bool backendReady = false;
                string detail;
                try
                {
                    using (var driver = Program.LoadBackend(model))
                    { backendReady = driver.IsAvailable; detail = driver.Detail; }
                }
                catch (Exception ex) { detail = ex.GetBaseException().Message; }
                string usbDetail = usbStatus == null ? "no se pudo consultar PnP" : usbStatus.Description;
                WriteLog(label + " | USB " + usbDetail + " | cámara " + (backendReady ? "disponible" : "no disponible") + " | " + detail);
                string state = usb ? " · conectada" : usbStatus != null && usbStatus.Detected ? " · error controlador " + usbStatus.ProblemCode : " · sin conectar";
                devices.Items.Add(new DeviceChoice(model, label + state, usb));
            }
            devices.SelectedIndex = ((DeviceChoice)devices.Items[0]).UsbPresent ? 0 : 1;
            SetStatus("Detección terminada. Selecciona una cámara.");
        }

        private void OpenSelected()
        {
            if (devices.SelectedItem == null) return;
            StopRecording();
            ClosePlayback();
            timer.Interval = 33;
            wantsCamera = true;
            retryTimer.Stop();
            CloseCamera();
            gestureEngine = new GestureEngine();
            TryOpenSelected();
        }

        private void OpenDualPreview()
        {
            bool resume = wantsCamera;
            StopCamera();
            using (var dual = new DualPreviewForm()) dual.ShowDialog(this);
            if (resume && !closing && !IsDisposed) OpenSelected();
        }

        private void TryOpenSelected()
        {
            if (!wantsCamera || devices.SelectedItem == null) return;
            var choice = (DeviceChoice)devices.SelectedItem;
            try
            {
                var usb = UsbDiscovery.GetStatus(choice.Model);
                if (!usb.Usable)
                {
                    SetStatus("No se puede abrir la cámara: " + usb.Description);
                    retryTimer.Start();
                    return;
                }
                camera = Program.LoadBackend(choice.Model);
                if (choice.Model == "360" && !camera.IsAvailable)
                    throw new InvalidOperationException(camera.Detail);
                camera.Open(SelectedStream());
                frameCount = 0;
                fpsSince = DateTime.UtcNow;
                lastFrameAt = DateTime.UtcNow;
                lastReconnectError = null;
                retryTimer.Stop();
                timer.Start();
                saveCloud.Enabled = SelectedStream() == StreamKind.Depth || SelectedStream() == StreamKind.ColorDepth;
                SetStatus("Cámara abierta; esperando imagen...");
                WriteLog(choice.Label + " | " + camera.BackendName + " | abierto");
            }
            catch (Exception ex)
            {
                string message = ex.GetBaseException().Message;
                if (message != lastReconnectError) WriteLog("Apertura: " + message);
                lastReconnectError = message;
                if (ex.GetBaseException() is NotSupportedException)
                {
                    wantsCamera = false;
                    CloseCamera();
                    SetStatus(message);
                    return;
                }
                ScheduleReconnect();
            }
        }

        private void PollFrame()
        {
            if (camera == null && playback == null) return;
            if (playback != null && playbackPaused && !playbackStep) return;
            playbackStep = false;
            try
            {
                if (recording != null && DateTime.UtcNow >= recordingUntil) StopRecording();
                if (pendingCloudPath != null && camera != null)
                {
                    PointCloudFrame cloud;
                    if (camera.TryReadPointCloud(out cloud))
                    {
                        int count = FrameExporter.SavePly(pendingCloudPath, cloud);
                        WriteLog("Nube PLY guardada: " + count + " puntos · " + pendingCloudPath);
                        pendingCloudPath = null;
                    }
                }
                if (pendingMeshPath != null && camera != null)
                {
                    PointCloudFrame cloud;
                    if (camera.TryReadPointCloud(out cloud))
                    {
                        FrameExporter.MeshResult mesh = FrameExporter.SaveMeshPly(pendingMeshPath, cloud);
                        WriteLog("Malla PLY: " + mesh.Vertices + " vértices, " + mesh.Faces + " caras · " + pendingMeshPath);
                        pendingMeshPath = null;
                    }
                }
                CameraFrame frame;
                bool received = playback != null ? playback.TryRead(out frame) : camera.TryRead(out frame);
                if (!received)
                {
                    if (playback != null)
                    {
                        ClosePlayback();
                        timer.Stop();
                        SetStatus("Fin de la grabación.");
                    }
                    else if ((DateTime.UtcNow - lastFrameAt).TotalSeconds > 3) ScheduleReconnect();
                    return;
                }
                lastFrameAt = DateTime.UtcNow;
                if (recording != null && DateTime.UtcNow >= nextRecordedFrame)
                {
                    recording.WriteFrame(frame);
                    nextRecordedFrame = DateTime.UtcNow.AddMilliseconds(200);
                }
                var next = avatarMode.Checked && frame.Kind == StreamKind.Skeleton
                    ? AvatarRenderer.Create(frame.Bodies, frame.Width, frame.Height)
                    : FrameImage.Create(frame);
                var old = currentImage;
                currentImage = next;
                preview.Image = next;
                if (old != null) old.Dispose();
                currentValues = frame.Values == null ? null : (ushort[])frame.Values.Clone();
                currentBodies = frame.Bodies;
                if (frame.Kind == StreamKind.Skeleton && interactionGallery != null && !interactionGallery.IsDisposed)
                    interactionGallery.Consume(frame);
                if (frame.Kind == StreamKind.Skeleton && liveGestures.Checked)
                    foreach (GestureEvent gesture in gestureEngine.Process(frame))
                        WriteLog("Gesto " + gesture.TrackingId + ": " + gesture.Gesture + " " + gesture.State);
                rawWidth = frame.Width;
                rawHeight = frame.Height;
                rawKind = frame.Kind;
                saveRaw.Enabled = currentValues != null || currentBodies != null;
                frameCount++;
                double elapsed = (DateTime.UtcNow - fpsSince).TotalSeconds;
                if (elapsed >= 1)
                {
                    string extra = frame.Bodies == null ? "" : " · " + frame.Bodies.Length + " cuerpos";
                    SetStatus(frame.Width + "×" + frame.Height + " " + frame.Kind + " · " + (frameCount / elapsed).ToString("0.0") + " fps" + extra + " · " + (playback == null ? camera.Model : "reproducción"));
                    frameCount = 0;
                    fpsSince = DateTime.UtcNow;
                }
            }
            catch (Exception ex)
            {
                WriteLog("Transmisión interrumpida: " + ex.GetBaseException().Message);
                if (playback != null) { ClosePlayback(); timer.Stop(); SetStatus("Grabación dañada o incompleta."); }
                else ScheduleReconnect();
            }
        }

        private void StopCamera()
        {
            wantsCamera = false;
            StopRecording();
            ClosePlayback();
            pendingCloudPath = null;
            pendingMeshPath = null;
            saveCloud.Enabled = false;
            retryTimer.Stop();
            CloseCamera();
        }

        private void CloseCamera()
        {
            timer.Stop();
            if (camera != null)
            {
                try { camera.Dispose(); } catch (Exception ex) { WriteLog("Cierre: " + ex.Message); }
                camera = null;
            }
        }

        private void ScheduleReconnect()
        {
            CloseCamera();
            saveCloud.Enabled = false;
            if (!wantsCamera) return;
            if (currentImage != null) { preview.Image = null; currentImage.Dispose(); currentImage = null; }
            currentValues = null;
            currentBodies = null;
            saveRaw.Enabled = false;
            SetStatus("Se perdió el flujo. Esperando la Kinect para reconectar...");
            retryTimer.Start();
        }

        private void RetryOpen()
        {
            if (!wantsCamera || devices.SelectedItem == null) { retryTimer.Stop(); return; }
            try
            {
                var choice = (DeviceChoice)devices.SelectedItem;
                if (!UsbDiscovery.IsPresent(choice.Model)) return;
                retryTimer.Stop();
                TryOpenSelected();
            }
            catch (Exception ex) { WriteLog("Reconexión: " + ex.GetBaseException().Message); }
        }

        private void SaveImage()
        {
            if (currentImage == null) { SetStatus("Todavía no hay imagen para guardar."); return; }
            using (var dialog = new SaveFileDialog { Filter = "Imagen PNG|*.png", FileName = "kinect-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".png", DefaultExt = "png" })
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    currentImage.Save(dialog.FileName, ImageFormat.Png);
                    WriteLog("Imagen guardada: " + dialog.FileName);
                }
        }

        private void SaveRaw()
        {
            if (currentBodies != null)
            {
                using (var dialog = new SaveFileDialog { Filter = "Articulaciones JSON|*.json", FileName = "kinect-bodies-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".json", DefaultExt = "json" })
                    if (dialog.ShowDialog(this) == DialogResult.OK)
                    {
                        using (var output = File.Create(dialog.FileName))
                            new DataContractJsonSerializer(typeof(TrackedBody[])).WriteObject(output, currentBodies);
                        WriteLog("Articulaciones guardadas: " + dialog.FileName);
                    }
                return;
            }
            if (currentValues == null) return;
            using (var dialog = new SaveFileDialog { Filter = "Datos PGM de 16 bits|*.pgm", FileName = "kinect-" + rawKind.ToString().ToLower() + "-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".pgm", DefaultExt = "pgm" })
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    FrameExporter.SavePgm(dialog.FileName, rawWidth, rawHeight, currentValues);
                    WriteLog("Datos de 16 bits guardados: " + dialog.FileName);
                }
        }

        private void SavePointCloud()
        {
            if (camera == null || (SelectedStream() != StreamKind.Depth && SelectedStream() != StreamKind.ColorDepth)) return;
            using (var dialog = new SaveFileDialog { Filter = "Nube de puntos PLY|*.ply", FileName = "kinect-cloud-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".ply", DefaultExt = "ply" })
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    pendingCloudPath = dialog.FileName;
                    SetStatus("Esperando el siguiente fotograma de profundidad para exportar PLY...");
                }
        }

        private void SaveMesh()
        {
            if (camera == null || (SelectedStream() != StreamKind.Depth && SelectedStream() != StreamKind.ColorDepth))
            { SetStatus("Abre Profundidad de una Kinect para exportar una malla."); return; }
            using (var dialog = new SaveFileDialog { Filter = "Malla PLY|*.ply", FileName = "kinect-mesh-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".ply", DefaultExt = "ply" })
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    pendingMeshPath = dialog.FileName;
                    SetStatus("Esperando el siguiente fotograma de profundidad para exportar malla...");
                }
        }

        private void OpenLiveScanner(string mode)
        {
            StopCamera();
            using (var scanner = new LiveScannerForm(mode, mode == "moving" ? "360" : "one")) scanner.ShowDialog(this);
        }

        private async Task Scan3D(bool quality = false, bool dual = false)
        {
            if (scanRunning) return;
            var choice = devices.SelectedItem as DeviceChoice;
            if (!dual && choice == null) { SetStatus("Selecciona una Kinect para escanear."); return; }
            if (dual && (!UsbDiscovery.IsPresent("one") || !UsbDiscovery.IsPresent("360")))
            { SetStatus("El escaneo dual necesita One y 360 conectadas a la vez."); return; }
            string extrinsicsPath = null;
            if (dual)
                using (var calibration = new OpenFileDialog { Filter = "Calibración dual JSON|*.json", Title = "Elige la calibración medida entre One y 360" })
                {
                    if (calibration.ShowDialog(this) != DialogResult.OK) return;
                    extrinsicsPath = calibration.FileName;
                }
            string root = AppDomain.CurrentDomain.BaseDirectory;
            if (!File.Exists(Path.Combine(root, "fusion.py")))
                root = Path.GetFullPath(Path.Combine(root, "..", "..", "..", ".."));
            string script = Path.Combine(root, "fusion.py");
            string python = Path.Combine(root, ".venv-scan", "Scripts", "python.exe");
            string bundledScanner = Path.Combine(root, "KinectHoard.Fusion.exe");
            bool bundled = File.Exists(bundledScanner);
            if (!bundled && (!File.Exists(script) || !File.Exists(python)))
            { SetStatus("Falta Fusion. Ejecuta setup-scan.ps1 o usa el ZIP completo de Hoard."); return; }
            string meshPath;
            using (var dialog = new SaveFileDialog { Filter = quality ? "Malla con textura OBJ|*.obj" : "Malla PLY|*.ply", FileName = (quality ? "kinect-scan-" : "kinect-fusion-") + DateTime.Now.ToString("yyyyMMdd-HHmmss") + (quality ? ".obj" : ".ply"), DefaultExt = quality ? "obj" : "ply" })
            {
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                meshPath = dialog.FileName;
            }
            bool resumeCamera = wantsCamera;
            StopCamera();
            scanRunning = true;
            SetStatus(dual ? "Escáner dual: grabando las dos cámaras; después alineará y texturizará..." :
                quality ? "Escáner: grabando 15 segundos RGBD; después generará malla y textura OBJ..." :
                "Fusion: grabando 15 segundos de RGB y profundidad; después reconstruirá la malla...");
            try
            {
                string sessionPath = Path.Combine(Path.GetDirectoryName(meshPath),
                    Path.GetFileNameWithoutExtension(meshPath) + "-" + Guid.NewGuid().ToString("N") + ".khr");
                string secondSessionPath = dual ? Path.Combine(Path.GetDirectoryName(meshPath),
                    Path.GetFileNameWithoutExtension(meshPath) + "-360-" + Guid.NewGuid().ToString("N") + ".khr") : null;
                string reportPath = Path.ChangeExtension(meshPath, quality ? ".scan.json" : ".fusion.json");
                string workingRoot = root;
                var result = await Task.Run(() =>
                {
                    var startInfo = new System.Diagnostics.ProcessStartInfo {
                        FileName = bundled ? bundledScanner : python,
                        Arguments = (bundled ? "" : "\"" + script + "\" ") + (quality ? "--quality " : "") +
                            "\"" + sessionPath + "\" \"" + meshPath + "\" --report \"" + reportPath + "\" " +
                            (dual ? "--second-session \"" + secondSessionPath + "\" --extrinsics \"" + extrinsicsPath + "\" --capture-dual 15 --tracking fixed" :
                                "--capture 15 --model " + choice.Model + " --tracking auto"),
                        WorkingDirectory = workingRoot,
                        UseShellExecute = false, CreateNoWindow = true,
                        RedirectStandardOutput = true, RedirectStandardError = true,
                        WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden
                    };
                    using (var process = System.Diagnostics.Process.Start(startInfo))
                    {
                        scanProcess = process;
                        string output = process.StandardOutput.ReadToEnd();
                        string error = process.StandardError.ReadToEnd();
                        process.WaitForExit();
                        return Tuple.Create(process.ExitCode, output, error);
                    }
                });
                if (result.Item1 != 0) throw new InvalidOperationException(result.Item3.Trim());
                var report = (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(File.ReadAllText(reportPath));
                if (quality)
                    WriteLog("Escáner: " + report["triangles"] + " caras, textura " + report["texture_width"] + "×" + report["texture_height"] + "; " + meshPath);
                else
                    WriteLog("Fusion: " + report["frames_integrated"] + " fotogramas, " + report["triangles"] + " caras; " + meshPath);
                SetStatus((quality ? "Malla OBJ y textura guardadas: " : "Malla 3D guardada: ") + report["triangles"] + " caras.");
                if (dual) WriteLog("Escáner dual: solape temporal " + report["capture_overlap_seconds"] + " s; " + secondSessionPath);
                OpenMeshViewer(meshPath);
            }
            catch (Exception ex)
            {
                if (!IsDisposed && !Disposing)
                {
                    WriteLog((quality ? "Escáner: " : "Fusion: ") + ex.GetBaseException().Message);
                    SetStatus((quality ? "El escáner" : "Fusion") + " no pudo completarse; consulta el registro.");
                }
            }
            finally
            {
                scanProcess = null;
                scanRunning = false;
                if (resumeCamera && !IsDisposed && !Disposing) OpenSelected();
            }
        }

        private void StopScan()
        {
            try
            {
                var process = scanProcess;
                if (process == null || process.HasExited) return;
                using (var killer = System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo {
                    FileName = "taskkill.exe", Arguments = "/PID " + process.Id + " /T /F",
                    UseShellExecute = false, CreateNoWindow = true,
                    WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden
                }))
                    killer.WaitForExit(5000);
            }
            catch { }
        }

        private void OpenMeshViewer(string meshPath = null)
        {
            if (meshPath == null)
            {
                using (var dialog = new OpenFileDialog { Filter = "Malla 3D PLY u OBJ|*.ply;*.obj|PLY|*.ply|OBJ con textura|*.obj" })
                {
                    if (dialog.ShowDialog(this) != DialogResult.OK) return;
                    meshPath = dialog.FileName;
                }
            }
            string root = AppDomain.CurrentDomain.BaseDirectory;
            if (!File.Exists(Path.Combine(root, "fusion.py")))
                root = Path.GetFullPath(Path.Combine(root, "..", "..", "..", ".."));
            string bundled = Path.Combine(root, "KinectHoard.Fusion.exe");
            string python = Path.Combine(root, ".venv-scan", "Scripts", "python.exe");
            if (!File.Exists(bundled) && !File.Exists(python))
            { SetStatus("Falta el visor 3D de Fusion."); return; }
            try
            {
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo {
                    FileName = File.Exists(bundled) ? bundled : python,
                    Arguments = (File.Exists(bundled) ? "" : "\"" + Path.Combine(root, "fusion.py") + "\" ") + "--view \"" + meshPath + "\"",
                    WorkingDirectory = root,
                    UseShellExecute = false, CreateNoWindow = true,
                    WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden
                });
                WriteLog("Visor 3D: " + meshPath);
            }
            catch (Exception ex) { WriteLog("Visor 3D: " + ex.GetBaseException().Message); }
        }

        private void StartWebServer()
        {
            if (webServerProcess != null && !webServerProcess.HasExited) { SetStatus("El servidor local ya está iniciado."); return; }
            if (webServerProcess != null) { webServerProcess.Dispose(); webServerProcess = null; }
            var choice = devices.SelectedItem as DeviceChoice;
            if (choice == null) { SetStatus("Selecciona una Kinect antes de iniciar el servidor."); return; }
            resumeCameraAfterWebServer = wantsCamera;
            StopCamera();
            try
            {
                webServerProcess = System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo {
                    FileName = Application.ExecutablePath,
                    Arguments = "--webserver-model " + choice.Model + " 8765 " + SelectedStream() + " 0",
                    WorkingDirectory = AppDomain.CurrentDomain.BaseDirectory,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden
                });
                Thread.Sleep(300);
                if (webServerProcess == null || webServerProcess.HasExited)
                    throw new InvalidOperationException("No se pudo abrir el puerto local 8765.");
                WriteLog("Servidor local: http://127.0.0.1:8765/ (" + SelectedStream() + ")");
                SetStatus("Servidor iniciado; abre http://127.0.0.1:8765/ en el navegador.");
            }
            catch (Exception ex)
            {
                WriteLog("Servidor: " + ex.GetBaseException().Message);
                if (webServerProcess != null) { webServerProcess.Dispose(); webServerProcess = null; }
                if (resumeCameraAfterWebServer) OpenSelected();
            }
        }

        private void AnalyzeCurrentFace()
        {
            var choice = devices.SelectedItem as DeviceChoice;
            if (choice == null || SelectedStream() != StreamKind.Color || currentImage == null)
            { SetStatus("Abre Color RGB de una Kinect antes de analizar rostros."); return; }
            using (var dialog = new SaveFileDialog { Filter = "Informe facial JSON|*.json", FileName = "kinect-face-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".json", DefaultExt = "json" })
            {
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                string imagePath = Path.ChangeExtension(dialog.FileName, ".png");
                using (var image = (Bitmap)currentImage.Clone())
                {
                    StopCamera();
                    int result = FaceAnalyzer.AnalyzeBitmap(image, dialog.FileName, imagePath,
                        choice.Model == "one" ? "Kinect One" : "Kinect 360");
                    if (result != 0) { SetStatus("No se pudo analizar la imagen RGB."); return; }
                }
                var report = (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(File.ReadAllText(dialog.FileName));
                var faces = (object[])report["faces"];
                var previous = currentImage;
                currentImage = new Bitmap(imagePath);
                preview.Image = currentImage;
                if (previous != null) previous.Dispose();
                WriteLog("Rostro: " + faces.Length + " regiones; " + dialog.FileName);
                SetStatus("Análisis facial: " + faces.Length + " regiones. Abre cámara para volver al directo.");
            }
        }

        private async Task CaptureFace3DFromUi(bool personalized = false)
        {
            if (faceRecording || scanRunning) return;
            var choice = devices.SelectedItem as DeviceChoice;
            if (choice == null || choice.Model != "one") { SetStatus("El seguimiento facial HD usa Kinect One."); return; }
            string reportPath;
            using (var dialog = new SaveFileDialog { Filter = "Informe facial JSON|*.json", FileName = "kinect-face3d-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".json", DefaultExt = "json" })
            {
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                reportPath = dialog.FileName;
            }
            string meshPath = Path.ChangeExtension(reportPath, ".ply");
            string progressPath = Path.ChangeExtension(reportPath, ".progress.json");
            bool resumeCamera = wantsCamera;
            StopCamera();
            faceRecording = true;
            SetStatus(personalized ? "Construyendo modelo facial: mira de frente, a izquierda, derecha y arriba..." :
                "Buscando un rostro frente a Kinect One durante 20 segundos...");
            try
            {
                var result = await Task.Run(() =>
                {
                    var start = new System.Diagnostics.ProcessStartInfo {
                        FileName = Application.ExecutablePath,
                        Arguments = (personalized ? "--headscan " : "--face3d ") +
                            "\"" + reportPath + "\" \"" + meshPath + "\" " + (personalized ? "90" : "20"),
                        WorkingDirectory = AppDomain.CurrentDomain.BaseDirectory,
                        UseShellExecute = false, CreateNoWindow = true,
                        RedirectStandardError = true,
                        WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden
                    };
                    using (var process = System.Diagnostics.Process.Start(start))
                    {
                        faceProcess = process;
                        string previous = null;
                        while (!process.WaitForExit(500))
                        {
                            if (!personalized || !File.Exists(progressPath)) continue;
                            try
                            {
                                string progress = File.ReadAllText(progressPath);
                                if (progress == previous) continue;
                                previous = progress;
                                string message = DescribeFaceProgress(progress);
                                if (!IsDisposed && !Disposing)
                                    BeginInvoke((Action)(() => { if (!IsDisposed && !Disposing) SetStatus(message); }));
                            }
                            catch (IOException) { }
                            catch (InvalidOperationException) { }
                            catch (ArgumentException) { }
                        }
                        string error = process.StandardError.ReadToEnd();
                        return Tuple.Create(process.ExitCode, error);
                    }
                });
                if (!File.Exists(reportPath)) throw new InvalidOperationException(result.Item2.Trim());
                var report = (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(File.ReadAllText(reportPath));
                bool hd = Convert.ToBoolean(report["hd_tracked"]);
                bool complete = personalized ? Convert.ToBoolean(report["personalized_model"]) : hd;
                WriteLog("Rostro HD: " + report["frames_with_face"] + " fotogramas; modelo personalizado=" +
                    report["personalized_model"] + "; " + reportPath);
                SetStatus(complete ? "Malla facial HD guardada en " + meshPath : "No se completó el modelo facial; consulta el informe.");
                if (complete && File.Exists(meshPath)) OpenMeshViewer(meshPath);
            }
            catch (Exception ex)
            {
                if (!IsDisposed && !Disposing)
                { WriteLog("Rostro HD: " + ex.GetBaseException().Message); SetStatus("No se pudo completar la captura facial."); }
            }
            finally
            {
                faceProcess = null;
                faceRecording = false;
                if (resumeCamera && !IsDisposed && !Disposing) OpenSelected();
            }
        }

        private static string DescribeFaceProgress(string json)
        {
            var data = (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(json);
            int frames = Convert.ToInt32(data["frames_with_face"]);
            if (Convert.ToBoolean(data["personalized_model"])) return "Modelo facial personalizado completado.";
            if (frames == 0) return "Escaneo facial: colócate frente a la Kinect con cabeza y torso visibles.";
            string status = Convert.ToString(data["collection_status"]);
            string instruction;
            if (status.Contains("LeftViewsNeeded")) instruction = "muestra el perfil izquierdo a la cámara";
            else if (status.Contains("RightViewsNeeded")) instruction = "muestra el perfil derecho a la cámara";
            else if (status.Contains("TiltedUpViewsNeeded")) instruction = "inclina la cabeza hacia arriba";
            else if (status.Contains("FrontViewNeeded")) instruction = "mira de frente a la cámara";
            else instruction = "gira la cabeza lentamente para reunir más vistas";
            return "Escaneo facial: " + frames + " fotogramas; " + instruction + ".";
        }

        private void StopFaceCapture()
        {
            try { var process = faceProcess; if (process != null && !process.HasExited) process.Kill(); }
            catch { }
        }

        private void AnalyzeGestureSession()
        {
            using (var source = new OpenFileDialog { Filter = "Sesión Kinect Hoard|*.khr" })
            {
                if (source.ShowDialog(this) != DialogResult.OK) return;
                using (var report = new SaveFileDialog { Filter = "Eventos JSON|*.json", FileName = "kinect-gestures-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".json", DefaultExt = "json" })
                {
                    if (report.ShowDialog(this) != DialogResult.OK) return;
                    int result = GestureDemo.AnalyzeSession(source.FileName, report.FileName);
                    if (result != 0) { SetStatus("La sesión debe contener esqueletos válidos."); return; }
                    var data = (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(File.ReadAllText(report.FileName));
                    var events = (object[])data["events"];
                    WriteLog("Gestos: " + events.Length + " eventos en " + data["frames"] + " fotogramas; " + report.FileName);
                    SetStatus("Análisis de gestos terminado: " + events.Length + " eventos.");
                }
            }
        }

        private void OpenInteractionGallery()
        {
            if (playback != null && playback.Stream != StreamKind.Skeleton)
            { SetStatus("La galería necesita una sesión de esqueleto."); return; }
            if (interactionGallery != null && !interactionGallery.IsDisposed)
            { interactionGallery.Activate(); return; }
            interactionGallery = new InteractionGallery();
            interactionGallery.FormClosed += (s, e) => interactionGallery = null;
            interactionGallery.Show(this);
            bool wasRunning = wantsCamera;
            bool sessionPlayback = playback != null;
            streams.SelectedIndex = 5;
            if (!wasRunning && !sessionPlayback) OpenSelected();
            WriteLog("Galería: esqueleto y mano derecha; controles por permanencia, ratón o teclado.");
        }

        private void OpenAudioMonitor()
        {
            if (audioMonitor != null && !audioMonitor.IsDisposed) { audioMonitor.Activate(); return; }
            var choice = devices.SelectedItem as DeviceChoice;
            if (choice == null || choice.Model != "one") { SetStatus("El explorador de audio usa Kinect One."); return; }
            bool resumeCamera = wantsCamera;
            StopCamera();
            audioMonitor = new AudioMonitorForm();
            audioMonitor.FormClosed += (s, e) => {
                audioMonitor = null;
                if (resumeCamera && !closing && !IsDisposed && !Disposing) OpenSelected();
            };
            audioMonitor.Show(this);
            SetStatus("Explorador de audio: nivel RMS y dirección del haz en directo.");
        }

        private void StopWebServer(bool restoreCamera)
        {
            if (webServerProcess == null) return;
            try
            {
                if (!webServerProcess.HasExited) { webServerProcess.Kill(); webServerProcess.WaitForExit(3000); }
                WriteLog("Servidor local detenido.");
            }
            catch (Exception ex) { WriteLog("Cierre del servidor: " + ex.GetBaseException().Message); }
            finally { webServerProcess.Dispose(); webServerProcess = null; }
            if (restoreCamera && resumeCameraAfterWebServer && !IsDisposed) OpenSelected();
            resumeCameraAfterWebServer = false;
        }

        private async Task CaptureSpeech()
        {
            if (speechRecording) return;
            var choice = devices.SelectedItem as DeviceChoice;
            if (choice == null || choice.Model != "one") { SetStatus("La demo de voz usa la Kinect One."); return; }
            string wavePath;
            using (var dialog = new SaveFileDialog { Filter = "Audio WAV|*.wav", FileName = "kinect-voice-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".wav", DefaultExt = "wav" })
            {
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                wavePath = dialog.FileName;
            }
            bool resumeCamera = wantsCamera;
            StopCamera();
            speechRecording = true;
            SetStatus("Grabando 10 segundos de la Kinect One para reconocer comandos...");
            WriteLog("Voz: grabación iniciada; gramática speech-commands.txt.");
            try
            {
                var outcome = await Task.Run(() =>
                {
                    int audioStatus = Program.RecordAudio(wavePath, 10);
                    string speechPath = Path.ChangeExtension(wavePath, ".speech.json");
                    int speechStatus = File.Exists(wavePath) && new FileInfo(wavePath).Length > 44
                        ? SpeechCommands.RecognizeFile(wavePath, speechPath, Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "speech-commands.txt")) : 2;
                    return Tuple.Create(audioStatus, speechStatus, speechPath);
                });
                if (outcome.Item2 == 0 && File.Exists(outcome.Item3))
                {
                    var report = (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(File.ReadAllText(outcome.Item3));
                    var recognized = (object[])report["recognized"];
                    foreach (object item in recognized)
                    {
                        var result = (Dictionary<string, object>)item;
                        WriteLog("Voz: " + result["text"] + " · confianza " + Convert.ToDouble(result["confidence"]).ToString("0.00"));
                    }
                    WriteLog("Voz: " + recognized.Length + " comandos; informe " + outcome.Item3);
                    SetStatus(outcome.Item1 == 0 ? "Reconocimiento terminado: " + recognized.Length + " comandos." : "Audio parcial: revisa el WAV y el informe de voz.");
                }
                else SetStatus("No se pudo completar la grabación o el reconocimiento de voz.");
            }
            catch (Exception ex) { WriteLog("Voz: " + ex.GetBaseException().Message); SetStatus("Error en la demo de voz."); }
            finally
            {
                speechRecording = false;
                if (resumeCamera && !IsDisposed) OpenSelected();
            }
        }

        private void StartRecording()
        {
            if (camera == null) { SetStatus("Abre una cámara antes de grabar."); return; }
            using (var dialog = new SaveFileDialog { Filter = "Sesión Kinect Hoard|*.khr", FileName = "kinect-session-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".khr", DefaultExt = "khr" })
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    StopRecording();
                    if (SelectedStream() == StreamKind.ColorDepth) Program.WriteDepthMetadata(dialog.FileName, camera);
                    recording = new SessionWriter(dialog.FileName, SelectedStream());
                    recordingUntil = DateTime.UtcNow.AddSeconds(10);
                    nextRecordedFrame = DateTime.MinValue;
                    WriteLog("Grabando 10 segundos: " + dialog.FileName);
                }
        }

        private void StopRecording()
        {
            if (recording == null) return;
            int count = recording.FrameCount;
            recording.Dispose();
            recording = null;
            WriteLog("Sesión guardada: " + count + " fotogramas.");
        }

        private void OpenRecording(bool startPaused)
        {
            using (var dialog = new OpenFileDialog { Filter = "Sesión Kinect Hoard|*.khr" })
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    StopCamera();
                    try
                    {
                        playback = new SessionReader(dialog.FileName);
                        streams.SelectedIndex = (int)playback.Stream;
                        playbackPaused = startPaused;
                        playbackStep = startPaused;
                        pausePlaybackMenu.Enabled = true;
                        pausePlaybackMenu.Text = startPaused ? "Reanudar reproducción" : "Pausar reproducción";
                        stepPlaybackMenu.Enabled = startPaused;
                        timer.Interval = 200;
                        frameCount = 0;
                        fpsSince = DateTime.UtcNow;
                        timer.Start();
                        WriteLog((startPaused ? "Abierta en pausa: " : "Reproduciendo: ") + dialog.FileName);
                    }
                    catch (Exception ex) { SetStatus("No se pudo abrir la sesión: " + ex.GetBaseException().Message); }
                }
        }

        private void TogglePlaybackPause()
        {
            if (playback == null) return;
            playbackPaused = !playbackPaused;
            playbackStep = false;
            pausePlaybackMenu.Text = playbackPaused ? "Reanudar reproducción" : "Pausar reproducción";
            stepPlaybackMenu.Enabled = playbackPaused;
            SetStatus(playbackPaused ? "Reproducción en pausa. Usa Sesión > Fotograma siguiente." : "Reproduciendo sesión.");
        }

        private void ClosePlayback()
        {
            if (playback == null) return;
            playback.Dispose();
            playback = null;
            playbackPaused = false;
            playbackStep = false;
            pausePlaybackMenu.Text = "Pausar reproducción";
            pausePlaybackMenu.Enabled = false;
            stepPlaybackMenu.Enabled = false;
        }

        private void LoadCapabilities()
        {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            string catalogPath = Path.Combine(root, "docs", "capabilities.json");
            if (!File.Exists(catalogPath))
            {
                root = Path.GetFullPath(Path.Combine(root, "..", "..", "..", ".."));
                catalogPath = Path.Combine(root, "docs", "capabilities.json");
            }
            if (!File.Exists(catalogPath)) { capabilityDetail.Text = "No se encontró docs/capabilities.json."; return; }
            try
            {
                var catalog = (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(File.ReadAllText(catalogPath));
                foreach (object entry in (object[])catalog["capabilities"])
                    capabilityList.Items.Add(new CapabilityChoice((Dictionary<string, object>)entry, root));
                if (capabilityList.Items.Count > 0) capabilityList.SelectedIndex = 0;
            }
            catch (Exception ex) { capabilityDetail.Text = "No se pudo cargar el catálogo: " + ex.Message; }
        }

        private void ShowCapability()
        {
            var choice = capabilityList.SelectedItem as CapabilityChoice;
            if (choice == null) return;
            var item = choice.Data;
            var info = "ONE: " + item["one"] + "    360: " + item["360"] + Environment.NewLine +
                "Salida: " + item["output"] + Environment.NewLine + Environment.NewLine;
            info += "Muestras originales: " + string.Join(", ", Array.ConvertAll((object[])item["toolkit_samples"], x => x.ToString())) + Environment.NewLine;
            info += "Código: " + string.Join(", ", Array.ConvertAll((object[])item["code"], x => x.ToString())) + Environment.NewLine + Environment.NewLine;
            string doc = Path.Combine(choice.Root, item["docs"].ToString().Replace('/', Path.DirectorySeparatorChar));
            capabilityDetail.Text = info + (File.Exists(doc) ? File.ReadAllText(doc) : "No se encontró la documentación.");
        }

        private void SetStatus(string message) { status.Text = message; }
        private StreamKind SelectedStream()
        {
            switch (streams.SelectedIndex)
            {
                case 1: return StreamKind.Depth;
                case 2: return StreamKind.Infrared;
                case 3: return StreamKind.LongExposureInfrared;
                case 4: return StreamKind.BodyIndex;
                case 5: return StreamKind.Skeleton;
                case 6: return StreamKind.BackgroundRemoved;
                case 7: return StreamKind.ColorDepth;
                default: return StreamKind.Color;
            }
        }
        private void WriteLog(string message) { log.AppendText(DateTime.Now.ToString("HH:mm:ss") + "  " + message + Environment.NewLine); }

        private sealed class DeviceChoice
        {
            internal readonly string Model;
            internal readonly string Label;
            internal readonly bool UsbPresent;
            internal DeviceChoice(string model, string label, bool usb) { Model = model; Label = label; UsbPresent = usb; }
            public override string ToString() { return Label; }
        }

        private sealed class CapabilityChoice
        {
            internal readonly Dictionary<string, object> Data;
            internal readonly string Root;
            internal CapabilityChoice(Dictionary<string, object> data, string root) { Data = data; Root = root; }
            public override string ToString() { return Data["title"] + "  [" + Data["one"] + "]"; }
        }
    }
}
