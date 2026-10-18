using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using KinectHoard.Core;

namespace KinectHoard.App
{
    // A reusable 2D avatar driven only by the normalized body contract.
    internal static class AvatarRenderer
    {
        internal static Bitmap Create(TrackedBody[] bodies, int width, int height)
        {
            var image = new Bitmap(width, height, PixelFormat.Format32bppArgb);
            using (var graphics = Graphics.FromImage(image))
            {
                graphics.Clear(Color.FromArgb(17, 23, 35));
                graphics.SmoothingMode = SmoothingMode.AntiAlias;
                foreach (var body in bodies ?? new TrackedBody[0]) DrawBody(graphics, body, width, height);
            }
            return image;
        }

        private static void DrawBody(Graphics g, TrackedBody body, int width, int height)
        {
            var joints = new Dictionary<string, BodyJoint>();
            foreach (var joint in body.Joints ?? new BodyJoint[0])
                if (joint.TrackingState == 2 && Valid(joint, width, height)) joints[joint.Name] = joint;
            BodyJoint leftShoulder, rightShoulder, leftHip, rightHip, head, neck;
            if (joints.TryGetValue("ShoulderLeft", out leftShoulder) &&
                joints.TryGetValue("ShoulderRight", out rightShoulder) &&
                joints.TryGetValue("HipLeft", out leftHip) &&
                joints.TryGetValue("HipRight", out rightHip))
            {
                var torso = new[] { Point(leftShoulder), Point(rightShoulder), Point(rightHip), Point(leftHip) };
                using (var fill = new SolidBrush(Color.FromArgb(49, 205, 189))) g.FillPolygon(fill, torso);
            }
            using (var limb = new Pen(Color.FromArgb(80, 166, 245), 16) { StartCap = LineCap.Round, EndCap = LineCap.Round })
            {
                Connect(g, limb, joints, "ShoulderLeft", "ElbowLeft");
                Connect(g, limb, joints, "ElbowLeft", "WristLeft");
                Connect(g, limb, joints, "WristLeft", "HandLeft");
                Connect(g, limb, joints, "ShoulderRight", "ElbowRight");
                Connect(g, limb, joints, "ElbowRight", "WristRight");
                Connect(g, limb, joints, "WristRight", "HandRight");
                Connect(g, limb, joints, "HipLeft", "KneeLeft");
                Connect(g, limb, joints, "KneeLeft", "AnkleLeft");
                Connect(g, limb, joints, "AnkleLeft", "FootLeft");
                Connect(g, limb, joints, "HipRight", "KneeRight");
                Connect(g, limb, joints, "KneeRight", "AnkleRight");
                Connect(g, limb, joints, "AnkleRight", "FootRight");
            }
            if (joints.TryGetValue("Head", out head))
            {
                float radius = 23;
                if (joints.TryGetValue("Neck", out neck))
                    radius = Math.Max(17, Math.Min(32, (float)Math.Sqrt(Math.Pow(head.DepthX - neck.DepthX, 2) + Math.Pow(head.DepthY - neck.DepthY, 2)) * 0.75f));
                using (var fill = new SolidBrush(Color.FromArgb(242, 190, 139)))
                    g.FillEllipse(fill, head.DepthX - radius, head.DepthY - radius, radius * 2, radius * 2);
            }
            using (var hand = new SolidBrush(Color.FromArgb(255, 218, 170)))
                foreach (string key in new[] { "HandLeft", "HandRight" })
                {
                    BodyJoint joint;
                    if (joints.TryGetValue(key, out joint)) g.FillEllipse(hand, joint.DepthX - 9, joint.DepthY - 9, 18, 18);
                }
        }

        private static bool Valid(BodyJoint joint, int width, int height)
        {
            return !float.IsNaN(joint.DepthX) && !float.IsInfinity(joint.DepthX) &&
                   !float.IsNaN(joint.DepthY) && !float.IsInfinity(joint.DepthY) &&
                   joint.DepthX >= 0 && joint.DepthX < width && joint.DepthY >= 0 && joint.DepthY < height;
        }

        private static PointF Point(BodyJoint joint) { return new PointF(joint.DepthX, joint.DepthY); }

        private static void Connect(Graphics g, Pen pen, Dictionary<string, BodyJoint> joints, string from, string to)
        {
            BodyJoint a, b;
            if (joints.TryGetValue(from, out a) && joints.TryGetValue(to, out b))
                g.DrawLine(pen, Point(a), Point(b));
        }
    }
}
