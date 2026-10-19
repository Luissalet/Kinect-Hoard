using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using System.Runtime.InteropServices;
using KinectHoard.Core;
using Microsoft.Kinect.Fusion;
using OpenCvSharp;
using OpenCvSharp.Features2D;
using FusionMatrix = Microsoft.Kinect.Fusion.Matrix4;

namespace KinectHoard.App
{
    // RGB features propose a pose; depth on both sides verifies it in metres.
    // Saved views also allow recovery when a previously seen side returns.
    internal sealed class RgbdFeatureTracker : IDisposable
    {
        internal sealed class View : IDisposable
        {
            internal KeyPoint[] Keys;
            internal Mat Descriptors = new Mat();
            internal ushort[] Depth;
            internal FusionMatrix Pose;
            internal int Width, Height;
            public void Dispose() { Descriptors.Dispose(); }
        }
        private readonly SIFT detector = SIFT.Create(1600, 3, .015, 10, 1.6);
        private readonly BFMatcher matcher = new BFMatcher(NormTypes.L2, false);
        private readonly List<View> anchors = new List<View>();
        private View previous;
        private int accepted;
        private readonly Random random = new Random(19);
        internal int Matches { get; private set; }
        internal double ErrorMetres { get; private set; }

        internal View Describe(CameraFrame frame, ushort[] depth)
        {
            var view = new View { Depth = depth, Width = frame.Width, Height = frame.Height };
            using (var bgra = new Mat(frame.Height, frame.Width, MatType.CV_8UC4))
            using (var gray = new Mat())
            using (var mask = new Mat(frame.Height, frame.Width, MatType.CV_8UC1))
            {
                Marshal.Copy(frame.Bgra, 0, bgra.Data, frame.Bgra.Length);
                var labels = depth.Select(z => z == 0 ? (byte)0 : (byte)255).ToArray();
                Marshal.Copy(labels, 0, mask.Data, labels.Length);
                Cv2.CvtColor(bgra, gray, ColorConversionCodes.BGRA2GRAY);
                detector.DetectAndCompute(gray, mask, out view.Keys, view.Descriptors);
            }
            return view;
        }

        internal bool Estimate(View current, DepthIntrinsics camera, out FusionMatrix guess)
        {
            guess = FusionMatrix.Identity; Matches = 0; ErrorMetres = double.PositiveInfinity;
            if (current.Descriptors.Rows < 8 || previous == null) return false;
            bool anchoredChoice = false;
            foreach (var reference in new[] { previous }.Concat(anchors))
            {
                if (reference.Descriptors.Rows < 8) continue;
                var matches = matcher.KnnMatch(reference.Descriptors, current.Descriptors, 2);
                var reverse = matcher.KnnMatch(current.Descriptors, reference.Descriptors, 2);
                var xyz = new List<Point3f>(); var uv = new List<Point2f>(); var observed = new List<Point3f>();
                var used = new HashSet<int>();
                foreach (var pair in matches)
                {
                    if (pair.Length < 2 || pair[0].Distance >= .75 * pair[1].Distance || !used.Add(pair[0].TrainIdx)) continue;
                    var back = reverse[pair[0].TrainIdx];
                    if (back.Length < 2 || back[0].Distance >= .75 * back[1].Distance || back[0].TrainIdx != pair[0].QueryIdx) continue;
                    var a = reference.Keys[pair[0].QueryIdx].Pt; var b = current.Keys[pair[0].TrainIdx].Pt;
                    Point3f pa, pb;
                    if (!Point(reference, a, camera, out pa) || !Point(current, b, camera, out pb)) continue;
                    xyz.Add(pa); uv.Add(b); observed.Add(pb);
                }
                if (xyz.Count < 8) continue;
                double[,] r; double[] translation; int[] inliers;
                if (!FitRansac(xyz, observed, out r, out translation, out inliers)) continue;
                double error = Math.Sqrt(inliers.Average(i => SquaredError(xyz[i], observed[i], r, translation)));
                bool anchored = anchors.Contains(reference);
                if (error > .010) continue;
                if (anchoredChoice && inliers.Length <= Matches * 1.5) continue;
                if (!anchoredChoice && inliers.Length <= Matches && !(anchored && inliers.Length >= Math.Max(10, Matches * .5))) continue;
                var motion = new Matrix4x4((float)r[0,0],(float)r[1,0],(float)r[2,0],0,
                    (float)r[0,1],(float)r[1,1],(float)r[2,1],0,(float)r[0,2],(float)r[1,2],(float)r[2,2],0,
                    (float)translation[0],(float)translation[1],(float)translation[2],1);
                var aPose = reference.Pose;
                var worldToReference = new Matrix4x4(aPose.M11,aPose.M12,aPose.M13,aPose.M14,aPose.M21,aPose.M22,aPose.M23,aPose.M24,aPose.M31,aPose.M32,aPose.M33,aPose.M34,aPose.M41,aPose.M42,aPose.M43,aPose.M44);
                var pPose = worldToReference * motion;
                guess = new FusionMatrix { M11=pPose.M11,M12=pPose.M12,M13=pPose.M13,M14=pPose.M14,M21=pPose.M21,M22=pPose.M22,M23=pPose.M23,M24=pPose.M24,M31=pPose.M31,M32=pPose.M32,M33=pPose.M33,M34=pPose.M34,M41=pPose.M41,M42=pPose.M42,M43=pPose.M43,M44=pPose.M44 };
                Matches = inliers.Length; ErrorMetres = error;
                anchoredChoice = anchored;
            }
            return Matches >= 8;
        }

        private bool FitRansac(List<Point3f> source, List<Point3f> target, out double[,] rotation, out double[] translation, out int[] inliers)
        {
            rotation = null; translation = null; inliers = new int[0];
            for (int attempt = 0; attempt < 80; attempt++)
            {
                int a = random.Next(source.Count), b = random.Next(source.Count), c = random.Next(source.Count);
                if (a == b || a == c || b == c) continue;
                var pa = new System.Numerics.Vector3(source[a].X, source[a].Y, source[a].Z);
                var pb = new System.Numerics.Vector3(source[b].X, source[b].Y, source[b].Z);
                var pc = new System.Numerics.Vector3(source[c].X, source[c].Y, source[c].Z);
                if (System.Numerics.Vector3.Cross(pb - pa, pc - pa).Length() < .0004f) continue;
                double[,] r; double[] t;
                Fit(source, target, new[] {a,b,c}, out r, out t);
                var selected = Enumerable.Range(0, source.Count).Where(i => SquaredError(source[i], target[i], r, t) < .012 * .012).ToArray();
                if (selected.Length <= inliers.Length) continue;
                inliers = selected;
                if (inliers.Length >= source.Count * .90) break;
            }
            if (inliers.Length < 8 || inliers.Length < source.Count * .5) return false;
            Fit(source, target, inliers, out rotation, out translation);
            return true;
        }

        private static double SquaredError(Point3f p, Point3f q, double[,] r, double[] t)
        {
            double x = r[0,0]*p.X+r[0,1]*p.Y+r[0,2]*p.Z+t[0]-q.X;
            double y = r[1,0]*p.X+r[1,1]*p.Y+r[1,2]*p.Z+t[1]-q.Y;
            double z = r[2,0]*p.X+r[2,1]*p.Y+r[2,2]*p.Z+t[2]-q.Z;
            return x*x+y*y+z*z;
        }

        private static void Fit(List<Point3f> source, List<Point3f> target, int[] indices, out double[,] rotation, out double[] translation)
        {
            var a = new double[3]; var b = new double[3];
            foreach (int i in indices)
            { a[0]+=source[i].X; a[1]+=source[i].Y; a[2]+=source[i].Z; b[0]+=target[i].X; b[1]+=target[i].Y; b[2]+=target[i].Z; }
            for (int j=0;j<3;j++) { a[j]/=indices.Length; b[j]/=indices.Length; }
            var covariance = new double[9];
            foreach (int i in indices)
            {
                var p = new[] {source[i].X-a[0],source[i].Y-a[1],source[i].Z-a[2]};
                var q = new[] {target[i].X-b[0],target[i].Y-b[1],target[i].Z-b[2]};
                for (int row=0;row<3;row++) for (int col=0;col<3;col++) covariance[row*3+col]+=p[row]*q[col];
            }
            rotation = new double[3,3]; translation = new double[3];
            using (var h = new Mat(3,3,MatType.CV_64FC1))
            using (var w = new Mat()) using (var u = new Mat()) using (var vt = new Mat())
            {
                Marshal.Copy(covariance,0,h.Data,9); Cv2.SVDecomp(h,w,u,vt);
                for (int row=0;row<3;row++) for (int col=0;col<3;col++)
                    for (int k=0;k<3;k++) rotation[row,col]+=vt.At<double>(k,row)*u.At<double>(col,k);
                double determinant = rotation[0,0]*(rotation[1,1]*rotation[2,2]-rotation[1,2]*rotation[2,1])-rotation[0,1]*(rotation[1,0]*rotation[2,2]-rotation[1,2]*rotation[2,0])+rotation[0,2]*(rotation[1,0]*rotation[2,1]-rotation[1,1]*rotation[2,0]);
                if (determinant < 0)
                    for (int row=0;row<3;row++) for (int col=0;col<3;col++) rotation[row,col]-=2*vt.At<double>(2,row)*u.At<double>(col,2);
            }
            for (int row=0;row<3;row++) translation[row]=b[row]-rotation[row,0]*a[0]-rotation[row,1]*a[1]-rotation[row,2]*a[2];
        }

        private static bool Point(View view, Point2f pixel, DepthIntrinsics camera, out Point3f point)
        {
            point = default(Point3f);
            int x = (int)Math.Round(pixel.X), y = (int)Math.Round(pixel.Y);
            if (x < 1 || y < 1 || x >= view.Width - 1 || y >= view.Height - 1) return false;
            var values = new List<ushort>(9);
            for (int dy = -1; dy <= 1; dy++) for (int dx = -1; dx <= 1; dx++)
            { ushort z = view.Depth[(y + dy) * view.Width + x + dx]; if (z > 0) values.Add(z); }
            if (values.Count < 5 || values.Max() - values.Min() > 35) return false;
            values.Sort(); float depth = values[values.Count / 2] / 1000f;
            point = new Point3f((pixel.X-camera.Cx)*depth/camera.Fx,(pixel.Y-camera.Cy)*depth/camera.Fy,depth);
            return true;
        }

        internal void Accept(View view, FusionMatrix pose)
        {
            if (previous != null && !anchors.Contains(previous)) previous.Dispose();
            view.Pose = pose; previous = view; accepted++;
            if (accepted == 1 || accepted % 10 == 0)
            {
                anchors.Add(view);
                if (anchors.Count > 24) { anchors[1].Dispose(); anchors.RemoveAt(1); }
            }
        }

        public void Dispose()
        {
            if (previous != null && !anchors.Contains(previous)) previous.Dispose();
            foreach (var view in anchors) view.Dispose();
            detector.Dispose(); matcher.Dispose();
        }
    }
}
