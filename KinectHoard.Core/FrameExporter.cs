using System;
using System.IO;
using System.Globalization;
using System.Text;

namespace KinectHoard.Core
{
    public static class FrameExporter
    {
        public sealed class MeshResult
        {
            public int Vertices { get; set; }
            public int Faces { get; set; }
        }
        // PGM P5 with maxval 65535 stores each sensor sample without reducing it to 8-bit preview gray.
        public static void SavePgm(string path, int width, int height, ushort[] values)
        {
            if (values == null || values.Length != checked(width * height))
                throw new ArgumentException("Dimensiones de datos no válidas.", "values");
            using (var stream = new FileStream(path, FileMode.Create, FileAccess.Write))
            {
                byte[] header = Encoding.ASCII.GetBytes("P5\n# Kinect Hoard: raw 16-bit sensor samples\n" + width + " " + height + "\n65535\n");
                stream.Write(header, 0, header.Length);
                byte[] row = new byte[width * 2];
                for (int y = 0; y < height; y++)
                {
                    for (int x = 0; x < width; x++)
                    {
                        ushort value = values[y * width + x];
                        row[x * 2] = (byte)(value >> 8);  // PGM requires big endian for 16-bit samples.
                        row[x * 2 + 1] = (byte)value;
                    }
                    stream.Write(row, 0, row.Length);
                }
            }
        }

        public static int SavePly(string path, PointCloudFrame frame)
        {
            if (frame == null || frame.Xyz == null || frame.Xyz.Length != checked(frame.Width * frame.Height * 3))
                throw new ArgumentException("Nube de puntos no válida.", "frame");
            bool color = frame.Rgb != null && frame.Rgb.Length == frame.Xyz.Length;
            if (frame.Rgb != null && !color) throw new ArgumentException("Colores RGB incompatibles.", "frame");
            int count = 0;
            for (int i = 0; i < frame.Xyz.Length; i += 3)
                if (Valid(frame.Xyz[i], frame.Xyz[i + 1], frame.Xyz[i + 2])) count++;
            using (var writer = new StreamWriter(path, false, new UTF8Encoding(false)))
            {
                writer.Write("ply\nformat ascii 1.0\ncomment Kinect Hoard XYZ in metres\nelement vertex ");
                writer.Write(count.ToString(CultureInfo.InvariantCulture));
                writer.Write("\nproperty float x\nproperty float y\nproperty float z\n");
                if (color) writer.Write("property uchar red\nproperty uchar green\nproperty uchar blue\n");
                writer.Write("end_header\n");
                for (int i = 0; i < frame.Xyz.Length; i += 3)
                {
                    float x = frame.Xyz[i], y = frame.Xyz[i + 1], z = frame.Xyz[i + 2];
                    if (!Valid(x, y, z)) continue;
                    writer.Write(x.ToString("R", CultureInfo.InvariantCulture)); writer.Write(' ');
                    writer.Write(y.ToString("R", CultureInfo.InvariantCulture)); writer.Write(' ');
                    writer.Write(z.ToString("R", CultureInfo.InvariantCulture));
                    if (color) writer.Write(" " + frame.Rgb[i] + " " + frame.Rgb[i + 1] + " " + frame.Rgb[i + 2]);
                    writer.WriteLine();
                }
            }
            return count;
        }

        // Two local triangles per depth quad; reject edges that cross a depth discontinuity.
        public static MeshResult SaveMeshPly(string path, PointCloudFrame frame, float maxEdgeMetres = 0.06f)
        {
            if (frame == null || frame.Width < 2 || frame.Height < 2 || frame.Xyz == null ||
                frame.Xyz.Length != checked(frame.Width * frame.Height * 3) || maxEdgeMetres <= 0)
                throw new ArgumentException("Nube de puntos no válida para una malla.", "frame");
            bool color = frame.Rgb != null && frame.Rgb.Length == frame.Xyz.Length;
            if (frame.Rgb != null && !color) throw new ArgumentException("Colores RGB incompatibles.", "frame");
            int count = frame.Width * frame.Height;
            var indices = new int[count];
            int vertices = 0, faces = 0;
            for (int i = 0; i < count; i++)
            {
                int j = i * 3;
                indices[i] = Valid(frame.Xyz[j], frame.Xyz[j + 1], frame.Xyz[j + 2]) ? vertices++ : -1;
            }
            for (int y = 0; y < frame.Height - 1; y++)
                for (int x = 0; x < frame.Width - 1; x++)
                {
                    int a = y * frame.Width + x, b = a + 1, c = a + frame.Width, d = c + 1;
                    if (Triangle(frame.Xyz, indices, a, c, b, maxEdgeMetres)) faces++;
                    if (Triangle(frame.Xyz, indices, b, c, d, maxEdgeMetres)) faces++;
                }
            using (var writer = new StreamWriter(path, false, new UTF8Encoding(false)))
            {
                writer.Write("ply\nformat ascii 1.0\ncomment Kinect Hoard single depth frame XYZ in metres\n");
                writer.Write("element vertex "); writer.Write(vertices.ToString(CultureInfo.InvariantCulture));
                writer.Write("\nproperty float x\nproperty float y\nproperty float z\n");
                if (color) writer.Write("property uchar red\nproperty uchar green\nproperty uchar blue\n");
                writer.Write("element face ");
                writer.Write(faces.ToString(CultureInfo.InvariantCulture));
                writer.Write("\nproperty list uchar int vertex_indices\nend_header\n");
                for (int i = 0; i < count; i++)
                {
                    if (indices[i] < 0) continue;
                    int j = i * 3;
                    writer.Write(frame.Xyz[j].ToString("R", CultureInfo.InvariantCulture)); writer.Write(' ');
                    writer.Write(frame.Xyz[j + 1].ToString("R", CultureInfo.InvariantCulture)); writer.Write(' ');
                    writer.Write(frame.Xyz[j + 2].ToString("R", CultureInfo.InvariantCulture));
                    if (color) writer.Write(" " + frame.Rgb[j] + " " + frame.Rgb[j + 1] + " " + frame.Rgb[j + 2]);
                    writer.WriteLine();
                }
                for (int y = 0; y < frame.Height - 1; y++)
                    for (int x = 0; x < frame.Width - 1; x++)
                    {
                        int a = y * frame.Width + x, b = a + 1, c = a + frame.Width, d = c + 1;
                        if (Triangle(frame.Xyz, indices, a, c, b, maxEdgeMetres))
                            writer.WriteLine("3 " + indices[a] + " " + indices[c] + " " + indices[b]);
                        if (Triangle(frame.Xyz, indices, b, c, d, maxEdgeMetres))
                            writer.WriteLine("3 " + indices[b] + " " + indices[c] + " " + indices[d]);
                    }
            }
            return new MeshResult { Vertices = vertices, Faces = faces };
        }

        private static bool Triangle(float[] xyz, int[] indices, int a, int b, int c, float maxEdge)
        {
            return indices[a] >= 0 && indices[b] >= 0 && indices[c] >= 0 &&
                Edge(xyz, a, b, maxEdge) && Edge(xyz, b, c, maxEdge) && Edge(xyz, c, a, maxEdge);
        }

        private static bool Edge(float[] xyz, int a, int b, float limit)
        {
            a *= 3; b *= 3;
            float dx = xyz[a] - xyz[b], dy = xyz[a + 1] - xyz[b + 1], dz = xyz[a + 2] - xyz[b + 2];
            return dx * dx + dy * dy + dz * dz <= limit * limit;
        }

        private static bool Valid(float x, float y, float z)
        {
            return z > 0 && !float.IsNaN(x) && !float.IsNaN(y) && !float.IsNaN(z) &&
                !float.IsInfinity(x) && !float.IsInfinity(y) && !float.IsInfinity(z);
        }
    }
}
