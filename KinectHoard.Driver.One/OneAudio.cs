using System;
using System.IO;
using KinectHoard.Core;
using Microsoft.Kinect;

namespace KinectHoard.Driver.One
{
    public sealed class OneAudio : MarshalByRefObject, IAudioBackend
    {
        private KinectSensor sensor;
        private AudioBeam beam;
        private Stream audioStream;
        public string Detail
        {
            get { return sensor == null ? "Sensor cerrado" : "sensor_available=" + sensor.IsAvailable + ", audio_active=" + sensor.AudioSource.IsActive + ", beams=" + sensor.AudioSource.AudioBeams.Count; }
        }

        public void Open()
        {
            Close();
            sensor = KinectSensor.GetDefault();
            if (sensor == null) throw new InvalidOperationException("Kinect One no encontrada.");
            try
            {
                sensor.Open();
                if (sensor.AudioSource.AudioBeams.Count == 0) throw new IOException("El sensor no expone haces de audio.");
                beam = sensor.AudioSource.AudioBeams[0];
                audioStream = beam.OpenInputStream();
                if (audioStream == null) throw new IOException("No se pudo abrir el micrófono Kinect.");
            }
            catch { Close(); throw; }
        }

        public bool TryRead(out AudioChunk chunk)
        {
            chunk = null;
            if (audioStream == null) return false;
            var bytes = new byte[8192];
            int count = audioStream.Read(bytes, 0, bytes.Length);
            if (count <= 0) return false;
            if ((count & 3) != 0) throw new IOException("El audio Kinect no está alineado a muestras float32.");
            if (count != bytes.Length) Array.Resize(ref bytes, count);
            chunk = new AudioChunk {
                PcmFloat32 = bytes, BeamAngleRadians = beam.BeamAngle,
                BeamConfidence = beam.BeamAngleConfidence, TimestampUtc = DateTime.UtcNow
            };
            return true;
        }

        public void Close()
        {
            if (audioStream != null) { audioStream.Dispose(); audioStream = null; }
            beam = null;
            if (sensor != null) { if (sensor.IsOpen) sensor.Close(); sensor = null; }
        }

        public void Dispose() { Close(); }
        public override object InitializeLifetimeService() { return null; }
    }
}
