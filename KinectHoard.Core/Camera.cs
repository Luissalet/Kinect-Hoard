using System;

namespace KinectHoard.Core
{
    public enum StreamKind { Color, Depth, Infrared, LongExposureInfrared, BodyIndex, Skeleton, BackgroundRemoved, ColorDepth }

    // The application speaks this API; each sensor generation has its own backend.
    public interface ICameraBackend : IDisposable
    {
        string Model { get; }
        string BackendName { get; }
        bool IsAvailable { get; }
        string Detail { get; }
        void Open(StreamKind stream);
        bool TryRead(out CameraFrame frame);
        bool TryReadPointCloud(out PointCloudFrame frame);
        DepthIntrinsics GetDepthIntrinsics();
        void SetQualityColor(bool enabled);
        void Close();
    }

    [Serializable]
    public sealed class CameraFrame
    {
        public int Width { get; set; }
        public int Height { get; set; }
        // Four bytes per pixel, blue/green/red/unused, top to bottom.
        public byte[] Bgra { get; set; }
        public StreamKind Kind { get; set; }
        public DateTime TimestampUtc { get; set; }
        // Unmodified millimetres (depth) or 16-bit sensor intensity (infrared).
        public ushort[] Values { get; set; }
        public TrackedBody[] Bodies { get; set; }
        // Optional synchronized SDK person labels: 0-5 body slot, 255 background.
        public byte[] BodyIndices { get; set; }
        // Optional original high-resolution RGB and depth-pixel-to-color mapping.
        // Populated only for quality recording, to avoid copying it for live previews.
        public int FullColorWidth { get; set; }
        public int FullColorHeight { get; set; }
        public byte[] FullColorBgra { get; set; }
        public float[] DepthToColorX { get; set; }
        public float[] DepthToColorY { get; set; }
    }

    [Serializable]
    public sealed class TrackedBody
    {
        public ulong TrackingId { get; set; }
        public int BodyIndex { get; set; }
        public BodyJoint[] Joints { get; set; }
    }

    [Serializable]
    public sealed class BodyJoint
    {
        public string Name { get; set; }
        public float X { get; set; }
        public float Y { get; set; }
        public float Z { get; set; }
        public float DepthX { get; set; }
        public float DepthY { get; set; }
        public int TrackingState { get; set; }
    }

    [Serializable]
    public sealed class PointCloudFrame
    {
        public int Width { get; set; }
        public int Height { get; set; }
        // XYZ in metres, one triplet per depth pixel; invalid samples are NaN.
        public float[] Xyz { get; set; }
        // Optional RGB triplet for each depth pixel, top to bottom.
        public byte[] Rgb { get; set; }
    }

    [Serializable]
    public sealed class DepthIntrinsics
    {
        public int Width { get; set; }
        public int Height { get; set; }
        public float Fx { get; set; }
        public float Fy { get; set; }
        public float Cx { get; set; }
        public float Cy { get; set; }
        public float K2 { get; set; }
        public float K4 { get; set; }
        public float K6 { get; set; }
        public string Method { get; set; }
    }
}
