using System;
using System.IO;
using System.IO.Compression;

namespace KinectHoard.Core
{
    // Sequential gzip archive: portable between sensors and readable without a connected Kinect.
    public sealed class SessionWriter : IDisposable
    {
        private readonly BinaryWriter writer;
        public int FrameCount { get; private set; }
        public StreamKind Stream { get; private set; }

        public SessionWriter(string path, StreamKind stream)
        {
            Stream = stream;
            writer = new BinaryWriter(new GZipStream(new FileStream(path, FileMode.Create, FileAccess.Write), CompressionMode.Compress));
            writer.Write("KINECT_HOARD_SESSION_1");
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
            FrameCount++;
        }

        public void Dispose() { writer.Dispose(); }
    }

    public sealed class SessionReader : IDisposable
    {
        private readonly BinaryReader reader;
        public StreamKind Stream { get; private set; }
        public DateTime StartedUtc { get; private set; }

        public SessionReader(string path)
        {
            reader = new BinaryReader(new GZipStream(new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read), CompressionMode.Decompress));
            try
            {
                if (reader.ReadString() != "KINECT_HOARD_SESSION_1") throw new InvalidDataException("Archivo de sesión desconocido.");
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
            frame = new CameraFrame { Kind = Stream, Width = width, Height = height, Bgra = pixels, Values = values, Bodies = bodies, TimestampUtc = new DateTime(ticks, DateTimeKind.Utc) };
            return true;
        }

        public void Dispose() { reader.Dispose(); }
    }
}
