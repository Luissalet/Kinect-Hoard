using System;
using System.Collections.Generic;

namespace KinectHoard.Core
{
    [Serializable]
    public sealed class FacePoint2D
    {
        public string Name { get; set; }
        public float X { get; set; }
        public float Y { get; set; }
    }

    [Serializable]
    public sealed class FaceSnapshot
    {
        public DateTime TimestampUtc { get; set; }
        public ulong TrackingId { get; set; }
        public bool BasicTracked { get; set; }
        public bool HighDefinitionTracked { get; set; }
        public string AlignmentQuality { get; set; }
        public string ModelCollectionStatus { get; set; }
        public string ModelCaptureStatus { get; set; }
        public bool PersonalizedModel { get; set; }
        public int[] ColorBoundingBox { get; set; }
        public FacePoint2D[] ColorPoints { get; set; }
        public Dictionary<string, string> Properties { get; set; }
        // Kinect camera coordinates: metres, X right, Y up, Z away from sensor.
        public float[] HeadPivotMetres { get; set; }
        public float[] OrientationQuaternion { get; set; }
        public float[] VerticesMetres { get; set; }
        public uint[] TriangleIndices { get; set; }
    }

    public interface IFaceBackend : IDisposable
    {
        void Open();
        void StartModelCollection();
        bool TryRead(out FaceSnapshot snapshot);
        void Close();
    }
}
