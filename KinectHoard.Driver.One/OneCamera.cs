using System;
using System.Collections.Generic;
using KinectHoard.Core;
using Microsoft.Kinect;

namespace KinectHoard.Driver.One
{
    public sealed class OneCamera : MarshalByRefObject, ICameraBackend
    {
        private KinectSensor sensor;
        private ColorFrameReader reader;
        private DepthFrameReader depthReader;
        private InfraredFrameReader infraredReader;
        private LongExposureInfraredFrameReader longInfraredReader;
        private BodyIndexFrameReader bodyIndexReader;
        private BodyFrameReader bodyReader;
        private MultiSourceFrameReader multiReader;
        private Body[] bodies;
        private CameraSpacePoint[] cameraPoints;
        private ColorSpacePoint[] depthToColor;
        private byte[] rawColor;
        private byte[] pixels;
        private ushort[] values;
        private byte[] bodyIndices;
        private StreamKind stream;

        public string Model { get { return "Kinect One / v2"; } }
        public string BackendName { get { return "Microsoft Kinect Runtime 2.0"; } }
        public string Detail { get; private set; }
        public bool IsAvailable
        {
            get
            {
                try
                {
                    var probe = KinectSensor.GetDefault();
                    if (probe == null) { Detail = "El runtime no encuentra el sensor."; return false; }
                    // IsAvailable can lag behind successful Open and actual frames.
                    Detail = probe.IsAvailable ? "Sensor listo (SDK IsAvailable=True)." : "Sensor detectado; SDK IsAvailable=False, se probará la transmisión.";
                    return true;
                }
                catch (Exception ex) { Detail = ex.Message; return false; }
            }
        }

        public void Open(StreamKind requestedStream)
        {
            Close();
            stream = requestedStream;
            sensor = KinectSensor.GetDefault();
            if (sensor == null) throw new InvalidOperationException("Kinect One no encontrada por el runtime.");
            try
            {
                sensor.Open();
                if (stream == StreamKind.Color) reader = sensor.ColorFrameSource.OpenReader();
                else if (stream == StreamKind.Depth) depthReader = sensor.DepthFrameSource.OpenReader();
                else if (stream == StreamKind.Infrared) infraredReader = sensor.InfraredFrameSource.OpenReader();
                else if (stream == StreamKind.LongExposureInfrared) longInfraredReader = sensor.LongExposureInfraredFrameSource.OpenReader();
                else if (stream == StreamKind.BodyIndex) bodyIndexReader = sensor.BodyIndexFrameSource.OpenReader();
                else if (stream == StreamKind.Skeleton) bodyReader = sensor.BodyFrameSource.OpenReader();
                else if (stream == StreamKind.BackgroundRemoved)
                    multiReader = sensor.OpenMultiSourceFrameReader(FrameSourceTypes.Color | FrameSourceTypes.Depth | FrameSourceTypes.BodyIndex);
                else if (stream == StreamKind.ColorDepth)
                    multiReader = sensor.OpenMultiSourceFrameReader(FrameSourceTypes.Color | FrameSourceTypes.Depth);
                else throw new NotSupportedException("Flujo no implementado: " + stream);
                if (reader == null && depthReader == null && infraredReader == null && longInfraredReader == null && bodyIndexReader == null && bodyReader == null && multiReader == null)
                    throw new InvalidOperationException("No se pudo abrir el flujo solicitado.");
            }
            catch { Close(); throw; }
        }

        public bool TryRead(out CameraFrame output)
        {
            output = null;
            if (stream == StreamKind.Depth)
            {
                if (depthReader == null) return false;
                using (var frame = depthReader.AcquireLatestFrame())
                {
                    if (frame == null) return false;
                    int width = frame.FrameDescription.Width, height = frame.FrameDescription.Height;
                    if (values == null || values.Length != width * height) values = new ushort[width * height];
                    frame.CopyFrameDataToArray(values);
                    pixels = FrameRenderer.RenderDepth(values, pixels, frame.DepthMinReliableDistance, frame.DepthMaxReliableDistance);
                    output = new CameraFrame { Width = width, Height = height, Bgra = pixels, Values = values, Kind = stream };
                    return true;
                }
            }
            if (stream == StreamKind.Infrared)
            {
                if (infraredReader == null) return false;
                using (var frame = infraredReader.AcquireLatestFrame())
                {
                    if (frame == null) return false;
                    int width = frame.FrameDescription.Width, height = frame.FrameDescription.Height;
                    if (values == null || values.Length != width * height) values = new ushort[width * height];
                    frame.CopyFrameDataToArray(values);
                    pixels = FrameRenderer.RenderInfrared(values, pixels);
                    output = new CameraFrame { Width = width, Height = height, Bgra = pixels, Values = values, Kind = stream };
                    return true;
                }
            }
            if (stream == StreamKind.LongExposureInfrared)
            {
                if (longInfraredReader == null) return false;
                using (var frame = longInfraredReader.AcquireLatestFrame())
                {
                    if (frame == null) return false;
                    int width = frame.FrameDescription.Width, height = frame.FrameDescription.Height;
                    if (values == null || values.Length != width * height) values = new ushort[width * height];
                    frame.CopyFrameDataToArray(values);
                    pixels = FrameRenderer.RenderInfrared(values, pixels);
                    output = new CameraFrame { Width = width, Height = height, Bgra = pixels, Values = values, Kind = stream };
                    return true;
                }
            }
            if (stream == StreamKind.BodyIndex)
            {
                if (bodyIndexReader == null) return false;
                using (var frame = bodyIndexReader.AcquireLatestFrame())
                {
                    if (frame == null) return false;
                    int width = frame.FrameDescription.Width, height = frame.FrameDescription.Height;
                    int count = width * height;
                    if (bodyIndices == null || bodyIndices.Length != count) bodyIndices = new byte[count];
                    if (values == null || values.Length != count) values = new ushort[count];
                    frame.CopyFrameDataToArray(bodyIndices);
                    for (int i = 0; i < count; i++) values[i] = bodyIndices[i];
                    pixels = FrameRenderer.RenderBodyIndex(values, pixels);
                    output = new CameraFrame { Width = width, Height = height, Bgra = pixels, Values = values, Kind = stream };
                    return true;
                }
            }
            if (stream == StreamKind.Skeleton)
            {
                if (bodyReader == null) return false;
                using (var frame = bodyReader.AcquireLatestFrame())
                {
                    if (frame == null) return false;
                    if (bodies == null) bodies = new Body[sensor.BodyFrameSource.BodyCount];
                    frame.GetAndRefreshBodyData(bodies);
                    var tracked = new List<TrackedBody>();
                    foreach (Body body in bodies)
                    {
                        if (body == null || !body.IsTracked) continue;
                        var joints = new List<BodyJoint>();
                        foreach (var pair in body.Joints)
                        {
                            var point = sensor.CoordinateMapper.MapCameraPointToDepthSpace(pair.Value.Position);
                            joints.Add(new BodyJoint {
                                Name = pair.Key.ToString(), X = pair.Value.Position.X, Y = pair.Value.Position.Y,
                                Z = pair.Value.Position.Z, DepthX = point.X, DepthY = point.Y,
                                TrackingState = (int)pair.Value.TrackingState
                            });
                        }
                        tracked.Add(new TrackedBody { TrackingId = body.TrackingId, Joints = joints.ToArray() });
                    }
                    int width = sensor.DepthFrameSource.FrameDescription.Width;
                    int height = sensor.DepthFrameSource.FrameDescription.Height;
                    pixels = FrameRenderer.RenderSkeleton(tracked.ToArray(), width, height, pixels);
                    output = new CameraFrame { Width = width, Height = height, Bgra = pixels, Bodies = tracked.ToArray(), Kind = stream };
                    return true;
                }
            }
            if (stream == StreamKind.BackgroundRemoved)
            {
                if (multiReader == null) return false;
                var multi = multiReader.AcquireLatestFrame();
                {
                    if (multi == null) return false;
                    using (var color = multi.ColorFrameReference.AcquireFrame())
                    using (var depth = multi.DepthFrameReference.AcquireFrame())
                    using (var index = multi.BodyIndexFrameReference.AcquireFrame())
                    {
                        if (color == null || depth == null || index == null) return false;
                        int colorWidth = color.FrameDescription.Width, colorHeight = color.FrameDescription.Height;
                        int depthWidth = depth.FrameDescription.Width, depthHeight = depth.FrameDescription.Height;
                        int colorCount = colorWidth * colorHeight, depthCount = depthWidth * depthHeight;
                        if (rawColor == null || rawColor.Length != colorCount * 4) rawColor = new byte[colorCount * 4];
                        if (pixels == null || pixels.Length != depthCount * 4) pixels = new byte[depthCount * 4];
                        if (values == null || values.Length != depthCount) values = new ushort[depthCount];
                        if (bodyIndices == null || bodyIndices.Length != depthCount) bodyIndices = new byte[depthCount];
                        if (depthToColor == null || depthToColor.Length != depthCount) depthToColor = new ColorSpacePoint[depthCount];
                        color.CopyConvertedFrameDataToArray(rawColor, ColorImageFormat.Bgra);
                        depth.CopyFrameDataToArray(values);
                        index.CopyFrameDataToArray(bodyIndices);
                        sensor.CoordinateMapper.MapDepthFrameToColorSpace(values, depthToColor);
                        Array.Clear(pixels, 0, pixels.Length);
                        for (int i = 0, j = 0; i < depthCount; i++, j += 4)
                        {
                            if (bodyIndices[i] >= 6) continue;
                            float px = depthToColor[i].X, py = depthToColor[i].Y;
                            if (float.IsNaN(px) || float.IsNaN(py) || float.IsInfinity(px) || float.IsInfinity(py)) continue;
                            int x = (int)(px + 0.5f), y = (int)(py + 0.5f);
                            if (x < 0 || y < 0 || x >= colorWidth || y >= colorHeight) continue;
                            int colorOffset = (y * colorWidth + x) * 4;
                            pixels[j] = rawColor[colorOffset]; pixels[j + 1] = rawColor[colorOffset + 1];
                            pixels[j + 2] = rawColor[colorOffset + 2]; pixels[j + 3] = 255;
                        }
                        output = new CameraFrame { Width = depthWidth, Height = depthHeight, Bgra = pixels, Kind = stream };
                        return true;
                    }
                }
            }
            if (stream == StreamKind.ColorDepth)
            {
                PointCloudFrame cloud;
                return TryReadColorDepth(out output, out cloud);
            }
            if (reader == null) return false;
            using (var frame = reader.AcquireLatestFrame())
            {
                if (frame == null) return false;
                int width = frame.FrameDescription.Width;
                int height = frame.FrameDescription.Height;
                int length = checked(width * height * 4);
                if (pixels == null || pixels.Length != length) pixels = new byte[length];
                frame.CopyConvertedFrameDataToArray(pixels, ColorImageFormat.Bgra);
                output = new CameraFrame { Width = width, Height = height, Bgra = pixels, Kind = stream };
                return true;
            }
        }

        public bool TryReadPointCloud(out PointCloudFrame output)
        {
            output = null;
            if (stream == StreamKind.ColorDepth)
            {
                CameraFrame image;
                return TryReadColorDepth(out image, out output);
            }
            if (depthReader == null || sensor == null) throw new InvalidOperationException("Abre el flujo Depth antes de pedir la nube de puntos.");
            using (var frame = depthReader.AcquireLatestFrame())
            {
                if (frame == null) return false;
                int width = frame.FrameDescription.Width, height = frame.FrameDescription.Height;
                int count = width * height;
                if (values == null || values.Length != count) values = new ushort[count];
                if (cameraPoints == null || cameraPoints.Length != count) cameraPoints = new CameraSpacePoint[count];
                frame.CopyFrameDataToArray(values);
                sensor.CoordinateMapper.MapDepthFrameToCameraSpace(values, cameraPoints);
                var xyz = new float[count * 3];
                for (int i = 0, j = 0; i < count; i++, j += 3)
                {
                    xyz[j] = cameraPoints[i].X;
                    xyz[j + 1] = cameraPoints[i].Y;
                    xyz[j + 2] = values[i] == 0 ? float.NaN : cameraPoints[i].Z;
                }
                output = new PointCloudFrame { Width = width, Height = height, Xyz = xyz };
                return true;
            }
        }

        public DepthIntrinsics GetDepthIntrinsics()
        {
            if (sensor == null || !sensor.IsOpen) throw new InvalidOperationException("Abre primero la Kinect One.");
            var calibration = sensor.CoordinateMapper.GetDepthCameraIntrinsics();
            var description = sensor.DepthFrameSource.FrameDescription;
            var result = new DepthIntrinsics {
                Width = description.Width, Height = description.Height,
                Fx = calibration.FocalLengthX, Fy = calibration.FocalLengthY,
                Cx = calibration.PrincipalPointX, Cy = calibration.PrincipalPointY,
                K2 = calibration.RadialDistortionSecondOrder,
                K4 = calibration.RadialDistortionFourthOrder,
                K6 = calibration.RadialDistortionSixthOrder,
                Method = "Kinect SDK depth camera intrinsics"
            };
            if (result.Fx > 0 && result.Fy > 0) return result;
            if (cameraPoints == null || cameraPoints.Length != result.Width * result.Height)
                throw new InvalidOperationException("La calibración todavía no está disponible; espera un fotograma de profundidad.");
            // Some runtime versions return zero intrinsics. Fit a pinhole model to the
            // calibrated camera-space points from the current physical depth frame.
            double n = 0, sx = 0, sxx = 0, su = 0, sxu = 0, sy = 0, syy = 0, sv = 0, syv = 0;
            for (int i = 0; i < cameraPoints.Length; i += 16)
            {
                var point = cameraPoints[i];
                if (point.Z <= 0 || float.IsNaN(point.Z) || float.IsInfinity(point.Z)) continue;
                double rx = point.X / point.Z, ry = point.Y / point.Z;
                if (double.IsNaN(rx) || double.IsNaN(ry) || double.IsInfinity(rx) || double.IsInfinity(ry)) continue;
                double u = i % result.Width, v = i / result.Width;
                n++; sx += rx; sxx += rx * rx; su += u; sxu += rx * u;
                sy += ry; syy += ry * ry; sv += v; syv += ry * v;
            }
            double dx = n * sxx - sx * sx, dy = n * syy - sy * sy;
            if (n < 100 || Math.Abs(dx) < 1e-9 || Math.Abs(dy) < 1e-9)
                throw new InvalidOperationException("No se pudo inferir la calibración de profundidad.");
            double fx = (n * sxu - sx * su) / dx;
            double slopeY = (n * syv - sy * sv) / dy;
            result.Fx = (float)fx; result.Fy = (float)-slopeY;
            result.Cx = (float)((su - fx * sx) / n);
            result.Cy = (float)((sv - slopeY * sy) / n);
            result.K2 = result.K4 = result.K6 = 0;
            result.Method = "Pinhole fit to SDK MapDepthFrameToCameraSpace (distortion omitted)";
            if (result.Fx <= 0 || result.Fy <= 0) throw new InvalidOperationException("Calibración inferida no válida.");
            return result;
        }

        private bool TryReadColorDepth(out CameraFrame image, out PointCloudFrame cloud)
        {
            image = null; cloud = null;
            if (multiReader == null || sensor == null) return false;
            var multi = multiReader.AcquireLatestFrame();
            {
                if (multi == null) return false;
                using (var color = multi.ColorFrameReference.AcquireFrame())
                using (var depth = multi.DepthFrameReference.AcquireFrame())
                {
                    if (color == null || depth == null) return false;
                    int colorWidth = color.FrameDescription.Width, colorHeight = color.FrameDescription.Height;
                    int width = depth.FrameDescription.Width, height = depth.FrameDescription.Height;
                    int count = width * height;
                    if (rawColor == null || rawColor.Length != colorWidth * colorHeight * 4) rawColor = new byte[colorWidth * colorHeight * 4];
                    if (values == null || values.Length != count) values = new ushort[count];
                    if (depthToColor == null || depthToColor.Length != count) depthToColor = new ColorSpacePoint[count];
                    if (cameraPoints == null || cameraPoints.Length != count) cameraPoints = new CameraSpacePoint[count];
                    color.CopyConvertedFrameDataToArray(rawColor, ColorImageFormat.Bgra);
                    depth.CopyFrameDataToArray(values);
                    sensor.CoordinateMapper.MapDepthFrameToColorSpace(values, depthToColor);
                    sensor.CoordinateMapper.MapDepthFrameToCameraSpace(values, cameraPoints);
                    var xyz = new float[count * 3];
                    var rgb = new byte[count * 3];
                    if (pixels == null || pixels.Length != count * 4) pixels = new byte[count * 4];
                    Array.Clear(pixels, 0, pixels.Length);
                    int validDepth = 0;
                    for (int i = 0, j = 0, k = 0; i < count; i++, j += 3, k += 4)
                    {
                        xyz[j] = cameraPoints[i].X;
                        xyz[j + 1] = cameraPoints[i].Y;
                        xyz[j + 2] = values[i] == 0 ? float.NaN : cameraPoints[i].Z;
                        if (values[i] == 0) continue;
                        validDepth++;
                        float px = depthToColor[i].X, py = depthToColor[i].Y;
                        if (float.IsNaN(px) || float.IsNaN(py) || float.IsInfinity(px) || float.IsInfinity(py)) continue;
                        int x = (int)(px + 0.5f), y = (int)(py + 0.5f);
                        if (x < 0 || y < 0 || x >= colorWidth || y >= colorHeight) continue;
                        int source = (y * colorWidth + x) * 4;
                        byte b = rawColor[source], g = rawColor[source + 1], r = rawColor[source + 2];
                        rgb[j] = r; rgb[j + 1] = g; rgb[j + 2] = b;
                        pixels[k] = b; pixels[k + 1] = g; pixels[k + 2] = r; pixels[k + 3] = 255;
                    }
                    if (validDepth < 1000) return false; // Ignore incomplete startup frames.
                    cloud = new PointCloudFrame { Width = width, Height = height, Xyz = xyz, Rgb = rgb };
                    image = new CameraFrame { Width = width, Height = height, Bgra = pixels, Values = values,
                        Kind = StreamKind.ColorDepth, TimestampUtc = DateTime.UtcNow };
                    return true;
                }
            }
        }

        public void Close()
        {
            if (reader != null) { reader.Dispose(); reader = null; }
            if (depthReader != null) { depthReader.Dispose(); depthReader = null; }
            if (infraredReader != null) { infraredReader.Dispose(); infraredReader = null; }
            if (longInfraredReader != null) { longInfraredReader.Dispose(); longInfraredReader = null; }
            if (bodyIndexReader != null) { bodyIndexReader.Dispose(); bodyIndexReader = null; }
            if (bodyReader != null) { bodyReader.Dispose(); bodyReader = null; }
            if (multiReader != null) { multiReader.Dispose(); multiReader = null; }
            if (sensor != null) { if (sensor.IsOpen) sensor.Close(); sensor = null; }
        }

        public void Dispose() { Close(); }
        public override object InitializeLifetimeService() { return null; }
    }
}
