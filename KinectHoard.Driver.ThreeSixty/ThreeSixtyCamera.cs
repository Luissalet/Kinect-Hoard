using System;
using KinectHoard.Core;
using Microsoft.Kinect;

namespace KinectHoard.Driver.ThreeSixty
{
    public sealed class ThreeSixtyCamera : MarshalByRefObject, ICameraBackend
    {
        private KinectSensor sensor;
        private byte[] pixels;
        private byte[] infraredBytes;
        private ushort[] values;
        private DepthImagePixel[] depthPixels;
        private StreamKind stream;

        public string Model { get { return "Kinect 360 / v1"; } }
        public string BackendName { get { return "Microsoft Kinect Runtime 1.8"; } }
        public string Detail { get; private set; }
        public bool IsAvailable
        {
            get
            {
                try
                {
                    foreach (KinectSensor candidate in KinectSensor.KinectSensors)
                        if (candidate.Status == KinectStatus.Connected)
                        { Detail = "Sensor listo."; return true; }
                    Detail = "El runtime no encuentra un sensor 360 conectado.";
                    return false;
                }
                catch (Exception ex) { Detail = ex.Message; return false; }
            }
        }

        public void Open(StreamKind requestedStream)
        {
            if (requestedStream == StreamKind.LongExposureInfrared || requestedStream == StreamKind.BodyIndex || requestedStream == StreamKind.Skeleton || requestedStream == StreamKind.BackgroundRemoved)
                throw new NotSupportedException("Este flujo es exclusivo de Kinect One.");
            Close();
            stream = requestedStream;
            foreach (KinectSensor candidate in KinectSensor.KinectSensors)
                if (candidate.Status == KinectStatus.Connected) { sensor = candidate; break; }
            if (sensor == null) throw new InvalidOperationException("Kinect 360 no encontrada por el runtime.");
            try
            {
                if (stream == StreamKind.Color) sensor.ColorStream.Enable(ColorImageFormat.RgbResolution640x480Fps30);
                else if (stream == StreamKind.Infrared) sensor.ColorStream.Enable(ColorImageFormat.InfraredResolution640x480Fps30);
                else sensor.DepthStream.Enable(DepthImageFormat.Resolution640x480Fps30);
                sensor.Start();
            }
            catch { Close(); throw; }
        }

        public bool TryRead(out CameraFrame output)
        {
            output = null;
            if (sensor == null) return false;
            if (stream == StreamKind.Depth)
            {
                using (var frame = sensor.DepthStream.OpenNextFrame(0))
                {
                    if (frame == null) return false;
                    int length = frame.Width * frame.Height;
                    if (depthPixels == null || depthPixels.Length != length) depthPixels = new DepthImagePixel[length];
                    if (values == null || values.Length != length) values = new ushort[length];
                    frame.CopyDepthImagePixelDataTo(depthPixels);
                    for (int i = 0; i < length; i++) values[i] = (ushort)Math.Max(0, (int)depthPixels[i].Depth);
                    pixels = FrameRenderer.RenderDepth(values, pixels, frame.MinDepth, frame.MaxDepth);
                    output = new CameraFrame { Width = frame.Width, Height = frame.Height, Bgra = pixels, Values = values, Kind = stream };
                    return true;
                }
            }
            using (var frame = sensor.ColorStream.OpenNextFrame(0))
            {
                if (frame == null) return false;
                int length = checked(frame.Width * frame.Height * frame.BytesPerPixel);
                if (stream == StreamKind.Infrared)
                {
                    if (frame.BytesPerPixel != 2) throw new NotSupportedException("Formato infrarrojo de Kinect 360 inesperado.");
                    if (infraredBytes == null || infraredBytes.Length != length) infraredBytes = new byte[length];
                    if (values == null || values.Length != frame.Width * frame.Height) values = new ushort[frame.Width * frame.Height];
                    frame.CopyPixelDataTo(infraredBytes);
                    Buffer.BlockCopy(infraredBytes, 0, values, 0, length);
                    pixels = FrameRenderer.RenderInfrared(values, pixels);
                    output = new CameraFrame { Width = frame.Width, Height = frame.Height, Bgra = pixels, Values = values, Kind = stream };
                }
                else
                {
                    if (frame.BytesPerPixel != 4) throw new NotSupportedException("Formato RGB de Kinect 360 inesperado.");
                    if (pixels == null || pixels.Length != length) pixels = new byte[length];
                    frame.CopyPixelDataTo(pixels);
                    output = new CameraFrame { Width = frame.Width, Height = frame.Height, Bgra = pixels, Kind = stream };
                }
                return true;
            }
        }

        public void Close()
        {
            if (sensor != null)
            {
                if (sensor.IsRunning) sensor.Stop();
                sensor = null;
            }
        }

        public bool TryReadPointCloud(out PointCloudFrame frame)
        {
            frame = null;
            throw new NotSupportedException("La nube de puntos de Kinect 360 todavía no está implementada.");
        }

        public DepthIntrinsics GetDepthIntrinsics()
        {
            throw new NotSupportedException("La calibración de profundidad de Kinect 360 todavía no está implementada.");
        }

        public void Dispose() { Close(); }
        public override object InitializeLifetimeService() { return null; }
    }
}
