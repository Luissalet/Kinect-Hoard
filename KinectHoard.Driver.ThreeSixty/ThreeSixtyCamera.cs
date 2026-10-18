using System;
using System.Collections.Generic;
using KinectHoard.Core;
using Microsoft.Kinect;

namespace KinectHoard.Driver.ThreeSixty
{
    public sealed class ThreeSixtyCamera : MarshalByRefObject, ICameraBackend
    {
        public void SetQualityColor(bool enabled) { }
        private KinectSensor sensor;
        private byte[] pixels;
        private byte[] infraredBytes;
        private ushort[] values;
        private DepthImagePixel[] depthPixels;
        private SkeletonPoint[] skeletonPoints;
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
            if (requestedStream == StreamKind.LongExposureInfrared)
                throw new NotSupportedException("La IR de larga exposición es exclusiva de Kinect One.");
            if (requestedStream == StreamKind.BodyIndex || requestedStream == StreamKind.BackgroundRemoved || requestedStream == StreamKind.ColorDepth)
                throw new NotSupportedException("Este flujo aún no está implementado para Kinect 360.");
            Close();
            stream = requestedStream;
            foreach (KinectSensor candidate in KinectSensor.KinectSensors)
                if (candidate.Status == KinectStatus.Connected) { sensor = candidate; break; }
            if (sensor == null) throw new InvalidOperationException("Kinect 360 no encontrada por el runtime.");
            try
            {
                if (stream == StreamKind.Color) sensor.ColorStream.Enable(ColorImageFormat.RgbResolution640x480Fps30);
                else if (stream == StreamKind.Infrared) sensor.ColorStream.Enable(ColorImageFormat.InfraredResolution640x480Fps30);
                else if (stream == StreamKind.Skeleton) sensor.SkeletonStream.Enable();
                else sensor.DepthStream.Enable(DepthImageFormat.Resolution640x480Fps30);
                sensor.Start();
            }
            catch { Close(); throw; }
        }

        public bool TryRead(out CameraFrame output)
        {
            output = null;
            if (sensor == null) return false;
            if (stream == StreamKind.Skeleton)
            {
                using (var frame = sensor.SkeletonStream.OpenNextFrame(0))
                {
                    if (frame == null) return false;
                    var skeletons = new Skeleton[frame.SkeletonArrayLength];
                    frame.CopySkeletonDataTo(skeletons);
                    var bodies = new List<TrackedBody>();
                    foreach (var skeleton in skeletons)
                    {
                        if (skeleton.TrackingState != SkeletonTrackingState.Tracked) continue;
                        var joints = new List<BodyJoint>();
                        foreach (Joint joint in skeleton.Joints)
                        {
                            string name = joint.JointType.ToString();
                            if (name == "HipCenter") name = "SpineBase";
                            else if (name == "Spine") name = "SpineMid";
                            else if (name == "ShoulderCenter") name = "SpineShoulder";
                            var point = sensor.CoordinateMapper.MapSkeletonPointToDepthPoint(
                                joint.Position, DepthImageFormat.Resolution640x480Fps30);
                            var mapped = new BodyJoint {
                                Name = name, X = joint.Position.X, Y = joint.Position.Y, Z = joint.Position.Z,
                                DepthX = point.X, DepthY = point.Y, TrackingState = (int)joint.TrackingState
                            };
                            joints.Add(mapped);
                            if (name == "SpineShoulder")
                                joints.Add(new BodyJoint {
                                    Name = "Neck", X = mapped.X, Y = mapped.Y, Z = mapped.Z,
                                    DepthX = mapped.DepthX, DepthY = mapped.DepthY,
                                    TrackingState = mapped.TrackingState
                                });
                        }
                        bodies.Add(new TrackedBody { TrackingId = unchecked((ulong)(uint)skeleton.TrackingId), Joints = joints.ToArray() });
                    }
                    const int width = 640, height = 480;
                    pixels = FrameRenderer.RenderSkeleton(bodies.ToArray(), width, height, pixels);
                    output = new CameraFrame { Width = width, Height = height, Bgra = pixels,
                        Bodies = bodies.ToArray(), Kind = stream, TimestampUtc = DateTime.UtcNow };
                    return true;
                }
            }
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
                    output = new CameraFrame { Width = frame.Width, Height = frame.Height, Bgra = pixels, Values = values, Kind = stream, TimestampUtc = DateTime.UtcNow };
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
                    output = new CameraFrame { Width = frame.Width, Height = frame.Height, Bgra = pixels, Values = values, Kind = stream, TimestampUtc = DateTime.UtcNow };
                }
                else
                {
                    if (frame.BytesPerPixel != 4) throw new NotSupportedException("Formato RGB de Kinect 360 inesperado.");
                    if (pixels == null || pixels.Length != length) pixels = new byte[length];
                    frame.CopyPixelDataTo(pixels);
                    output = new CameraFrame { Width = frame.Width, Height = frame.Height, Bgra = pixels, Kind = stream, TimestampUtc = DateTime.UtcNow };
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
            if (sensor == null || stream != StreamKind.Depth)
                throw new InvalidOperationException("Abre profundidad de Kinect 360 antes de pedir la nube de puntos.");
            using (var depth = sensor.DepthStream.OpenNextFrame(0))
            {
                if (depth == null) return false;
                int count = depth.Width * depth.Height;
                if (depthPixels == null || depthPixels.Length != count) depthPixels = new DepthImagePixel[count];
                if (skeletonPoints == null || skeletonPoints.Length != count) skeletonPoints = new SkeletonPoint[count];
                depth.CopyDepthImagePixelDataTo(depthPixels);
                sensor.CoordinateMapper.MapDepthFrameToSkeletonFrame(depth.Format, depthPixels, skeletonPoints);
                var xyz = new float[count * 3];
                for (int i = 0, j = 0; i < count; i++, j += 3)
                {
                    var point = skeletonPoints[i];
                    if (depthPixels[i].Depth <= 0 || point.Z <= 0 || float.IsNaN(point.Z) || float.IsInfinity(point.Z))
                    { xyz[j] = xyz[j + 1] = xyz[j + 2] = float.NaN; continue; }
                    xyz[j] = point.X; xyz[j + 1] = point.Y; xyz[j + 2] = point.Z;
                }
                frame = new PointCloudFrame { Width = depth.Width, Height = depth.Height, Xyz = xyz };
                return true;
            }
        }

        public DepthIntrinsics GetDepthIntrinsics()
        {
            const int width = 640, height = 480;
            if (sensor == null || stream != StreamKind.Depth || skeletonPoints == null || skeletonPoints.Length != width * height)
                throw new InvalidOperationException("Abre profundidad y espera una nube de puntos antes de pedir la calibración.");
            double n = 0, sx = 0, sxx = 0, su = 0, sxu = 0, sy = 0, syy = 0, sv = 0, syv = 0;
            for (int i = 0; i < skeletonPoints.Length; i += 16)
            {
                var point = skeletonPoints[i];
                if (point.Z <= 0 || float.IsNaN(point.Z) || float.IsInfinity(point.Z)) continue;
                double rx = point.X / point.Z, ry = point.Y / point.Z;
                if (double.IsNaN(rx) || double.IsNaN(ry) || double.IsInfinity(rx) || double.IsInfinity(ry)) continue;
                double u = i % width, v = i / width;
                n++; sx += rx; sxx += rx * rx; su += u; sxu += rx * u;
                sy += ry; syy += ry * ry; sv += v; syv += ry * v;
            }
            double dx = n * sxx - sx * sx, dy = n * syy - sy * sy;
            if (n < 100 || Math.Abs(dx) < 1e-9 || Math.Abs(dy) < 1e-9)
                throw new InvalidOperationException("No se pudo inferir la calibración de profundidad 360.");
            double fx = (n * sxu - sx * su) / dx;
            double slopeY = (n * syv - sy * sv) / dy;
            if (fx <= 0 || slopeY >= 0) throw new InvalidOperationException("Calibración 360 no válida.");
            return new DepthIntrinsics {
                Width = width, Height = height, Fx = (float)fx, Fy = (float)-slopeY,
                Cx = (float)((su - fx * sx) / n), Cy = (float)((sv - slopeY * sy) / n),
                Method = "Pinhole fit to SDK 1.8 MapDepthFrameToSkeletonFrame (distortion omitted)"
            };
        }

        public void Dispose() { Close(); }
        public override object InitializeLifetimeService() { return null; }
    }
}
