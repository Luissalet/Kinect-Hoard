using System;
using System.IO;

namespace KinectHoard.Core
{
    public interface IAudioBackend : IDisposable
    {
        string Detail { get; }
        void Open();
        bool TryRead(out AudioChunk chunk);
        void Close();
    }

    [Serializable]
    public sealed class AudioChunk
    {
        // Little-endian IEEE float32, mono, 16000 samples per second.
        public byte[] PcmFloat32 { get; set; }
        public float BeamAngleRadians { get; set; }
        public float BeamConfidence { get; set; }
        public DateTime TimestampUtc { get; set; }
    }

    public sealed class FloatWaveWriter : IDisposable
    {
        private readonly FileStream stream;
        private readonly BinaryWriter writer;
        private int dataBytes;

        public FloatWaveWriter(string path)
        {
            stream = File.Create(path);
            writer = new BinaryWriter(stream);
            writer.Write(new[] { (byte)'R', (byte)'I', (byte)'F', (byte)'F' });
            writer.Write(0);
            writer.Write(new[] { (byte)'W', (byte)'A', (byte)'V', (byte)'E' });
            writer.Write(new[] { (byte)'f', (byte)'m', (byte)'t', (byte)' ' });
            writer.Write(16);
            writer.Write((ushort)3); // WAVE_FORMAT_IEEE_FLOAT
            writer.Write((ushort)1);
            writer.Write(16000);
            writer.Write(64000);
            writer.Write((ushort)4);
            writer.Write((ushort)32);
            writer.Write(new[] { (byte)'d', (byte)'a', (byte)'t', (byte)'a' });
            writer.Write(0);
        }

        public int DataBytes { get { return dataBytes; } }

        public void Write(AudioChunk chunk)
        {
            if (chunk == null || chunk.PcmFloat32 == null || chunk.PcmFloat32.Length % 4 != 0)
                throw new ArgumentException("Bloque de audio no válido.");
            writer.Write(chunk.PcmFloat32);
            dataBytes = checked(dataBytes + chunk.PcmFloat32.Length);
        }

        public void Dispose()
        {
            stream.Position = 4;
            writer.Write(checked(36 + dataBytes));
            stream.Position = 40;
            writer.Write(dataBytes);
            writer.Dispose();
        }
    }
}
