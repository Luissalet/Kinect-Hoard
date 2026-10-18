using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using KinectHoard.Core;

namespace KinectHoard.App
{
    internal sealed class AudioMonitorForm : Form
    {
        private readonly ProgressBar level = new ProgressBar { Minimum = 0, Maximum = 100, Dock = DockStyle.Top, Height = 32 };
        private readonly Label levelText = new Label { Dock = DockStyle.Top, Height = 45, TextAlign = ContentAlignment.MiddleCenter };
        private readonly Label beamText = new Label { Dock = DockStyle.Top, Height = 54, TextAlign = ContentAlignment.MiddleCenter };
        private readonly Label state = new Label { Dock = DockStyle.Bottom, Height = 48, TextAlign = ContentAlignment.MiddleCenter };
        private readonly BeamView beam = new BeamView { Dock = DockStyle.Fill };
        private volatile bool stopping;

        internal AudioMonitorForm()
        {
            Text = "Kinect Hoard · Explorador de audio";
            ClientSize = new Size(620, 330);
            MinimumSize = new Size(460, 280);
            Font = new Font("Segoe UI", 12);
            BackColor = Color.FromArgb(25, 30, 38);
            ForeColor = Color.WhiteSmoke;
            levelText.Text = "Nivel: esperando muestras de la Kinect One...";
            beamText.Text = "Dirección del haz: esperando...";
            state.Text = "Abriendo micrófono de la Kinect One...";
            var layout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 5 };
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 45));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 32));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 54));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 48));
            layout.Controls.Add(levelText, 0, 0);
            layout.Controls.Add(level, 0, 1);
            layout.Controls.Add(beamText, 0, 2);
            layout.Controls.Add(beam, 0, 3);
            layout.Controls.Add(state, 0, 4);
            Controls.Add(layout);
            Shown += (s, e) => Task.Run(() => Monitor());
            FormClosing += (s, e) => stopping = true;
        }

        private void Monitor()
        {
            while (!stopping)
            {
                try
                {
                    using (var input = Program.LoadAudioBackend())
                    {
                        input.Open();
                        Post(() => state.Text = "Micrófono activo · float32 mono, 16 kHz");
                        while (!stopping)
                        {
                            AudioChunk chunk;
                            if (!input.TryRead(out chunk)) { Thread.Sleep(30); continue; }
                            var data = chunk.PcmFloat32;
                            double sum = 0;
                            for (int i = 0; i + 3 < data.Length; i += 4)
                            {
                                float sample = BitConverter.ToSingle(data, i);
                                if (!float.IsNaN(sample) && !float.IsInfinity(sample)) sum += sample * sample;
                            }
                            double rms = Math.Sqrt(sum / Math.Max(1, data.Length / 4));
                            double decibels = 20 * Math.Log10(Math.Max(rms, 0.0000001));
                            int position = Math.Max(0, Math.Min(100, (int)((decibels + 60) * 100 / 60)));
                            float angle = chunk.BeamAngleRadians * 180f / (float)Math.PI;
                            float confidence = chunk.BeamConfidence;
                            Post(() => {
                                level.Value = position;
                                levelText.Text = "Nivel RMS: " + decibels.ToString("0.0") + " dBFS";
                                beamText.Text = "Dirección del haz: " + angle.ToString("+0.0;-0.0;0.0") +
                                    "° · confianza " + confidence.ToString("0.00");
                                beam.AngleDegrees = angle;
                                beam.Confidence = confidence;
                                beam.Invalidate();
                            });
                        }
                    }
                }
                catch (Exception ex)
                {
                    string message = ex.GetBaseException().Message;
                    Post(() => state.Text = "Audio interrumpido; reintentando: " + message);
                    for (int i = 0; i < 10 && !stopping; i++) Thread.Sleep(200);
                }
            }
        }

        private void Post(Action action)
        {
            if (stopping || IsDisposed || !IsHandleCreated) return;
            try { BeginInvoke(action); } catch (InvalidOperationException) { }
        }

        private sealed class BeamView : Panel
        {
            internal float AngleDegrees;
            internal float Confidence;

            internal BeamView() { BackColor = Color.FromArgb(17, 23, 35); DoubleBuffered = true; }

            protected override void OnPaint(PaintEventArgs e)
            {
                base.OnPaint(e);
                var g = e.Graphics;
                g.SmoothingMode = SmoothingMode.AntiAlias;
                float centerX = ClientSize.Width / 2f, centerY = ClientSize.Height * 0.78f;
                float radius = Math.Min(ClientSize.Width * 0.4f, ClientSize.Height * 0.75f);
                using (var guide = new Pen(Color.FromArgb(80, 95, 115), 2))
                {
                    g.DrawArc(guide, centerX - radius, centerY - radius, radius * 2, radius * 2, 180, 180);
                    g.DrawLine(guide, centerX, centerY, centerX, centerY - radius);
                }
                float angle = Math.Max(-50, Math.Min(50, AngleDegrees));
                float radians = angle * (float)Math.PI / 180f;
                float x = centerX + radius * (float)Math.Sin(radians);
                float y = centerY - radius * (float)Math.Cos(radians);
                int alpha = Math.Max(70, Math.Min(255, (int)(70 + Confidence * 185)));
                using (var pen = new Pen(Color.FromArgb(alpha, 74, 220, 199), 7) { EndCap = LineCap.ArrowAnchor })
                    g.DrawLine(pen, centerX, centerY, x, y);
                using (var brush = new SolidBrush(Color.WhiteSmoke))
                    g.FillEllipse(brush, centerX - 8, centerY - 8, 16, 16);
            }
        }
    }
}
