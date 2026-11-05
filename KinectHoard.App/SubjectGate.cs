using System;
using System.Collections.Generic;
using System.Linq;
using KinectHoard.Core;

namespace KinectHoard.App
{
    // The refine's subject mask, per frame and live: depth band, floor plane
    // (found once), components separated at depth jumps, a vertical cylinder
    // around the subject axis and a continuity test that drops views where
    // the subject left the image or the mask jumped to another surface.
    internal sealed class SubjectGate
    {
        internal double Radius = .5, Near = .4, Far = 3.0;
        internal int MinPixels = 1500;
        private double[] floor;
        private int floorAttempts;
        private double[] axis;
        private readonly List<int> areas = new List<int>();
        private readonly Random random = new Random(5);
        private float[] x, z, all;
        private bool[] valid, cut;
        private int[] labels, queue;
        internal string LastReason = "";
        internal bool HasFloor { get { return floor != null; } }
        internal double[] Axis { get { return axis; } }

        internal void Reset() { axis = null; areas.Clear(); }

        // seed: pixel the user picked; until the axis is known the component
        // under it wins, otherwise the largest one near the image centre.
        internal ushort[] Apply(ushort[] raw, ushort[] masked, int width, int height, DepthIntrinsics k, int seed = -1)
        {
            if (floor == null && floorAttempts < 10) { floorAttempts++; floor = FindFloor(raw, width, height, k); }
            int size = width * height;
            // Buffers are reused between frames: large per-frame arrays would
            // land on the large-object heap and stall the capture thread in GC.
            if (x == null || x.Length != size)
            { x = new float[size]; z = new float[size]; valid = new bool[size]; all = new float[size]; cut = new bool[size]; labels = new int[size]; queue = new int[size]; }
            Array.Clear(cut, 0, size); Array.Clear(labels, 0, size);
            for (int i = 0; i < size; i++)
            {
                all[i] = raw[i] / 1000f;
                valid[i] = false;
                if (masked[i] == 0) continue;
                double depth = masked[i] / 1000.0;
                if (depth <= Near || depth >= Far) continue;
                double px = (i % width - k.Cx) * depth / k.Fx, py = (i / width - k.Cy) * depth / k.Fy;
                if (floor != null && floor[0] * px + floor[1] * py + floor[2] * depth + floor[3] <= .025) continue;
                x[i] = (float)px; z[i] = (float)depth; valid[i] = true;
            }
            // Cut depth discontinuities of the full image so the subject separates from what lies behind.
            for (int y = 0; y < height; y++)
                for (int c = 0; c < width; c++)
                {
                    int i = y * width + c;
                    if (c + 1 < width && Math.Abs(all[i] - all[i + 1]) > .02 + .01 * all[i + 1]) { cut[i] = cut[i + 1] = true; }
                    if (y + 1 < height && Math.Abs(all[i] - all[i + width]) > .02 + .01 * all[i + width]) { cut[i] = cut[i + width] = true; }
                }
            var components = new List<double[]>(); // label, area, mean x, mean z, column centre
            int next = 0;
            for (int start = 0; start < size; start++)
            {
                if (!valid[start] || cut[start] || labels[start] != 0) continue;
                next++;
                int head = 0, tail = 0, area = 0, left = width, right = 0; double sx = 0, sz = 0;
                queue[tail++] = start; labels[start] = next;
                while (head < tail)
                {
                    int i = queue[head++]; area++; sx += x[i]; sz += z[i];
                    int column = i % width; if (column < left) left = column; if (column > right) right = column;
                    if (column > 0) Visit(i - 1, next, valid, cut, labels, queue, ref tail);
                    if (column < width - 1) Visit(i + 1, next, valid, cut, labels, queue, ref tail);
                    if (i >= width) Visit(i - width, next, valid, cut, labels, queue, ref tail);
                    if (i + width < size) Visit(i + width, next, valid, cut, labels, queue, ref tail);
                }
                if (area >= 250) components.Add(new double[] { next, area, sx / area, sz / area, (left + right) / 2.0 });
            }
            components = components.OrderByDescending(c => c[1]).Take(16).ToList();
            if (components.Count == 0) { LastReason = "Sin superficie del sujeto en la imagen."; return null; }
            double[] candidate = axis;
            if (candidate == null)
            {
                var picked = seed >= 0 && seed < size ? components.FirstOrDefault(c => (int)c[0] == labels[seed]) : null;
                var first = picked ?? components.OrderByDescending(c => c[1] * (1.25 - Math.Abs(c[4] / width - .5))).First();
                candidate = new[] { first[2], first[3] + .08 };
            }
            var chosen = new HashSet<int>(components.Where(c => Math.Sqrt((c[2] - candidate[0]) * (c[2] - candidate[0]) + (c[3] - candidate[1]) * (c[3] - candidate[1])) < Radius).Select(c => (int)c[0]));
            if (chosen.Count == 0) { LastReason = "El sujeto no está junto a su eje de giro."; return null; }
            var result = new ushort[size];
            int count = 0; double mx = 0, mz = 0;
            double r2 = Radius * Radius;
            for (int i = 0; i < size; i++)
            {
                if (labels[i] == 0 || !chosen.Contains(labels[i])) continue;
                double dx = x[i] - candidate[0], dz = z[i] - candidate[1];
                if (dx * dx + dz * dz >= r2) continue;
                result[i] = masked[i]; count++; mx += x[i]; mz += z[i];
            }
            double typical = areas.Count == 0 ? count : Median(areas.Skip(Math.Max(0, areas.Count - 15)));
            if (count < Math.Max(MinPixels, .3 * typical)) { LastReason = "Sujeto parcial o fuera de la imagen."; return null; }
            double[] centre = { mx / count, mz / count + .08 };
            if (axis != null && Math.Sqrt((centre[0] - axis[0]) * (centre[0] - axis[0]) + (centre[1] - axis[1]) * (centre[1] - axis[1])) > .35)
            { LastReason = "La máscara saltó a otra superficie."; return null; }
            axis = axis == null ? centre : new[] { .85 * axis[0] + .15 * centre[0], .85 * axis[1] + .15 * centre[1] };
            areas.Add(count); if (areas.Count > 60) areas.RemoveAt(0);
            LastReason = "";
            return result;
        }

        private static void Visit(int j, int label, bool[] valid, bool[] cut, int[] labels, int[] queue, ref int tail)
        {
            if (!valid[j] || cut[j] || labels[j] != 0) return;
            labels[j] = label; queue[tail++] = j;
        }

        private static double Median(IEnumerable<int> values)
        {
            var sorted = values.OrderBy(v => v).ToArray();
            return sorted.Length == 0 ? 0 : sorted[sorted.Length / 2];
        }

        // Horizontal plane below the image centre (camera Y points down).
        private double[] FindFloor(ushort[] raw, int width, int height, DepthIntrinsics k)
        {
            var points = new List<double[]>();
            for (int y = 0; y < height; y += 4)
                for (int c = 0; c < width; c += 4)
                {
                    double depth = raw[y * width + c] / 1000.0;
                    if (depth <= Near || depth >= Far + 1.5) continue;
                    points.Add(new[] { (c - k.Cx) * depth / k.Fx, (y - k.Cy) * depth / k.Fy, depth });
                }
            if (points.Count < 500) return null;
            double medianY = points.Select(p => p[1]).OrderBy(v => v).ElementAt(points.Count / 2);
            var remaining = points;
            for (int round = 0; round < 3 && remaining.Count >= 500; round++)
            {
                double[] best = null; int bestCount = 0;
                for (int attempt = 0; attempt < 300; attempt++)
                {
                    var a = remaining[random.Next(remaining.Count)]; var b = remaining[random.Next(remaining.Count)]; var c = remaining[random.Next(remaining.Count)];
                    double ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2], vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
                    double nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx, n = Math.Sqrt(nx * nx + ny * ny + nz * nz);
                    if (n < 1e-9) continue;
                    nx /= n; ny /= n; nz /= n;
                    double d = -(nx * a[0] + ny * a[1] + nz * a[2]);
                    int inliers = 0;
                    foreach (var p in remaining) if (Math.Abs(nx * p[0] + ny * p[1] + nz * p[2] + d) < .015) inliers++;
                    if (inliers > bestCount) { bestCount = inliers; best = new[] { nx, ny, nz, d }; }
                }
                if (best == null) return null;
                var plane = best;
                var inPlane = remaining.Where(p => Math.Abs(plane[0] * p[0] + plane[1] * p[1] + plane[2] * p[2] + plane[3]) < .015).ToList();
                if (Math.Abs(plane[1]) > .88 && bestCount > .05 * points.Count)
                {
                    if (plane[1] > 0) plane = plane.Select(v => -v).ToArray();
                    double floorY = inPlane.Select(p => p[1]).OrderBy(v => v).ElementAt(inPlane.Count / 2);
                    if (floorY > medianY - .05) return plane;
                }
                remaining = remaining.Where(p => Math.Abs(plane[0] * p[0] + plane[1] * p[1] + plane[2] * p[2] + plane[3]) >= .015).ToList();
            }
            return null;
        }
    }
}
