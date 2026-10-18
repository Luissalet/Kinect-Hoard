using System;
using System.Collections.Generic;

namespace KinectHoard.Core
{
    public static class FrameRenderer
    {
        private static readonly string[,] Bones = {
            { "Head", "Neck" }, { "Neck", "SpineShoulder" }, { "SpineShoulder", "SpineMid" },
            { "SpineMid", "SpineBase" }, { "SpineShoulder", "ShoulderLeft" }, { "SpineShoulder", "ShoulderRight" },
            { "ShoulderLeft", "ElbowLeft" }, { "ElbowLeft", "WristLeft" }, { "WristLeft", "HandLeft" },
            { "ShoulderRight", "ElbowRight" }, { "ElbowRight", "WristRight" }, { "WristRight", "HandRight" },
            { "SpineBase", "HipLeft" }, { "HipLeft", "KneeLeft" }, { "KneeLeft", "AnkleLeft" }, { "AnkleLeft", "FootLeft" },
            { "SpineBase", "HipRight" }, { "HipRight", "KneeRight" }, { "KneeRight", "AnkleRight" }, { "AnkleRight", "FootRight" }
        };

        public static byte[] RenderSkeleton(TrackedBody[] bodies, int width, int height, byte[] reuse)
        {
            int length = checked(width * height * 4);
            byte[] pixels = reuse != null && reuse.Length == length ? reuse : new byte[length];
            Array.Clear(pixels, 0, pixels.Length);
            foreach (TrackedBody body in bodies)
            {
                var joints = new Dictionary<string, BodyJoint>();
                foreach (BodyJoint joint in body.Joints) joints[joint.Name] = joint;
                for (int i = 0; i < Bones.GetLength(0); i++)
                {
                    BodyJoint a, b;
                    if (joints.TryGetValue(Bones[i, 0], out a) && joints.TryGetValue(Bones[i, 1], out b) &&
                        a.TrackingState != 0 && b.TrackingState != 0 && Valid(a, width, height) && Valid(b, width, height))
                        Line(pixels, width, height, (int)a.DepthX, (int)a.DepthY, (int)b.DepthX, (int)b.DepthY);
                }
                foreach (BodyJoint joint in body.Joints)
                    if (joint.TrackingState != 0 && Valid(joint, width, height))
                        Dot(pixels, width, height, (int)joint.DepthX, (int)joint.DepthY);
            }
            return pixels;
        }

        private static bool Valid(BodyJoint joint, int width, int height)
        {
            return !float.IsNaN(joint.DepthX) && !float.IsNaN(joint.DepthY) &&
                !float.IsInfinity(joint.DepthX) && !float.IsInfinity(joint.DepthY) &&
                joint.DepthX >= 0 && joint.DepthY >= 0 && joint.DepthX < width && joint.DepthY < height;
        }

        private static void Dot(byte[] pixels, int width, int height, int x, int y)
        {
            for (int dy = -3; dy <= 3; dy++)
                for (int dx = -3; dx <= 3; dx++)
                    if (dx * dx + dy * dy <= 9) Pixel(pixels, width, height, x + dx, y + dy, 245, 245, 245);
        }

        private static void Line(byte[] pixels, int width, int height, int x0, int y0, int x1, int y1)
        {
            int dx = Math.Abs(x1 - x0), sx = x0 < x1 ? 1 : -1;
            int dy = -Math.Abs(y1 - y0), sy = y0 < y1 ? 1 : -1;
            int error = dx + dy;
            while (true)
            {
                Pixel(pixels, width, height, x0, y0, 116, 224, 110);
                if (x0 == x1 && y0 == y1) break;
                int twice = error * 2;
                if (twice >= dy) { error += dy; x0 += sx; }
                if (twice <= dx) { error += dx; y0 += sy; }
            }
        }

        private static void Pixel(byte[] pixels, int width, int height, int x, int y, byte b, byte g, byte r)
        {
            if (x < 0 || y < 0 || x >= width || y >= height) return;
            int i = (y * width + x) * 4;
            pixels[i] = b; pixels[i + 1] = g; pixels[i + 2] = r; pixels[i + 3] = 255;
        }
        public static byte[] RenderDepth(ushort[] values, byte[] reuse, int minDepth, int maxDepth)
        {
            byte[] pixels = Prepare(values, reuse);
            int span = Math.Max(1, maxDepth - minDepth);
            for (int i = 0, j = 0; i < values.Length; i++, j += 4)
            {
                int value = values[i];
                byte shade = value < minDepth || value > maxDepth ? (byte)0 : (byte)(255 - (value - minDepth) * 255 / span);
                pixels[j] = shade; pixels[j + 1] = shade; pixels[j + 2] = shade; pixels[j + 3] = 255;
            }
            return pixels;
        }

        public static byte[] RenderInfrared(ushort[] values, byte[] reuse)
        {
            byte[] pixels = Prepare(values, reuse);
            // Auto contrast from a sampled 1%-99% intensity range; ignore zero pixels.
            int[] histogram = new int[1024];
            int count = 0;
            for (int i = 0; i < values.Length; i += 4)
                if (values[i] != 0) { histogram[values[i] >> 6]++; count++; }
            int low = Percentile(histogram, count / 100);
            int high = Percentile(histogram, count * 99 / 100);
            int span = Math.Max(1, high - low);
            for (int i = 0, j = 0; i < values.Length; i++, j += 4)
            {
                int shade = ((int)values[i] - low) * 255 / span;
                byte level = (byte)Math.Max(0, Math.Min(255, shade));
                pixels[j] = level; pixels[j + 1] = level; pixels[j + 2] = level; pixels[j + 3] = 255;
            }
            return pixels;
        }

        public static byte[] RenderBodyIndex(ushort[] values, byte[] reuse)
        {
            byte[] pixels = Prepare(values, reuse);
            byte[,] colors = { { 39, 198, 255 }, { 255, 165, 65 }, { 104, 228, 140 },
                { 233, 112, 192 }, { 161, 136, 255 }, { 255, 226, 87 } };
            for (int i = 0, j = 0; i < values.Length; i++, j += 4)
            {
                int body = values[i];
                pixels[j] = body < 6 ? colors[body, 0] : (byte)0;
                pixels[j + 1] = body < 6 ? colors[body, 1] : (byte)0;
                pixels[j + 2] = body < 6 ? colors[body, 2] : (byte)0;
                pixels[j + 3] = 255;
            }
            return pixels;
        }

        private static int Percentile(int[] histogram, int target)
        {
            int total = 0;
            for (int i = 0; i < histogram.Length; i++)
            {
                total += histogram[i];
                if (total >= target) return i << 6;
            }
            return 65535;
        }

        private static byte[] Prepare(ushort[] values, byte[] reuse)
        {
            int length = checked(values.Length * 4);
            return reuse != null && reuse.Length == length ? reuse : new byte[length];
        }
    }
}
