using System;
using System.Collections.Generic;
using System.Drawing.Imaging;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using KinectHoard.Core;

namespace KinectHoard.App
{
    internal sealed class CameraStreamServer
    {
        private readonly object gate = new object();
        private readonly StreamKind stream;
        private readonly string model;
        private readonly bool quality;
        private readonly FusionScanner scanner;
        private volatile bool stopRequested;
        private volatile bool usbPresent;
        private byte[] image;
        private byte[] raw;
        private byte[] rgbd;
        private string frameJson;
        private byte[] avatar;
        private string lastError;
        private DateTime lastFrameUtc;
        private long frameNumber;
        private int bodyCount;

        private CameraStreamServer(StreamKind stream, string model, bool quality, FusionScanner scanner) { this.stream = stream; this.model = model; this.quality = quality; this.scanner = scanner; }

        internal static int Run(int port, StreamKind stream, int seconds, string model = "one", bool quality = false, FusionScanner scanner = null)
        {
            if (port < 1024 || port > 65535) throw new ArgumentOutOfRangeException("port");
            if (seconds < 0 || seconds > 86400) throw new ArgumentOutOfRangeException("seconds");
            if (model != "one" && model != "360") throw new ArgumentException("Modelo desconocido", "model");
            var server = new CameraStreamServer(stream, model, quality, scanner);
            DateTime until = seconds == 0 ? DateTime.MaxValue : DateTime.UtcNow.AddSeconds(seconds);
            using (var listener = new HttpListener())
            {
                listener.Prefixes.Add("http://127.0.0.1:" + port + "/");
                try { listener.Start(); }
                catch (HttpListenerException ex) { scanner?.Dispose(); Console.Error.WriteLine("Servidor local: " + ex.Message); return 1; }
                Console.WriteLine("Kinect Hoard: http://127.0.0.1:" + port + "/");
                using (var timer = seconds == 0 ? null : new Timer(state => listener.Stop(), null, seconds * 1000, Timeout.Infinite))
                {
                    var cameraTask = Task.Run(() => server.ReadCamera(until));
                    try
                    {
                        while (DateTime.UtcNow < until && listener.IsListening && !server.stopRequested)
                        {
                            HttpListenerContext context;
                            try { context = listener.GetContext(); }
                            catch (HttpListenerException) when (!listener.IsListening) { break; }
                            server.Respond(context);
                        }
                    }
                    finally { server.stopRequested = true; listener.Stop(); if (scanner == null) cameraTask.Wait(5000); else cameraTask.GetAwaiter().GetResult(); }
                }
            }
            return 0;
        }

        private void ReadCamera(DateTime until)
        {
            ICameraBackend camera = null;
            DateTime lastReceived = DateTime.UtcNow;
            DateTime nextProbe = DateTime.MinValue;
            bool usable = false;
            try
            {
                while (DateTime.UtcNow < until && !stopRequested)
                {
                    if (DateTime.UtcNow >= nextProbe)
                    {
                        var usb = UsbDiscovery.GetStatus(model);
                        usable = usb.Usable;
                        usbPresent = usb.Detected;
                        if (!usable) SetError(usb.Description);
                        nextProbe = DateTime.UtcNow.AddSeconds(1);
                    }
                    if (!usable)
                    {
                        if (camera != null) { camera.Dispose(); camera = null; }
                        Thread.Sleep(500);
                        continue;
                    }
                    try
                    {
                        if (camera == null)
                        {
                            camera = Program.LoadBackend(model);
                            camera.Open(stream);
                            camera.SetQualityColor(quality);
                            lastReceived = DateTime.UtcNow;
                            SetError(null);
                        }
                        CameraFrame frame;
                        if (camera.TryRead(out frame))
                        {
                            if (scanner == null) Publish(frame, stream == StreamKind.ColorDepth ? camera.GetDepthIntrinsics() : null);
                            else
                            {
                                scanner.Process(frame, camera.GetDepthIntrinsics());
                                lock (gate) { frameNumber++; lastFrameUtc = DateTime.UtcNow; lastError = null; }
                            }
                            lastReceived = DateTime.UtcNow;
                        }
                        else if ((DateTime.UtcNow - lastReceived).TotalSeconds > 3)
                        {
                            SetError("Tres segundos sin fotogramas; reabriendo el lector.");
                            camera.Dispose(); camera = null;
                        }
                    }
                    catch (Exception ex)
                    {
                        SetError(ex.GetBaseException().Message);
                        if (camera != null) { try { camera.Dispose(); } catch { } camera = null; }
                        Thread.Sleep(300);
                    }
                    Thread.Sleep(scanner == null ? 30 : 1);
                }
            }
            finally { if (camera != null) camera.Dispose(); if (scanner != null) scanner.Dispose(); }
        }

        private void Publish(CameraFrame frame, DepthIntrinsics intrinsics)
        {
            byte[] avatarPng = null;
            if (frame.Bodies != null)
                using (var bitmap = AvatarRenderer.Create(frame.Bodies, frame.Width, frame.Height))
                using (var output = new MemoryStream()) { bitmap.Save(output, ImageFormat.Png); avatarPng = output.ToArray(); }
            byte[] png;
            using (var bitmap = FrameImage.Create(frame))
            using (var output = new MemoryStream())
            {
                bitmap.Save(output, ImageFormat.Png);
                png = output.ToArray();
            }
            byte[] values = null;
            if (frame.Values != null)
            {
                values = new byte[frame.Values.Length * sizeof(ushort)];
                Buffer.BlockCopy(frame.Values, 0, values, 0, values.Length);
            }
            long sequence = Interlocked.Increment(ref frameNumber);
            string metadata = new JavaScriptSerializer().Serialize(new Dictionary<string, object> {
                { "sequence", sequence }, { "stream", stream.ToString() },
                { "width", frame.Width }, { "height", frame.Height },
                { "timestamp_utc", DateTime.UtcNow.ToString("O") },
                { "raw_format", values == null ? null : "uint16_le" },
                { "raw_unit", stream == StreamKind.Depth || stream == StreamKind.ColorDepth ? "millimetres" : stream == StreamKind.BodyIndex ? "body_index" : "sensor_intensity" },
                { "bodies", frame.Bodies }
            });
            byte[] snapshot = null;
            if (intrinsics != null && values != null)
            {
                var header = new Dictionary<string, object> {
                    { "format", "KINECT_HOARD_LIVE_RGBD_1" }, { "sequence", sequence },
                    { "timestamp_ticks_utc", frame.TimestampUtc.Ticks }, { "model", model },
                    { "width", frame.Width }, { "height", frame.Height },
                    { "bgra_bytes", frame.Bgra.Length }, { "depth_bytes", values.Length },
                    { "full_color_width", frame.FullColorWidth }, { "full_color_height", frame.FullColorHeight },
                    { "full_color_bytes", frame.FullColorBgra == null ? 0 : frame.FullColorBgra.Length },
                    { "map_count", frame.DepthToColorX == null ? 0 : frame.DepthToColorX.Length },
                    { "body_index_bytes", frame.BodyIndices == null ? 0 : frame.BodyIndices.Length },
                    { "bodies", frame.Bodies },
                    { "image_orientation", model == "one" ? "mirrored_x" : "camera" },
                    { "intrinsics", new Dictionary<string, object> {
                        { "width", intrinsics.Width }, { "height", intrinsics.Height },
                        { "fx", intrinsics.Fx }, { "fy", intrinsics.Fy },
                        { "cx", intrinsics.Cx }, { "cy", intrinsics.Cy }, { "method", intrinsics.Method }
                    } }
                };
                byte[] headerBytes = Encoding.UTF8.GetBytes(new JavaScriptSerializer().Serialize(header));
                using (var memory = new MemoryStream())
                using (var writer = new BinaryWriter(memory))
                {
                    writer.Write(Encoding.ASCII.GetBytes("KHRGBD1\n"));
                    writer.Write(headerBytes.Length); writer.Write(headerBytes);
                    writer.Write(frame.Bgra); writer.Write(values);
                    if (frame.FullColorBgra != null) writer.Write(frame.FullColorBgra);
                    if (frame.DepthToColorX != null)
                    {
                        float[] coordinates = new float[frame.DepthToColorX.Length * 2];
                        for (int i = 0; i < frame.DepthToColorX.Length; i++)
                        {
                            coordinates[i * 2] = frame.DepthToColorX[i];
                            coordinates[i * 2 + 1] = frame.DepthToColorY[i];
                        }
                        byte[] mapping = new byte[coordinates.Length * sizeof(float)];
                        Buffer.BlockCopy(coordinates, 0, mapping, 0, mapping.Length);
                        writer.Write(mapping);
                    }
                    if (frame.BodyIndices != null) writer.Write(frame.BodyIndices);
                    snapshot = memory.ToArray();
                }
            }
            lock (gate)
            {
                image = png;
                avatar = avatarPng;
                bodyCount = frame.Bodies == null ? 0 : frame.Bodies.Length;
                raw = values;
                rgbd = snapshot;
                frameJson = metadata;
                lastFrameUtc = DateTime.UtcNow;
                lastError = null;
            }
        }

        private void SetError(string message) { lock (gate) lastError = message; if (message != null && scanner != null) scanner.SetError(message); }

        private void Respond(HttpListenerContext context)
        {
            try
            {
                if (scanner != null && context.Request.Url.AbsolutePath.StartsWith("/api/scan/"))
                {
                    string action = context.Request.Url.AbsolutePath.Substring("/api/scan/".Length);
                    if (action == "close" && context.Request.HttpMethod == "POST")
                    { stopRequested = true; Send(context, 202, "application/json", Encoding.UTF8.GetBytes("{\"closing\":true}")); return; }
                    if (action == "status" && context.Request.HttpMethod == "GET")
                    { Send(context, 200, "application/json; charset=utf-8", Encoding.UTF8.GetBytes(new JavaScriptSerializer().Serialize(scanner.Status()))); return; }
                    if ((action == "preview.png" || action == "surface.png") && context.Request.HttpMethod == "GET")
                    {
                        var png = scanner.Preview(action == "surface.png");
                        context.Response.Headers["Cache-Control"] = "no-store";
                        Send(context, png == null ? 503 : 200, "image/png", png ?? new byte[0]); return;
                    }
                    if (context.Request.HttpMethod == "POST")
                    {
                        double x = 0, y = 0;
                        double.TryParse(context.Request.QueryString["x"], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out x);
                        double.TryParse(context.Request.QueryString["y"], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out y);
                        try { scanner.Command(action, x, y); }
                        catch (ArgumentException ex) { Send(context, 400, "text/plain; charset=utf-8", Encoding.UTF8.GetBytes(ex.Message)); return; }
                        Send(context, 202, "application/json", Encoding.UTF8.GetBytes("{\"queued\":true}")); return;
                    }
                    Send(context, 404, "text/plain", Encoding.UTF8.GetBytes("Unknown scanner endpoint")); return;
                }
                if (context.Request.Url.AbsolutePath == "/api/stop" && context.Request.HttpMethod == "POST")
                {
                    stopRequested = true;
                    Send(context, 200, "application/json", Encoding.UTF8.GetBytes("{\"stopping\":true}")); return;
                }
                if (context.Request.HttpMethod != "GET") { Send(context, 405, "text/plain; charset=utf-8", Encoding.UTF8.GetBytes("GET required")); return; }
                string path = context.Request.Url.AbsolutePath;
                if (path == "/") { Send(context, 200, "text/html; charset=utf-8", Encoding.UTF8.GetBytes(Page)); return; }
                if (path == "/api/health")
                {
                    string error; DateTime last; long sequence; int tracked;
                    lock (gate) { error = lastError; last = lastFrameUtc; sequence = frameNumber; tracked = bodyCount; }
                    string json = new JavaScriptSerializer().Serialize(new Dictionary<string, object> {
                        { "service", "kinect-hoard-camera" }, { "sensor", model }, { "usb_present", usbPresent },
                        { "stream", stream.ToString() }, { "frames", sequence },
                        { "body_tracking", model == "one" && (stream == StreamKind.Skeleton || stream == StreamKind.ColorDepth) }, { "bodies_count", tracked },
                        { "streaming", last != DateTime.MinValue && (DateTime.UtcNow - last).TotalSeconds < 3 },
                        { "last_frame_utc", last == DateTime.MinValue ? null : last.ToString("O") }, { "error", error }
                    });
                    Send(context, 200, "application/json; charset=utf-8", Encoding.UTF8.GetBytes(json)); return;
                }
                byte[] content; string type;
                lock (gate)
                {
                    content = path == "/frame.png" ? image : path == "/avatar.png" ? avatar : path == "/frame.raw" ? raw : path == "/api/rgbd" ? rgbd : path == "/api/frame" && frameJson != null ? Encoding.UTF8.GetBytes(frameJson) : null;
                    type = path == "/frame.png" || path == "/avatar.png" ? "image/png" : path == "/frame.raw" || path == "/api/rgbd" ? "application/octet-stream" : "application/json; charset=utf-8";
                }
                if (content == null) { Send(context, path == "/frame.png" || path == "/frame.raw" || path == "/api/frame" || path == "/api/rgbd" ? 503 : 404, "text/plain; charset=utf-8", Encoding.UTF8.GetBytes("No frame")); return; }
                context.Response.Headers["Cache-Control"] = "no-store";
                Send(context, 200, type, content);
            }
            catch (Exception ex)
            {
                SetError("HTTP: " + ex.GetBaseException().Message);
                try { context.Response.Abort(); } catch { }
            }
        }

        private static void Send(HttpListenerContext context, int status, string type, byte[] content)
        {
            context.Response.StatusCode = status;
            context.Response.ContentType = type;
            context.Response.ContentLength64 = content.Length;
            context.Response.OutputStream.Write(content, 0, content.Length);
            context.Response.Close();
        }

        private const string Page = "<!doctype html><html lang=es><meta charset=utf-8><title>Kinect Hoard</title>" +
            "<style>body{font:16px sans-serif;background:#171b20;color:#eee;margin:2rem}img{max-width:100%;background:#000}pre{white-space:pre-wrap}</style>" +
            "<h1>Kinect Hoard · One</h1><p>Vista local del sensor. API: /api/health, /api/frame, /frame.png, /frame.raw.</p>" +
            "<img id=frame alt='Esperando imagen'><pre id=health></pre><script>setInterval(async()=>{try{let h=await fetch('/api/health');" +
            "document.getElementById('health').textContent=JSON.stringify(await h.json(),null,2);" +
            "document.getElementById('frame').src='/frame.png?t='+Date.now()}catch(e){}},300)</script></html>";
    }
}
