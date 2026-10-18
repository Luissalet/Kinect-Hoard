using System;
using System.Collections.Generic;
using KinectHoard.Core;
using Microsoft.Kinect;
using Microsoft.Kinect.Face;

namespace KinectHoard.Driver.One
{
    public sealed class OneFace : MarshalByRefObject, IFaceBackend
    {
        private KinectSensor sensor;
        private BodyFrameReader bodyReader;
        private FaceFrameSource basicSource;
        private FaceFrameReader basicReader;
        private HighDefinitionFaceFrameSource hdSource;
        private HighDefinitionFaceFrameReader hdReader;
        private FaceAlignment alignment;
        private Body[] bodies;
        private FaceModelBuilder modelBuilder;
        private FaceModel personalizedModel;
        private FaceModel pendingModel;
        private string modelError;
        private readonly object modelLock = new object();

        public void Open()
        {
            Close();
            sensor = KinectSensor.GetDefault();
            if (sensor == null) throw new InvalidOperationException("Kinect One no encontrada.");
            try
            {
                sensor.Open();
                bodyReader = sensor.BodyFrameSource.OpenReader();
                var features = FaceFrameFeatures.BoundingBoxInColorSpace |
                    FaceFrameFeatures.PointsInColorSpace | FaceFrameFeatures.RotationOrientation |
                    FaceFrameFeatures.Happy | FaceFrameFeatures.RightEyeClosed |
                    FaceFrameFeatures.LeftEyeClosed | FaceFrameFeatures.MouthOpen |
                    FaceFrameFeatures.MouthMoved | FaceFrameFeatures.LookingAway |
                    FaceFrameFeatures.Glasses | FaceFrameFeatures.FaceEngagement;
                basicSource = new FaceFrameSource(sensor, 0, features);
                basicReader = basicSource.OpenReader();
                hdSource = new HighDefinitionFaceFrameSource(sensor);
                hdReader = hdSource.OpenReader();
                alignment = new FaceAlignment();
                bodies = new Body[sensor.BodyFrameSource.BodyCount];
            }
            catch { Close(); throw; }
        }

        public void StartModelCollection()
        {
            if (hdSource == null) throw new InvalidOperationException("Abre la cámara facial antes de iniciar el escaneo.");
            if (modelBuilder != null) return;
            modelBuilder = hdSource.OpenModelBuilder(FaceModelBuilderAttributes.None);
            modelBuilder.CollectionCompleted += OnModelCollectionCompleted;
            modelBuilder.BeginFaceDataCollection();
        }

        private void OnModelCollectionCompleted(object sender, FaceModelBuilderCollectionCompletedEventArgs args)
        {
            try
            {
                using (var data = args.ModelData)
                {
                    var model = data.ProduceFaceModel();
                    lock (modelLock) pendingModel = model;
                }
            }
            catch (Exception ex) { lock (modelLock) modelError = ex.GetBaseException().Message; }
        }

        public bool TryRead(out FaceSnapshot snapshot)
        {
            snapshot = null;
            if (sensor == null || bodyReader == null) return false;
            lock (modelLock)
                if (pendingModel != null)
                {
                    personalizedModel = pendingModel;
                    pendingModel = null;
                }
            using (var frame = bodyReader.AcquireLatestFrame())
            {
                if (frame != null)
                {
                    frame.GetAndRefreshBodyData(bodies);
                    Body nearest = null;
                    float distance = float.PositiveInfinity;
                    foreach (Body body in bodies)
                        if (body != null && body.IsTracked && body.Joints[JointType.Head].TrackingState != TrackingState.NotTracked)
                        {
                            float z = body.Joints[JointType.Head].Position.Z;
                            if (z > 0 && z < distance) { nearest = body; distance = z; }
                        }
                    if (nearest != null)
                    {
                        basicSource.TrackingId = nearest.TrackingId;
                        hdSource.TrackingId = nearest.TrackingId;
                    }
                }
            }
            using (var face = basicReader.AcquireLatestFrame())
            using (var hd = hdReader.AcquireLatestFrame())
            {
                var result = face == null ? null : face.FaceFrameResult;
                if (result == null && (hd == null || !hd.IsFaceTracked)) return false;
                snapshot = new FaceSnapshot { TimestampUtc = DateTime.UtcNow, ColorPoints = new FacePoint2D[0],
                    Properties = new Dictionary<string, string>() };
                if (modelBuilder != null)
                {
                    snapshot.ModelCollectionStatus = modelBuilder.CollectionStatus.ToString();
                    snapshot.ModelCaptureStatus = modelError ?? modelBuilder.CaptureStatus.ToString();
                    snapshot.PersonalizedModel = personalizedModel != null;
                }
                if (result != null)
                {
                    snapshot.TrackingId = face.TrackingId;
                    snapshot.BasicTracked = true;
                    var box = result.FaceBoundingBoxInColorSpace;
                    snapshot.ColorBoundingBox = new[] { box.Left, box.Top, box.Right, box.Bottom };
                    var points = new List<FacePoint2D>();
                    foreach (var item in result.FacePointsInColorSpace)
                        points.Add(new FacePoint2D { Name = item.Key.ToString(), X = item.Value.X, Y = item.Value.Y });
                    snapshot.ColorPoints = points.ToArray();
                    foreach (var item in result.FaceProperties)
                        snapshot.Properties[item.Key.ToString()] = item.Value.ToString();
                    var orientation = result.FaceRotationQuaternion;
                    snapshot.OrientationQuaternion = new[] { orientation.X, orientation.Y, orientation.Z, orientation.W };
                }
                if (hd != null && hd.IsFaceTracked)
                {
                    hd.GetAndRefreshFaceAlignmentResult(alignment);
                    snapshot.TrackingId = hd.TrackingId;
                    snapshot.HighDefinitionTracked = true;
                    snapshot.AlignmentQuality = alignment.Quality.ToString();
                    var pivot = alignment.HeadPivotPoint;
                    snapshot.HeadPivotMetres = new[] { pivot.X, pivot.Y, pivot.Z };
                    var rotation = alignment.FaceOrientation;
                    snapshot.OrientationQuaternion = new[] { rotation.X, rotation.Y, rotation.Z, rotation.W };
                    var model = personalizedModel ?? hd.FaceModel ?? hdSource.FaceModel;
                    if (model != null)
                    {
                        var vertices = model.CalculateVerticesForAlignment(alignment);
                        snapshot.VerticesMetres = new float[vertices.Count * 3];
                        for (int i = 0, j = 0; i < vertices.Count; i++, j += 3)
                        {
                            snapshot.VerticesMetres[j] = vertices[i].X;
                            snapshot.VerticesMetres[j + 1] = vertices[i].Y;
                            snapshot.VerticesMetres[j + 2] = vertices[i].Z;
                        }
                        snapshot.TriangleIndices = new uint[model.TriangleIndices.Count];
                        for (int i = 0; i < snapshot.TriangleIndices.Length; i++)
                            snapshot.TriangleIndices[i] = model.TriangleIndices[i];
                    }
                }
                return true;
            }
        }

        public void Close()
        {
            if (modelBuilder != null) { modelBuilder.CollectionCompleted -= OnModelCollectionCompleted; modelBuilder.Dispose(); modelBuilder = null; }
            personalizedModel = null;
            pendingModel = null;
            modelError = null;
            if (basicReader != null) { basicReader.Dispose(); basicReader = null; }
            if (basicSource != null) { basicSource.Dispose(); basicSource = null; }
            if (hdReader != null) { hdReader.Dispose(); hdReader = null; }
            hdSource = null;
            alignment = null;
            if (bodyReader != null) { bodyReader.Dispose(); bodyReader = null; }
            if (sensor != null) { if (sensor.IsOpen) sensor.Close(); sensor = null; }
        }

        public void Dispose() { Close(); }
        public override object InitializeLifetimeService() { return null; }
    }
}
