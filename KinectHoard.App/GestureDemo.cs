using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;
using KinectHoard.Core;

namespace KinectHoard.App
{
    internal static class GestureDemo
    {
        internal static int AnalyzeSession(string source, string reportPath)
        {
            try
            {
                using (var session = new SessionReader(source))
                {
                    if (session.Stream != StreamKind.Skeleton) throw new InvalidDataException("La sesión debe contener el flujo Skeleton.");
                    var engine = new GestureEngine();
                    var events = new List<Dictionary<string, object>>();
                    int frames = 0, trackedFrames = 0;
                    CameraFrame frame;
                    while (session.TryRead(out frame))
                    {
                        frames++;
                        if (frame.Bodies != null && frame.Bodies.Length > 0) trackedFrames++;
                        foreach (GestureEvent gesture in engine.Process(frame)) events.Add(Describe(gesture));
                    }
                    Write(reportPath, "session", frames, trackedFrames, events);
                }
                return 0;
            }
            catch (Exception ex) { Console.Error.WriteLine("Gestos: " + ex.GetBaseException().Message); return 1; }
        }

        internal static int Capture(string reportPath, int seconds, string model = "one")
        {
            if (seconds < 1 || seconds > 120) return 1;
            ICameraBackend camera = null;
            var engine = new GestureEngine();
            var events = new List<Dictionary<string, object>>();
            int frames = 0, trackedFrames = 0;
            DateTime end = DateTime.UtcNow.AddSeconds(seconds), lastFrame = DateTime.UtcNow;
            try
            {
                while (DateTime.UtcNow < end)
                {
                    try
                    {
                        if (!UsbDiscovery.IsPresent(model))
                        {
                            if (camera != null) { camera.Dispose(); camera = null; }
                            Thread.Sleep(300); continue;
                        }
                        if (camera == null)
                        {
                            camera = Program.LoadBackend(model);
                            camera.Open(StreamKind.Skeleton);
                            lastFrame = DateTime.UtcNow;
                        }
                        CameraFrame frame;
                        if (camera.TryRead(out frame))
                        {
                            frames++;
                            lastFrame = DateTime.UtcNow;
                            if (frame.Bodies != null && frame.Bodies.Length > 0) trackedFrames++;
                            foreach (GestureEvent gesture in engine.Process(frame)) events.Add(Describe(gesture));
                        }
                        else if ((DateTime.UtcNow - lastFrame).TotalSeconds > 3)
                        { camera.Dispose(); camera = null; }
                    }
                    catch (Exception ex)
                    {
                        Console.Error.WriteLine("Gestos: " + ex.GetBaseException().Message);
                        if (camera != null) { try { camera.Dispose(); } catch { } camera = null; }
                        Thread.Sleep(300);
                    }
                    Thread.Sleep(25);
                }
                Write(reportPath, model == "one" ? "Kinect One" : "Kinect 360", frames, trackedFrames, events);
                return frames > 0 ? 0 : 2;
            }
            catch (Exception ex) { Console.Error.WriteLine("Gestos: " + ex.GetBaseException().Message); return 1; }
            finally { if (camera != null) camera.Dispose(); }
        }

        internal static Dictionary<string, object> Describe(GestureEvent gesture)
        {
            return new Dictionary<string, object> {
                { "tracking_id", gesture.TrackingId.ToString() },
                { "gesture", gesture.Gesture }, { "state", gesture.State },
                { "timestamp_utc", gesture.TimestampUtc.ToString("O") },
                { "confidence", gesture.Confidence }
            };
        }

        private static void Write(string path, string source, int frames, int trackedFrames, List<Dictionary<string, object>> events)
        {
            var report = new Dictionary<string, object> {
                { "format", "KINECT_HOARD_GESTURES_1" }, { "source", source },
                { "frames", frames }, { "tracked_frames", trackedFrames }, { "events", events }
            };
            File.WriteAllText(path, new JavaScriptSerializer().Serialize(report));
        }
    }
}
