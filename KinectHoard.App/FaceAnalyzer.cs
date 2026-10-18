using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;
using KinectHoard.Core;
using OpenCvSharp;

namespace KinectHoard.App
{
    internal static class FaceAnalyzer
    {
        private static readonly string ModelPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "models", "haarcascade_frontalface_default.xml");

        internal static int Capture(string reportPath, string imagePath)
        {
            try
            {
                using (var camera = Program.LoadBackend("one"))
                {
                    camera.Open(StreamKind.Color);
                    DateTime deadline = DateTime.UtcNow.AddSeconds(12);
                    while (DateTime.UtcNow < deadline)
                    {
                        CameraFrame frame;
                        if (camera.TryRead(out frame))
                        {
                            using (var bitmap = FrameImage.Create(frame)) return Analyze(bitmap, reportPath, imagePath, "Kinect One");
                        }
                        Thread.Sleep(30);
                    }
                }
                Console.Error.WriteLine("Rostro: no llegó una imagen RGB de la Kinect One.");
                return 2;
            }
            catch (Exception ex) { Console.Error.WriteLine("Rostro: " + ex.GetBaseException().Message); return 1; }
        }

        internal static int AnalyzeFile(string inputPath, string reportPath, string imagePath)
        {
            try { using (var bitmap = new Bitmap(inputPath)) return Analyze(bitmap, reportPath, imagePath, inputPath); }
            catch (Exception ex) { Console.Error.WriteLine("Rostro: " + ex.GetBaseException().Message); return 1; }
        }

        internal static int AnalyzeBitmap(Bitmap bitmap, string reportPath, string imagePath)
        {
            try { return Analyze(bitmap, reportPath, imagePath, "Kinect One"); }
            catch (Exception ex) { Console.Error.WriteLine("Rostro: " + ex.GetBaseException().Message); return 1; }
        }

        private static int Analyze(Bitmap bitmap, string reportPath, string imagePath, string source)
        {
            if (!File.Exists(ModelPath)) throw new FileNotFoundException("Falta el detector de rostro.", ModelPath);
            byte[] image;
            using (var memory = new MemoryStream()) { bitmap.Save(memory, ImageFormat.Png); image = memory.ToArray(); }
            var boxes = new List<Dictionary<string, object>>();
            using (var color = Cv2.ImDecode(image, ImreadModes.Color))
            using (var grayscale = new Mat())
            using (var reduced = new Mat())
            using (var cascade = new CascadeClassifier(ModelPath))
            {
                if (color.Empty() || cascade.Empty()) throw new InvalidDataException("No se pudo cargar la imagen o el detector facial.");
                Cv2.CvtColor(color, grayscale, ColorConversionCodes.BGR2GRAY);
                double scale = Math.Min(1.0, 960.0 / bitmap.Width);
                if (scale < 1) Cv2.Resize(grayscale, reduced, new OpenCvSharp.Size(), scale, scale, InterpolationFlags.Area);
                else grayscale.CopyTo(reduced);
                Cv2.EqualizeHist(reduced, reduced);
                OpenCvSharp.Rect[] faces = cascade.DetectMultiScale(reduced, 1.1, 7, HaarDetectionTypes.ScaleImage, new OpenCvSharp.Size(24, 24));
                using (var drawing = Graphics.FromImage(bitmap))
                using (var pen = new Pen(Color.LimeGreen, Math.Max(2, bitmap.Width / 400)))
                    foreach (var face in faces)
                    {
                        int x = (int)Math.Round(face.X / scale), y = (int)Math.Round(face.Y / scale);
                        int width = (int)Math.Round(face.Width / scale), height = (int)Math.Round(face.Height / scale);
                        boxes.Add(new Dictionary<string, object> { { "x", x }, { "y", y }, { "width", width }, { "height", height } });
                        drawing.DrawRectangle(pen, x, y, width, height);
                    }
            }
            bitmap.Save(imagePath, ImageFormat.Png);
            var report = new Dictionary<string, object> {
                { "format", "KINECT_HOARD_FACE_1" }, { "source", source },
                { "width", bitmap.Width }, { "height", bitmap.Height },
                { "coordinate_space", "color_pixels" }, { "faces", boxes },
                { "detector", "OpenCV Haar frontal face" }, { "timestamp_utc", DateTime.UtcNow.ToString("O") }
            };
            File.WriteAllText(reportPath, new JavaScriptSerializer().Serialize(report));
            return 0;
        }
    }
}
