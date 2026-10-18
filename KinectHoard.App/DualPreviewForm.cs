using System;
using System.Drawing;
using System.Windows.Forms;
using KinectHoard.Core;

namespace KinectHoard.App
{
    // Each pane owns a separate backend. A failure or USB reconnect on one side
    // does not close the other reader.
    internal sealed class DualPreviewForm : Form
    {
        private readonly ICameraBackend[] cameras = new ICameraBackend[2];
        private readonly PictureBox[] previews = new PictureBox[2];
        private readonly ComboBox[] streams = new ComboBox[2];
        private readonly Label[] statuses = new Label[2];
        private readonly Bitmap[] images = new Bitmap[2];
        private readonly DateTime[] lastFrames = new DateTime[2];
        private readonly DateTime[] nextOpens = new DateTime[2];
        private readonly DateTime[] fpsSince = new DateTime[2];
        private readonly int[] frameCounts = new int[2];
        private readonly Timer timer = new Timer { Interval = 33 };
        private readonly string[] models = { "one", "360" };

        internal DualPreviewForm()
        {
            Text = "Kinect Hoard · ambas cámaras";
            ClientSize = new Size(1370, 680);
            MinimumSize = new Size(850, 430);
            BackColor = Color.FromArgb(22, 25, 31);
            ForeColor = Color.WhiteSmoke;
            Font = new Font("Segoe UI", 10);
            var grid = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1, Padding = new Padding(9) };
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
            Controls.Add(grid);
            for (int i = 0; i < 2; i++)
            {
                int index = i;
                var pane = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 3, BackColor = Color.FromArgb(31, 35, 43), Margin = new Padding(6) };
                pane.RowStyles.Add(new RowStyle(SizeType.Absolute, 45));
                pane.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
                pane.RowStyles.Add(new RowStyle(SizeType.Absolute, 50));
                var toolbar = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(9, 7, 0, 0) };
                toolbar.Controls.Add(new Label { Text = i == 0 ? "Kinect One" : "Kinect 360", AutoSize = true, Margin = new Padding(0, 4, 16, 0), Font = new Font("Segoe UI Semibold", 11) });
                streams[i] = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Width = 150 };
                streams[i].Items.AddRange(new object[] { "Color RGB", "Profundidad", "Infrarrojos" });
                streams[i].SelectedIndex = 0;
                streams[i].SelectedIndexChanged += (s, e) => { if (IsHandleCreated) { CloseCamera(index); nextOpens[index] = DateTime.MinValue; } };
                toolbar.Controls.Add(streams[i]);
                previews[i] = new PictureBox { Dock = DockStyle.Fill, SizeMode = PictureBoxSizeMode.Zoom, BackColor = Color.Black };
                statuses[i] = new Label { Dock = DockStyle.Fill, Text = "Buscando sensor...", AutoEllipsis = true, Padding = new Padding(10, 11, 5, 0) };
                pane.Controls.Add(toolbar, 0, 0);
                pane.Controls.Add(previews[i], 0, 1);
                pane.Controls.Add(statuses[i], 0, 2);
                grid.Controls.Add(pane, i, 0);
            }
            timer.Tick += (s, e) => Poll();
            Shown += (s, e) => timer.Start();
            FormClosed += (s, e) =>
            {
                timer.Stop();
                for (int i = 0; i < 2; i++) CloseCamera(i);
                timer.Dispose();
            };
        }

        private StreamKind SelectedStream(int i)
        {
            return streams[i].SelectedIndex == 1 ? StreamKind.Depth :
                streams[i].SelectedIndex == 2 ? StreamKind.Infrared : StreamKind.Color;
        }

        private void Poll()
        {
            for (int i = 0; i < 2; i++)
            {
                if (cameras[i] == null)
                {
                    if (DateTime.UtcNow >= nextOpens[i]) TryOpen(i);
                    continue;
                }
                try
                {
                    CameraFrame frame;
                    if (!cameras[i].TryRead(out frame))
                    {
                        if ((DateTime.UtcNow - lastFrames[i]).TotalSeconds > 3)
                        {
                            statuses[i].Text = "Sin fotogramas; reconectando " + models[i] + "...";
                            CloseCamera(i);
                            nextOpens[i] = DateTime.UtcNow.AddSeconds(2);
                        }
                        continue;
                    }
                    lastFrames[i] = DateTime.UtcNow;
                    var image = FrameImage.Create(frame);
                    previews[i].Image = image;
                    if (images[i] != null) images[i].Dispose();
                    images[i] = image;
                    frameCounts[i]++;
                    double elapsed = (DateTime.UtcNow - fpsSince[i]).TotalSeconds;
                    if (elapsed >= 1)
                    {
                        statuses[i].Text = frame.Width + "×" + frame.Height + " " + frame.Kind + " · " +
                            (frameCounts[i] / elapsed).ToString("0.0") + " fps · " + cameras[i].BackendName;
                        frameCounts[i] = 0;
                        fpsSince[i] = DateTime.UtcNow;
                    }
                }
                catch (Exception ex)
                {
                    statuses[i].Text = models[i] + ": " + ex.GetBaseException().Message;
                    CloseCamera(i);
                    nextOpens[i] = DateTime.UtcNow.AddSeconds(2);
                }
            }
        }

        private void TryOpen(int i)
        {
            nextOpens[i] = DateTime.UtcNow.AddSeconds(2);
            try
            {
                var usb = UsbDiscovery.GetStatus(models[i]);
                if (!usb.Usable) { statuses[i].Text = usb.Description; return; }
                cameras[i] = Program.LoadBackend(models[i]);
                if (i == 1 && !cameras[i].IsAvailable)
                    throw new InvalidOperationException(cameras[i].Detail);
                cameras[i].Open(SelectedStream(i));
                lastFrames[i] = fpsSince[i] = DateTime.UtcNow;
                frameCounts[i] = 0;
                statuses[i].Text = "Abierta; esperando fotogramas...";
            }
            catch (Exception ex)
            {
                statuses[i].Text = models[i] + ": " + ex.GetBaseException().Message;
                CloseCamera(i);
            }
        }

        private void CloseCamera(int i)
        {
            if (cameras[i] != null)
            {
                try { cameras[i].Dispose(); } catch { }
                cameras[i] = null;
            }
            previews[i].Image = null;
            if (images[i] != null) { images[i].Dispose(); images[i] = null; }
        }
    }
}
