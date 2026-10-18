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
        private byte[] image;
        private byte[] raw;
        private string frameJson;
        private string lastError;
        private DateTime lastFrameUtc;
        private long frameNumber;

        private CameraStreamServer(StreamKind stream, string model) { this.stream = stream; this.model = model; }

        internal static int Run(int port, StreamKind stream, int seconds, string model = "one")
        {
            if (port < 1024 || port > 65535) throw new ArgumentOutOfRangeException("port");
            if (seconds < 0 || seconds > 86400) throw new ArgumentOutOfRangeException("seconds");
            if (model != "one" && model != "360") throw new ArgumentException("Modelo desconocido", "model");
            var server = new CameraStreamServer(stream, model);
            DateTime until = seconds == 0 ? DateTime.MaxValue : DateTime.UtcNow.AddSeconds(seconds);
            using (var listener = new HttpListener())
            {
                listener.Prefixes.Add("http://127.0.0.1:" + port + "/");
                try { listener.Start(); }
                catch (HttpListenerException ex) { Console.Error.WriteLine("Servidor local: " + ex.Message); return 1; }
                Console.WriteLine("Kinect Hoard: http://127.0.0.1:" + port + "/");
                using (var timer = seconds == 0 ? null : new Timer(state => listener.Stop(), null, seconds * 1000, Timeout.Infinite))
                {
                    var cameraTask = Task.Run(() => server.ReadCamera(until));
                    try
                    {
                        while (DateTime.UtcNow < until && listener.IsListening)
                        {
                            HttpListenerContext context;
                            try { context = listener.GetContext(); }
                            catch (HttpListenerException) when (!listener.IsListening) { break; }
                            server.Respond(context);
                        }
                    }
                    finally { listener.Stop(); cameraTask.Wait(5000); }
                }
            }
            return 0;
        }

        private void ReadCamera(DateTime until)
        {
            ICameraBackend camera = null;
            DateTime lastReceived = DateTime.UtcNow;
            try
            {
                while (DateTime.UtcNow < until)
                {
                    var usb = UsbDiscovery.GetStatus(model);
                    if (!usb.Usable)
                    {
                        if (camera != null) { camera.Dispose(); camera = null; }
                        SetError(usb.Description);
                        Thread.Sleep(500);
                        continue;
                    }
                    try
                    {
                        if (camera == null)
                        {
                            camera = Program.LoadBackend(model);
                            camera.Open(stream);
                            lastReceived = DateTime.UtcNow;
                            SetError(null);
                        }
                        CameraFrame frame;
                        if (camera.TryRead(out frame))
                        {
                            Publish(frame);
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
                    Thread.Sleep(30);
                }
            }
            finally { if (camera != null) camera.Dispose(); }
        }

        private void Publish(CameraFrame frame)
        {
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
            lock (gate)
            {
                image = png;
                raw = values;
                frameJson = metadata;
                lastFrameUtc = DateTime.UtcNow;
                lastError = null;
            }
        }

        private void SetError(string message) { lock (gate) lastError = message; }

        private void Respond(HttpListenerContext context)
        {
            try
            {
                if (context.Request.HttpMethod != "GET") { Send(context, 405, "text/plain; charset=utf-8", Encoding.UTF8.GetBytes("GET required")); return; }
                string path = context.Request.Url.AbsolutePath;
                if (path == "/") { Send(context, 200, "text/html; charset=utf-8", Encoding.UTF8.GetBytes(Page)); return; }
                if (path == "/api/health")
                {
                    string error; DateTime last; long sequence;
                    lock (gate) { error = lastError; last = lastFrameUtc; sequence = frameNumber; }
                    string json = new JavaScriptSerializer().Serialize(new Dictionary<string, object> {
                        { "sensor", model }, { "usb_present", UsbDiscovery.IsPresent(model) },
                        { "stream", stream.ToString() }, { "frames", sequence },
                        { "streaming", last != DateTime.MinValue && (DateTime.UtcNow - last).TotalSeconds < 3 },
                        { "last_frame_utc", last == DateTime.MinValue ? null : last.ToString("O") }, { "error", error }
                    });
                    Send(context, 200, "application/json; charset=utf-8", Encoding.UTF8.GetBytes(json)); return;
                }
                byte[] content; string type;
                lock (gate)
                {
                    content = path == "/frame.png" ? image : path == "/frame.raw" ? raw : path == "/api/frame" && frameJson != null ? Encoding.UTF8.GetBytes(frameJson) : null;
                    type = path == "/frame.png" ? "image/png" : path == "/frame.raw" ? "application/octet-stream" : "application/json; charset=utf-8";
                }
                if (content == null) { Send(context, path == "/frame.png" || path == "/frame.raw" || path == "/api/frame" ? 503 : 404, "text/plain; charset=utf-8", Encoding.UTF8.GetBytes("No frame")); return; }
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
