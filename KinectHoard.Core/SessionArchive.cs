using System;
using System.IO;
using System.IO.Compression;

namespace KinectHoard.Core
{
    // Sequential gzip archive: portable between sensors and readable without a connected Kinect.
    public sealed class SessionWriter : IDisposable
    {
        private readonly BinaryWriter writer;
        private readonly bool qualityColor;
        public int FrameCount { get; private set; }
        public StreamKind Stream { get; private set; }

        public SessionWriter(string path, StreamKind stream, bool qualityColor = false)
        {
            Stream = stream;
            this.qualityColor = qualityColor;
            writer = new BinaryWriter(new GZipStream(new FileStream(path, FileMode.Create, FileAccess.Write), CompressionMode.Compress));
            writer.Write(qualityColor ? "KINECT_HOARD_SESSION_2" : "KINECT_HOARD_SESSION_1");
            writer.Write((int)stream);
            writer.Write(DateTime.UtcNow.Ticks);
        }

        public void WriteFrame(CameraFrame frame)
        {
            if (frame == null || frame.Kind != Stream || frame.Width < 1 || frame.Height < 1 ||
                frame.Bgra == null || frame.Bgra.Length != checked(frame.Width * frame.Height * 4))
                throw new ArgumentException("Fotograma incompatible con la sesión.", "frame");
            writer.Write((byte)1);
            writer.Write((frame.TimestampUtc == default(DateTime) ? DateTime.UtcNow : frame.TimestampUtc.ToUniversalTime()).Ticks);
            writer.Write(frame.Width);
            writer.Write(frame.Height);
            writer.Write(frame.Bgra.Length);
            writer.Write(frame.Bgra);
            writer.Write(frame.Values == null ? 0 : frame.Values.Length);
            if (frame.Values != null)
                foreach (ushort value in frame.Values) writer.Write(value);
            writer.Write(frame.Bodies == null ? 0 : frame.Bodies.Length);
            if (frame.Bodies != null)
                foreach (TrackedBody body in frame.Bodies)
                {
                    writer.Write(body.TrackingId);
                    writer.Write(body.Joints.Length);
                    foreach (BodyJoint joint in body.Joints)
                    {
                        writer.Write(joint.Name ?? "");
                        writer.Write(joint.X); writer.Write(joint.Y); writer.Write(joint.Z);
                        writer.Write(joint.DepthX); writer.Write(joint.DepthY);
                        writer.Write(joint.TrackingState);
                    }
                }
            if (qualityColor)
            {
                int colorWidth = frame.FullColorWidth, colorHeight = frame.FullColorHeight;
                byte[] fullColor = frame.FullColorBgra;
                float[] mapX = frame.DepthToColorX, mapY = frame.DepthToColorY;
                if (fullColor == null)
                {
                    colorWidth = colorHeight = 0;
                    if (mapX != null || mapY != null) throw new InvalidDataException("Mapa RGB sin imagen original.");
                }
                else if (colorWidth < 1 || colorHeight < 1 || fullColor.Length != checked(colorWidth * colorHeight * 4) ||
                         mapX == null || mapY == null || mapX.Length != frame.Width * frame.Height || mapY.Length != mapX.Length)
                    throw new InvalidDataException("RGB original o mapa de color incompatible.");
                writer.Write(colorWidth);
                writer.Write(colorHeight);
                writer.Write(fullColor == null ? 0 : fullColor.Length);
                if (fullColor != null) writer.Write(fullColor);
                writer.Write(mapX == null ? 0 : mapX.Length);
                if (mapX != null)
                    for (int i = 0; i < mapX.Length; i++) { writer.Write(mapX[i]); writer.Write(mapY[i]); }
            }
            FrameCount++;
        }

        public void Dispose() { writer.Dispose(); }
    }

    public sealed class SessionReader : IDisposable
    {
        private readonly BinaryReader reader;
        private readonly bool qualityColor;
        public StreamKind Stream { get; private set; }
        public DateTime StartedUtc { get; private set; }
        public string Format { get; private set; }

        public SessionReader(string path)
        {
            reader = new BinaryReader(new GZipStream(new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read), CompressionMode.Decompress));
            try
            {
                string format = reader.ReadString();
                if (format != "KINECT_HOARD_SESSION_1" && format != "KINECT_HOARD_SESSION_2")
                    throw new InvalidDataException("Archivo de sesión desconocido.");
                Format = format;
                qualityColor = format == "KINECT_HOARD_SESSION_2";
                int stream = reader.ReadInt32();
                if (!Enum.IsDefined(typeof(StreamKind), stream)) throw new InvalidDataException("Flujo de sesión desconocido.");
                Stream = (StreamKind)stream;
                StartedUtc = new DateTime(reader.ReadInt64(), DateTimeKind.Utc);
            }
            catch { reader.Dispose(); throw; }
        }

        public bool TryRead(out CameraFrame frame)
        {
            frame = null;
            byte marker;
            try { marker = reader.ReadByte(); }
            catch (EndOfStreamException) { return false; }
            if (marker != 1) throw new InvalidDataException("Fotograma de sesión corrupto.");
            long ticks = reader.ReadInt64();
            if (ticks < DateTime.MinValue.Ticks || ticks > DateTime.MaxValue.Ticks) throw new InvalidDataException("Fecha de fotograma no válida.");
            int width = reader.ReadInt32(), height = reader.ReadInt32();
            if (width < 1 || height < 1 || (long)width * height > 8000000) throw new InvalidDataException("Dimensiones de fotograma no válidas.");
            int pixelLength = reader.ReadInt32();
            if (pixelLength != width * height * 4) throw new InvalidDataException("Longitud de imagen no válida.");
            byte[] pixels = reader.ReadBytes(pixelLength);
            if (pixels.Length != pixelLength) throw new EndOfStreamException("Imagen incompleta.");
            int valueCount = reader.ReadInt32();
            if (valueCount < 0 || valueCount > width * height) throw new InvalidDataException("Número de muestras no válido.");
            ushort[] values = valueCount == 0 ? null : new ushort[valueCount];
            if (values != null) for (int i = 0; i < values.Length; i++) values[i] = reader.ReadUInt16();
            int bodyCount = reader.ReadInt32();
            if (bodyCount < 0 || bodyCount > 6) throw new InvalidDataException("Número de cuerpos no válido.");
            TrackedBody[] bodies = Stream == StreamKind.Skeleton ? new TrackedBody[bodyCount] : null;
            for (int i = 0; i < bodyCount; i++)
            {
                ulong id = reader.ReadUInt64();
                int jointCount = reader.ReadInt32();
                if (jointCount < 0 || jointCount > 64) throw new InvalidDataException("Número de articulaciones no válido.");
                var joints = new BodyJoint[jointCount];
                for (int j = 0; j < jointCount; j++)
                    joints[j] = new BodyJoint {
                        Name = reader.ReadString(), X = reader.ReadSingle(), Y = reader.ReadSingle(), Z = reader.ReadSingle(),
                        DepthX = reader.ReadSingle(), DepthY = reader.ReadSingle(), TrackingState = reader.ReadInt32()
                    };
                if (bodies != null) bodies[i] = new TrackedBody { TrackingId = id, Joints = joints };
            }
            int fullWidth = 0, fullHeight = 0;
            byte[] fullColor = null;
            float[] mapX = null, mapY = null;
            if (qualityColor)
            {
                fullWidth = reader.ReadInt32(); fullHeight = reader.ReadInt32();
                int colorLength = reader.ReadInt32();
                if (colorLength < 0 || colorLength > 32_000_000 ||
                    (colorLength == 0 ? fullWidth != 0 || fullHeight != 0 :
                    fullWidth < 1 || fullHeight < 1 || (long)fullWidth * fullHeight * 4 != colorLength))
                    throw new InvalidDataException("RGB original inválido.");
                if (colorLength > 0)
                {
                    fullColor = reader.ReadBytes(colorLength);
                    if (fullColor.Length != colorLength) throw new EndOfStreamException("RGB original incompleto.");
                }
                int mapCount = reader.ReadInt32();
                if (mapCount != 0 && mapCount != width * height || (mapCount == 0) != (colorLength == 0))
                    throw new InvalidDataException("Mapa RGB original inválido.");
                if (mapCount > 0)
                {
                    mapX = new float[mapCount]; mapY = new float[mapCount];
                    for (int i = 0; i < mapCount; i++) { mapX[i] = reader.ReadSingle(); mapY[i] = reader.ReadSingle(); }
                }
            }
            frame = new CameraFrame { Kind = Stream, Width = width, Height = height, Bgra = pixels, Values = values,
                Bodies = bodies, TimestampUtc = new DateTime(ticks, DateTimeKind.Utc), FullColorWidth = fullWidth,
                FullColorHeight = fullHeight, FullColorBgra = fullColor, DepthToColorX = mapX, DepthToColorY = mapY };
            return true;
        }

        public void Dispose() { reader.Dispose(); }
    }
}
