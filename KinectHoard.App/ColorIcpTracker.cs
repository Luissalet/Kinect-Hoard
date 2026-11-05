using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using KinectHoard.Core;
using FusionMatrix = Microsoft.Kinect.Fusion.Matrix4;

namespace KinectHoard.App
{
    // Rigid transforms: row-major 4x4 doubles, column-vector convention
    // (p' = M p). Poses are camera-to-world unless a name says otherwise.
    internal static class Rigid
    {
        internal static double[] Identity() { return new double[] { 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1 }; }

        internal static double[] Mul(double[] a, double[] b)
        {
            var r = new double[16];
            for (int i = 0; i < 4; i++)
                for (int j = 0; j < 4; j++)
                    r[i * 4 + j] = a[i * 4] * b[j] + a[i * 4 + 1] * b[4 + j] + a[i * 4 + 2] * b[8 + j] + a[i * 4 + 3] * b[12 + j];
            return r;
        }

        internal static double[] Inverse(double[] m)
        {
            var r = Identity();
            for (int i = 0; i < 3; i++) for (int j = 0; j < 3; j++) r[i * 4 + j] = m[j * 4 + i];
            for (int i = 0; i < 3; i++) r[i * 4 + 3] = -(r[i * 4] * m[3] + r[i * 4 + 1] * m[7] + r[i * 4 + 2] * m[11]);
            return r;
        }

        internal static double[] Relative(double[] from, double[] to) { return Mul(Inverse(from), to); }
        internal static double Angle(double[] m) { return Math.Acos(Math.Max(-1, Math.Min(1, (m[0] + m[5] + m[10] - 1) / 2))) * 180 / Math.PI; }
        internal static double Shift(double[] m) { return Math.Sqrt(m[3] * m[3] + m[7] * m[7] + m[11] * m[11]); }

        internal static void Apply(double[] m, double x, double y, double z, out double ox, out double oy, out double oz)
        {
            ox = m[0] * x + m[1] * y + m[2] * z + m[3];
            oy = m[4] * x + m[5] * y + m[6] * z + m[7];
            oz = m[8] * x + m[9] * y + m[10] * z + m[11];
        }

        // Rotation by the rotation vector w followed by translation t.
        internal static double[] FromVector(double wx, double wy, double wz, double tx, double ty, double tz)
        {
            double theta = Math.Sqrt(wx * wx + wy * wy + wz * wz);
            double a, b;
            if (theta < 1e-10) { a = 1; b = .5; }
            else { a = Math.Sin(theta) / theta; b = (1 - Math.Cos(theta)) / (theta * theta); }
            // R = I + a [w]x + b [w]x^2
            double xx = wx * wx, yy = wy * wy, zz = wz * wz, xy = wx * wy, xz = wx * wz, yz = wy * wz;
            return new[] {
                1 - b * (yy + zz), -a * wz + b * xy, a * wy + b * xz, tx,
                a * wz + b * xy, 1 - b * (xx + zz), -a * wx + b * yz, ty,
                -a * wy + b * xz, a * wx + b * yz, 1 - b * (xx + yy), tz,
                0, 0, 0, 1 };
        }

        // Rotation vector (radians) and translation of a rigid transform.
        internal static double[] ToVector(double[] m)
        {
            double c = Math.Max(-1, Math.Min(1, (m[0] + m[5] + m[10] - 1) / 2)), theta = Math.Acos(c);
            double rx = m[9] - m[6], ry = m[2] - m[8], rz = m[4] - m[1];
            double s = Math.Sin(theta), k = theta < 1e-6 ? .5 : theta / (2 * s);
            if (theta > Math.PI - 1e-3)
            {
                // Near 180 degrees the antisymmetric part vanishes; use the diagonal.
                double ax = Math.Sqrt(Math.Max(0, (m[0] + 1) / 2)), ay = Math.Sqrt(Math.Max(0, (m[5] + 1) / 2)), az = Math.Sqrt(Math.Max(0, (m[10] + 1) / 2));
                if (m[1] < 0) ay = -ay; if (m[2] < 0) az = -az;
                return new[] { ax * theta, ay * theta, az * theta, m[3], m[7], m[11] };
            }
            return new[] { rx * k, ry * k, rz * k, m[3], m[7], m[11] };
        }

        internal static double[] Orthonormalize(double[] m)
        {
            var r = (double[])m.Clone();
            double[] x = { m[0], m[4], m[8] }, y = { m[1], m[5], m[9] };
            Normalize(x);
            double d = x[0] * y[0] + x[1] * y[1] + x[2] * y[2];
            for (int i = 0; i < 3; i++) y[i] -= d * x[i];
            Normalize(y);
            double[] z = { x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2], x[0] * y[1] - x[1] * y[0] };
            for (int i = 0; i < 3; i++) { r[i * 4] = x[i]; r[i * 4 + 1] = y[i]; r[i * 4 + 2] = z[i]; }
            r[12] = r[13] = r[14] = 0; r[15] = 1;
            return r;
        }

        private static void Normalize(double[] v)
        {
            double n = Math.Sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
            if (n < 1e-12) { v[0] = 1; v[1] = v[2] = 0; return; }
            v[0] /= n; v[1] /= n; v[2] /= n;
        }

        // Fusion stores world-to-camera in the row-vector convention.
        internal static double[] FromFusion(FusionMatrix p)
        {
            var worldToCamera = new double[] { p.M11, p.M21, p.M31, p.M41, p.M12, p.M22, p.M32, p.M42, p.M13, p.M23, p.M33, p.M43, 0, 0, 0, 1 };
            return Inverse(Orthonormalize(worldToCamera));
        }

        internal static FusionMatrix ToFusion(double[] cameraToWorld)
        {
            var w = Inverse(cameraToWorld);
            return new FusionMatrix {
                M11 = (float)w[0], M21 = (float)w[1], M31 = (float)w[2], M41 = (float)w[3],
                M12 = (float)w[4], M22 = (float)w[5], M32 = (float)w[6], M42 = (float)w[7],
                M13 = (float)w[8], M23 = (float)w[9], M33 = (float)w[10], M43 = (float)w[11],
                M14 = 0, M24 = 0, M34 = 0, M44 = 1 };
        }

        internal static double[][] Rows(double[] m)
        {
            return new[] { new[] { m[0], m[1], m[2], m[3] }, new[] { m[4], m[5], m[6], m[7] },
                new[] { m[8], m[9], m[10], m[11] }, new[] { m[12], m[13], m[14], m[15] } };
        }

        // Solves the symmetric positive system a x = b in place (Cholesky).
        internal static bool Solve(double[] a, double[] b, int n)
        {
            for (int j = 0; j < n; j++)
            {
                double s = a[j * n + j];
                for (int k = 0; k < j; k++) s -= a[j * n + k] * a[j * n + k];
                if (s <= 1e-18) return false;
                double d = Math.Sqrt(s);
                a[j * n + j] = d;
                for (int i = j + 1; i < n; i++)
                {
                    double t = a[i * n + j];
                    for (int k = 0; k < j; k++) t -= a[i * n + k] * a[j * n + k];
                    a[i * n + j] = t / d;
                }
            }
            for (int i = 0; i < n; i++)
            {
                double t = b[i];
                for (int k = 0; k < i; k++) t -= a[i * n + k] * b[k];
                b[i] = t / a[i * n + i];
            }
            for (int i = n - 1; i >= 0; i--)
            {
                double t = b[i];
                for (int k = i + 1; k < n; k++) t -= a[k * n + i] * b[k];
                b[i] = t / a[i * n + i];
            }
            return true;
        }
    }

    // Half-resolution organised RGBD view: vertices, normals, intensity and
    // its gradient, chromaticity. Keyframes also keep the full-resolution
    // masked depth and colour so the volume can be rebuilt after a loop closure.
    internal sealed class IcpFrame
    {
        internal int W, H, Count;
        internal double Fx, Fy, Cx, Cy;
        internal float[] P, N, I, Gx, Gy, Chroma;
        internal bool[] Ok, Moving;
        internal int[] Valid;
        internal double[] Centroid = new double[3];
        internal double[] Pose;
        internal long Ticks;
        internal int Id = -1;
        internal double Travelled;
        internal ushort[] Depth;
        internal int[] Color;

        private static readonly double Grazing = ColorIcp.Tuning("KINECT_HOARD_ICP_GRAZING", .25);

        internal static IcpFrame Build(CameraFrame frame, ushort[] masked, DepthIntrinsics k)
        {
            int fw = frame.Width, fh = frame.Height, w = fw / 2, h = fh / 2;
            var f = new IcpFrame { W = w, H = h, Fx = k.Fx / 2, Fy = k.Fy / 2, Cx = (k.Cx - .5) / 2, Cy = (k.Cy - .5) / 2 };
            f.P = new float[w * h * 3]; f.N = new float[w * h * 3]; f.I = new float[w * h];
            f.Gx = new float[w * h]; f.Gy = new float[w * h]; f.Chroma = new float[w * h * 2]; f.Ok = new bool[w * h]; f.Moving = new bool[w * h];
            byte[] bgra = frame.Bgra;
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                {
                    int n = 0; double z = 0, zmin = 1e9, zmax = 0, r = 0, g = 0, b = 0;
                    for (int dy = 0; dy < 2; dy++)
                        for (int dx = 0; dx < 2; dx++)
                        {
                            int i = (2 * y + dy) * fw + 2 * x + dx;
                            ushort d = masked[i];
                            if (d == 0) continue;
                            double m = d / 1000.0; z += m; n++;
                            if (m < zmin) zmin = m; if (m > zmax) zmax = m;
                            b += bgra[i * 4]; g += bgra[i * 4 + 1]; r += bgra[i * 4 + 2];
                        }
                    if (n < 3 || zmax - zmin > .02) continue;
                    z /= n; int o = y * w + x;
                    f.P[o * 3] = (float)((x - f.Cx) * z / f.Fx); f.P[o * 3 + 1] = (float)((y - f.Cy) * z / f.Fy); f.P[o * 3 + 2] = (float)z;
                    r /= n * 255.0; g /= n * 255.0; b /= n * 255.0;
                    f.I[o] = (float)(.299 * r + .587 * g + .114 * b);
                    double s = Math.Max(r + g + b, .05);
                    f.Chroma[o * 2] = (float)(r / s); f.Chroma[o * 2 + 1] = (float)(g / s);
                }
            var valid = new List<int>();
            double sx = 0, sy = 0, sz = 0;
            for (int y = 1; y < h - 1; y++)
                for (int x = 1; x < w - 1; x++)
                {
                    int o = y * w + x; float z = f.P[o * 3 + 2];
                    if (z == 0) continue;
                    int l = o - 1, rr = o + 1, u = o - w, d = o + w;
                    float zl = f.P[l * 3 + 2], zr = f.P[rr * 3 + 2], zu = f.P[u * 3 + 2], zd = f.P[d * 3 + 2];
                    if (zl == 0 || zr == 0 || zu == 0 || zd == 0) continue;
                    double jump = 2 * (.02 + .01 * z);
                    if (Math.Abs(zl - zr) > jump || Math.Abs(zu - zd) > jump) continue;
                    double ax = f.P[rr * 3] - f.P[l * 3], ay = f.P[rr * 3 + 1] - f.P[l * 3 + 1], az = zr - zl;
                    double bx = f.P[d * 3] - f.P[u * 3], by = f.P[d * 3 + 1] - f.P[u * 3 + 1], bz = zd - zu;
                    double nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx;
                    double len = Math.Sqrt(nx * nx + ny * ny + nz * nz);
                    if (len < 1e-12) continue;
                    nx /= len; ny /= len; nz /= len;
                    double facing = (nx * f.P[o * 3] + ny * f.P[o * 3 + 1] + nz * z) / Math.Sqrt(f.P[o * 3] * f.P[o * 3] + f.P[o * 3 + 1] * f.P[o * 3 + 1] + z * z);
                    if (facing > 0) { nx = -nx; ny = -ny; nz = -nz; }
                    // Grazing surfaces at the silhouette have the noisiest depth and
                    // normals, and appear or vanish as the subject turns.
                    if (Math.Abs(facing) < Grazing) continue;
                    f.N[o * 3] = (float)nx; f.N[o * 3 + 1] = (float)ny; f.N[o * 3 + 2] = (float)nz;
                    f.Gx[o] = (f.I[rr] - f.I[l]) / 2; f.Gy[o] = (f.I[d] - f.I[u]) / 2;
                    f.Ok[o] = true; valid.Add(o);
                    sx += f.P[o * 3]; sy += f.P[o * 3 + 1]; sz += z;
                }
            f.Valid = valid.ToArray(); f.Count = f.Valid.Length;
            if (f.Count > 0) f.Centroid = new[] { sx / f.Count, sy / f.Count, sz / f.Count };
            return f;
        }

        // Drops the arrays only needed while this view is the source of an alignment.
        internal void Release() { Depth = null; Color = null; }
    }

    internal struct IcpLevel
    {
        internal readonly int Stride, Iterations;
        internal readonly double Distance, Kernel;
        internal readonly bool Colour;
        internal IcpLevel(int stride, double distance, double kernel, int iterations, bool colour)
        { Stride = stride; Distance = distance; Kernel = kernel; Iterations = iterations; Colour = colour; }
    }

    internal sealed class IcpResult
    {
        internal double[] Pose;
        internal double Fitness, Rmse, Colour;
        internal int Inliers, Samples;
    }

    // Coloured point-to-plane ICP with projective association against one or
    // more keyframes. Point-to-plane geometry plus an intensity term (image
    // gradient of the keyframe, as in dense RGB-D odometry), Tukey weights on
    // both: moved limbs and shadows fall outside the kernels instead of
    // pulling the pose. Coarse to fine over point strides and distances.
    internal static class ColorIcp
    {
        // KINECT_HOARD_ICP_GEOMETRIC overrides the geometric share for benchmarks.
        private static readonly double Geometric = Tuning("KINECT_HOARD_ICP_GEOMETRIC", .95), ColourKernel = Tuning("KINECT_HOARD_ICP_COLOUR_KERNEL", .08),
            RigidLimit = Tuning("KINECT_HOARD_ICP_RIGID", .01), FreeSpace = Tuning("KINECT_HOARD_ICP_FREE_SPACE", .03),
            PriorWeight = Tuning("KINECT_HOARD_ICP_PRIOR", .05);

        internal static double Tuning(string name, double fallback)
        {
            double value;
            return double.TryParse(Environment.GetEnvironmentVariable(name), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out value) ? value : fallback;
        }
        internal static readonly IcpLevel[] Standard = {
            new IcpLevel(4, .05, .03, 12, false), new IcpLevel(2, .025, .015, 8, true), new IcpLevel(1, .0125, .0075, 5, true) };
        internal static readonly IcpLevel[] Wide = {
            new IcpLevel(4, .10, .06, 14, false), new IcpLevel(4, .05, .03, 10, false),
            new IcpLevel(2, .025, .015, 8, true), new IcpLevel(1, .0125, .0075, 5, true) };
        internal static readonly IcpLevel[] Coarse = { new IcpLevel(4, .10, .06, 10, false), new IcpLevel(4, .05, .03, 8, false) };

        private struct Target
        {
            internal IcpFrame Frame;
            internal double[] Pose, WorldToCamera;
        }

        private static Target[] Prepare(IList<IcpFrame> frames)
        {
            var result = new Target[frames.Count];
            for (int i = 0; i < frames.Count; i++) result[i] = new Target { Frame = frames[i], Pose = frames[i].Pose, WorldToCamera = Rigid.Inverse(frames[i].Pose) };
            return result;
        }

        // Nearest projective neighbour among the targets of world point (wx,wy,wz).
        private static bool Associate(Target[] targets, double wx, double wy, double wz, double nx, double ny, double nz,
            double limit, int window, out int target, out int pixel, out double u, out double v, out double qx, out double qy, out double qz)
        {
            double spread; int seen;
            return Associate(targets, wx, wy, wz, nx, ny, nz, limit, window, out target, out pixel, out u, out v, out qx, out qy, out qz, out spread, out seen);
        }

        // Nearest projective neighbour among the targets of world point
        // (wx,wy,wz). spread is the largest point-to-plane residual over the
        // targets that see the point: a rigid surface agrees with every recent
        // keyframe, a swinging arm only with the one in the same phase.
        private static bool Associate(Target[] targets, double wx, double wy, double wz, double nx, double ny, double nz,
            double limit, int window, out int target, out int pixel, out double u, out double v, out double qx, out double qy, out double qz,
            out double spread, out int seen)
        {
            target = -1; pixel = -1; u = v = qx = qy = qz = 0; spread = 0; seen = 0;
            double best = limit * limit;
            for (int t = 0; t < targets.Length; t++)
            {
                var f = targets[t].Frame; var m = targets[t].WorldToCamera;
                double x, y, z;
                Rigid.Apply(m, wx, wy, wz, out x, out y, out z);
                if (z < .1) continue;
                double pu = f.Fx * x / z + f.Cx, pv = f.Fy * y / z + f.Cy;
                int cu = (int)Math.Round(pu), cv = (int)Math.Round(pv);
                // Normal of the source point in this target's camera.
                double tnx = m[0] * nx + m[1] * ny + m[2] * nz, tny = m[4] * nx + m[5] * ny + m[6] * nz, tnz = m[8] * nx + m[9] * ny + m[10] * nz;
                // Free space: this view saw a surface clearly behind the point, so a
                // rigid subject cannot be there now. A limb swung into that space;
                // a surface turning into view is behind, not in front, and passes.
                if (cu >= 1 && cv >= 1 && cu < f.W - 1 && cv < f.H - 1)
                {
                    int centre = cv * f.W + cu;
                    if (f.Ok[centre] && f.P[centre * 3 + 2] - z > FreeSpace) { seen++; spread = Math.Max(spread, 1.0); }
                }
                // A wider gate than the match itself, so a limb that moved
                // several centimetres still registers as a disagreement.
                double gate = Math.Max(limit, .05), local = gate * gate; int found = -1;
                for (int dv = -window; dv <= window; dv++)
                    for (int du = -window; du <= window; du++)
                    {
                        int iu = cu + du, iv = cv + dv;
                        if (iu < 1 || iv < 1 || iu >= f.W - 1 || iv >= f.H - 1) continue;
                        int o = iv * f.W + iu;
                        if (!f.Ok[o]) continue;
                        double ex = f.P[o * 3] - x, ey = f.P[o * 3 + 1] - y, ez = f.P[o * 3 + 2] - z;
                        double d = ex * ex + ey * ey + ez * ez;
                        if (d >= local) continue;
                        // Reject opposite-facing surfaces.
                        if (tnx * f.N[o * 3] + tny * f.N[o * 3 + 1] + tnz * f.N[o * 3 + 2] < .6) continue;
                        local = d; found = o;
                    }
                if (found < 0) continue;
                seen++;
                double residual = Math.Abs(f.N[found * 3] * (x - f.P[found * 3]) + f.N[found * 3 + 1] * (y - f.P[found * 3 + 1]) + f.N[found * 3 + 2] * (z - f.P[found * 3 + 2]));
                if (residual > spread) spread = residual;
                if (local < best) { best = local; target = t; pixel = found; u = pu; v = pv; qx = x; qy = y; qz = z; }
            }
            return target >= 0;
        }

        private static bool Bilinear(IcpFrame f, double u, double v, out double i, out double gx, out double gy)
        {
            i = gx = gy = 0;
            int x0 = (int)Math.Floor(u), y0 = (int)Math.Floor(v);
            if (x0 < 1 || y0 < 1 || x0 + 1 >= f.W - 1 || y0 + 1 >= f.H - 1) return false;
            int a = y0 * f.W + x0, b = a + 1, c = a + f.W, d = c + 1;
            if (!f.Ok[a] || !f.Ok[b] || !f.Ok[c] || !f.Ok[d]) return false;
            double fx = u - x0, fy = v - y0;
            double wa = (1 - fx) * (1 - fy), wb = fx * (1 - fy), wc = (1 - fx) * fy, wd = fx * fy;
            i = wa * f.I[a] + wb * f.I[b] + wc * f.I[c] + wd * f.I[d];
            gx = wa * f.Gx[a] + wb * f.Gx[b] + wc * f.Gx[c] + wd * f.Gx[d];
            gy = wa * f.Gy[a] + wb * f.Gy[b] + wc * f.Gy[c] + wd * f.Gy[d];
            return true;
        }

        private static double Tukey(double r, double k) { if (r >= k || r <= -k) return 0; double s = 1 - r * r / (k * k); return s * s; }

        private static void Accumulate(double[] h, double[] g, double[] j, double r, double weight)
        {
            for (int a = 0; a < 6; a++)
            {
                double ja = j[a] * weight;
                g[a] += ja * r;
                for (int b = a; b < 6; b++) h[a * 6 + b] += ja * j[b];
            }
        }

        internal static IcpResult Align(IcpFrame source, IList<IcpFrame> frames, double[] init, IcpLevel[] levels, double[] prior = null)
        {
            if (source.Count < 50 || frames.Count == 0) return null;
            var targets = Prepare(frames);
            var pose = (double[])init.Clone();
            var h = new double[36]; var g = new double[6]; var j = new double[6];
            for (int number = 0; number < levels.Length; number++)
            {
                var level = levels[number];
                bool finalLevel = number == levels.Length - 1;
                int step = Math.Max(1, level.Stride * level.Stride);
                for (int iteration = 0; iteration < level.Iterations; iteration++)
                {
                    Array.Clear(h, 0, 36); Array.Clear(g, 0, 6);
                    double cx, cy, cz;
                    Rigid.Apply(pose, source.Centroid[0], source.Centroid[1], source.Centroid[2], out cx, out cy, out cz);
                    int used = 0;
                    for (int s = 0; s < source.Count; s += step)
                    {
                        int o = source.Valid[s];
                        double wx, wy, wz;
                        Rigid.Apply(pose, source.P[o * 3], source.P[o * 3 + 1], source.P[o * 3 + 2], out wx, out wy, out wz);
                        double snx = pose[0] * source.N[o * 3] + pose[1] * source.N[o * 3 + 1] + pose[2] * source.N[o * 3 + 2];
                        double sny = pose[4] * source.N[o * 3] + pose[5] * source.N[o * 3 + 1] + pose[6] * source.N[o * 3 + 2];
                        double snz = pose[8] * source.N[o * 3] + pose[9] * source.N[o * 3 + 1] + pose[10] * source.N[o * 3 + 2];
                        int t, pixel, seen; double u, v, qx, qy, qz, spread;
                        bool matched = Associate(targets, wx, wy, wz, snx, sny, snz, level.Distance, 0, out t, out pixel, out u, out v, out qx, out qy, out qz, out spread, out seen);
                        // Fine levels: points that recent keyframes disagree on are
                        // moving limbs or cloth; they neither pull the pose nor fuse.
                        bool moving = level.Colour && seen >= 2 && spread > RigidLimit;
                        if (finalLevel && targets.Length >= 2) source.Moving[o] = moving;
                        if (!matched || moving) continue;
                        var f = targets[t].Frame; var kp = targets[t].Pose;
                        double vx, vy, vz;
                        Rigid.Apply(kp, f.P[pixel * 3], f.P[pixel * 3 + 1], f.P[pixel * 3 + 2], out vx, out vy, out vz);
                        double nx = kp[0] * f.N[pixel * 3] + kp[1] * f.N[pixel * 3 + 1] + kp[2] * f.N[pixel * 3 + 2];
                        double ny = kp[4] * f.N[pixel * 3] + kp[5] * f.N[pixel * 3 + 1] + kp[6] * f.N[pixel * 3 + 2];
                        double nz = kp[8] * f.N[pixel * 3] + kp[9] * f.N[pixel * 3 + 1] + kp[10] * f.N[pixel * 3 + 2];
                        double ax = wx - cx, ay = wy - cy, az = wz - cz;
                        double r = nx * (wx - vx) + ny * (wy - vy) + nz * (wz - vz);
                        double weight = Tukey(r, level.Kernel);
                        if (weight > 0)
                        {
                            j[0] = ay * nz - az * ny; j[1] = az * nx - ax * nz; j[2] = ax * ny - ay * nx; j[3] = nx; j[4] = ny; j[5] = nz;
                            Accumulate(h, g, j, r, Geometric * weight);
                            used++;
                        }
                        if (!level.Colour) continue;
                        double intensity, gu, gv;
                        if (!Bilinear(f, u, v, out intensity, out gu, out gv)) continue;
                        double rc = intensity - source.I[o];
                        double wc = Tukey(rc, ColourKernel);
                        if (wc <= 0) continue;
                        // d(u,v)/dq, then back to world through the keyframe rotation.
                        double iz = 1 / qz;
                        double gqx = gu * f.Fx * iz, gqy = gv * f.Fy * iz, gqz = -(gu * f.Fx * qx + gv * f.Fy * qy) * iz * iz;
                        double gx = kp[0] * gqx + kp[1] * gqy + kp[2] * gqz, gy = kp[4] * gqx + kp[5] * gqy + kp[6] * gqz, gz = kp[8] * gqx + kp[9] * gqy + kp[10] * gqz;
                        j[0] = ay * gz - az * gy; j[1] = az * gx - ax * gz; j[2] = ax * gy - ay * gx; j[3] = gx; j[4] = gy; j[5] = gz;
                        Accumulate(h, g, j, rc, (1 - Geometric) * wc);
                    }
                    if (used < 30) return null;
                    for (int a = 0; a < 6; a++) for (int b = 0; b < a; b++) h[a * 6 + b] = h[b * 6 + a];
                    double trace = 0; for (int a = 0; a < 6; a++) trace += h[a * 7];
                    for (int a = 0; a < 6; a++) { h[a * 7] += 1e-6 * trace / 6 + 1e-12; g[a] = -g[a]; }
                    if (prior != null && PriorWeight > 0)
                    {
                        // Soft motion prior: where the data barely constrain a rotation
                        // (a profile hidden behind a swinging arm), keep the turn rate.
                        var towards = Rigid.Mul(prior, Rigid.Inverse(pose));
                        var w = Rigid.ToVector(towards);
                        double px, py, pz;
                        Rigid.Apply(towards, cx, cy, cz, out px, out py, out pz);
                        double[] delta = { w[0], w[1], w[2], px - cx, py - cy, pz - cz };
                        double rotationScale = (h[0] + h[7] + h[14]) / 3 * PriorWeight;
                        for (int a = 0; a < 3; a++) { h[a * 7] += rotationScale; g[a] += rotationScale * delta[a]; }
                    }
                    if (!Rigid.Solve(h, g, 6)) return null;
                    var rotation = Rigid.FromVector(g[0], g[1], g[2], 0, 0, 0);
                    double rx, ry, rz;
                    Rigid.Apply(rotation, cx, cy, cz, out rx, out ry, out rz);
                    rotation[3] = cx - rx + g[3]; rotation[7] = cy - ry + g[4]; rotation[11] = cz - rz + g[5];
                    pose = Rigid.Orthonormalize(Rigid.Mul(rotation, pose));
                    if (Math.Abs(g[0]) + Math.Abs(g[1]) + Math.Abs(g[2]) < 2e-5 && Math.Abs(g[3]) + Math.Abs(g[4]) + Math.Abs(g[5]) < 2e-5) break;
                }
            }
            var result = Evaluate(source, targets, pose, .01);
            return result;
        }

        internal static IcpResult Evaluate(IcpFrame source, IList<IcpFrame> frames, double[] pose, double distance)
        {
            return Evaluate(source, Prepare(frames), pose, distance);
        }

        // Overlap within `distance`, inlier RMSE and chromaticity agreement:
        // a symmetric torso can fit front-to-back but not with its colours.
        private static IcpResult Evaluate(IcpFrame source, Target[] targets, double[] pose, double distance)
        {
            int samples = 0, inliers = 0, agree = 0; double squared = 0;
            for (int s = 0; s < source.Count; s += 2)
            {
                int o = source.Valid[s];
                double wx, wy, wz;
                Rigid.Apply(pose, source.P[o * 3], source.P[o * 3 + 1], source.P[o * 3 + 2], out wx, out wy, out wz);
                double snx = pose[0] * source.N[o * 3] + pose[1] * source.N[o * 3 + 1] + pose[2] * source.N[o * 3 + 2];
                double sny = pose[4] * source.N[o * 3] + pose[5] * source.N[o * 3 + 1] + pose[6] * source.N[o * 3 + 2];
                double snz = pose[8] * source.N[o * 3] + pose[9] * source.N[o * 3 + 1] + pose[10] * source.N[o * 3 + 2];
                samples++;
                int t, pixel; double u, v, qx, qy, qz;
                if (!Associate(targets, wx, wy, wz, snx, sny, snz, distance, 1, out t, out pixel, out u, out v, out qx, out qy, out qz)) continue;
                var f = targets[t].Frame;
                double ex = f.P[pixel * 3] - qx, ey = f.P[pixel * 3 + 1] - qy, ez = f.P[pixel * 3 + 2] - qz;
                squared += ex * ex + ey * ey + ez * ez; inliers++;
                if (Math.Max(Math.Abs(f.Chroma[pixel * 2] - source.Chroma[o * 2]), Math.Abs(f.Chroma[pixel * 2 + 1] - source.Chroma[o * 2 + 1])) < .05) agree++;
            }
            return new IcpResult {
                Pose = pose, Samples = samples, Inliers = inliers,
                Fitness = samples == 0 ? 0 : (double)inliers / samples,
                Rmse = inliers == 0 ? double.PositiveInfinity : Math.Sqrt(squared / inliers),
                Colour = inliers >= 50 ? (double)agree / inliers : 0 };
        }
    }
}
