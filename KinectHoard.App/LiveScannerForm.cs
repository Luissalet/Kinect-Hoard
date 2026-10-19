using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace KinectHoard.App
{
    internal static class ScannerExport
    {
        internal static string Root()
        {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            if (!File.Exists(Path.Combine(root, "fusion.py")) && !File.Exists(Path.Combine(root, "KinectHoard.Fusion.exe")))
                root = Path.GetFullPath(Path.Combine(root, "..", "..", "..", ".."));
            return root;
        }

        internal static void Texture(string directory)
        {
            string root = Root();
            string python = Path.Combine(root, ".venv-scan", "Scripts", "python.exe");
            string bundled = Path.Combine(root, "KinectHoard.Fusion.exe");
            bool source = File.Exists(python) && File.Exists(Path.Combine(root, "quality_scan.py"));
            if (!source && !File.Exists(bundled)) throw new FileNotFoundException("Falta el motor de texturas; ejecuta setup-scan.ps1.");
            var start = new ProcessStartInfo {
                FileName = source ? python : bundled,
                Arguments = (source ? "\"" + Path.Combine(root, "quality_scan.py") + "\" " : "") + "--texture-live \"" + directory + "\"",
                WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden, RedirectStandardOutput = true, RedirectStandardError = true
            };
            using (var process = Process.Start(start))
            {
                var stdout = process.StandardOutput.ReadToEndAsync();
                var stderr = process.StandardError.ReadToEndAsync();
                process.WaitForExit(); Task.WaitAll(stdout, stderr);
                File.WriteAllText(Path.Combine(directory, "texture.log"), stdout.Result + stderr.Result);
                if (process.ExitCode != 0) throw new InvalidOperationException(stderr.Result.Trim());
            }
        }
    }

    internal sealed class LiveScannerForm : Form
    {
        private readonly ComboBox mode = Choice(220, "Cámara móvil", "Cámara fija");
        private readonly ComboBox camera = Choice(155, "Kinect 360", "Kinect One");
        private readonly ComboBox target = Choice(140, "Persona", "Objeto");
        private readonly PictureBox preview = View(), surface = View();
        private readonly Label status = new Label { Dock = DockStyle.Fill, AutoEllipsis = true, Padding = new Padding(12, 10, 8, 0) };
        private readonly Label instructions = new Label { Dock = DockStyle.Fill, Padding = new Padding(12, 7, 8, 0) };
        private readonly Button connect = Button("Conectar"), start = Button("Iniciar"), pause = Button("Pausar"), finish = Button("Finalizar"), open = Button("Abrir OBJ"), follow = Button("Vista de cámara");
        private readonly Timer timer = new Timer { Interval = 150 };
        private FusionScanner scanner;
        private Task server;
        private byte[] lastPreview, lastSurface;
        private Point drag;
        private bool closing;
        private bool settingsDirty;

        private readonly int port;
        internal LiveScannerForm(string initialMode = "fixed", string initialModel = "one", string initialTarget = "person", int port = 64320)
        {
            this.port = port;
            Text = "Kinect Hoard · escáner en directo";
            ClientSize = new Size(1350, 780); MinimumSize = new Size(990, 600);
            BackColor = Color.FromArgb(22, 25, 31); ForeColor = Color.WhiteSmoke; Font = new Font("Segoe UI", 10);
            var layout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 5 };
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 52));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 49));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
            var setup = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(10, 8, 0, 0), BackColor = Color.FromArgb(31, 35, 43), WrapContents = false };
            setup.Controls.AddRange(new Control[] { mode, camera, target, connect });
            var actions = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(10, 7, 0, 0), WrapContents = false };
            actions.Controls.AddRange(new Control[] { start, pause, finish, follow, open });
            start.BackColor = Color.FromArgb(122, 218, 196); start.ForeColor = Color.FromArgb(15, 25, 27);
            var views = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 2, Padding = new Padding(10, 0, 10, 0) };
            views.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 36)); views.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 64));
            views.RowStyles.Add(new RowStyle(SizeType.Absolute, 30)); views.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            views.Controls.Add(new Label { Text = "Cámara · pulsa sobre el objeto para seleccionarlo", Dock = DockStyle.Fill, AutoEllipsis = true }, 0, 0);
            views.Controls.Add(new Label { Text = "Superficie en directo · arrastra para girar la vista", Dock = DockStyle.Fill }, 1, 0);
            views.Controls.Add(preview, 0, 1); views.Controls.Add(surface, 1, 1);
            status.BackColor = Color.FromArgb(31, 35, 43);
            layout.Controls.Add(setup, 0, 0); layout.Controls.Add(actions, 0, 1); layout.Controls.Add(views, 0, 2); layout.Controls.Add(status, 0, 3); layout.Controls.Add(instructions, 0, 4);
            Controls.Add(layout);
            mode.SelectedIndex = initialMode == "fixed" ? 1 : 0;
            camera.SelectedIndex = initialModel == "one" ? 1 : 0;
            target.SelectedIndex = initialTarget == "object" ? 1 : 0;
            mode.SelectedIndexChanged += (s, e) => { camera.SelectedIndex = mode.SelectedIndex == 0 ? 0 : 1; settingsDirty = true; Instruction(); };
            camera.SelectedIndexChanged += (s, e) => settingsDirty = true;
            target.SelectedIndexChanged += (s, e) => { settingsDirty = true; Instruction(); };
            connect.Click += async (s, e) => await Connect();
            start.Click += (s, e) => scanner?.Command("start");
            pause.Click += (s, e) => scanner?.Command("pause");
            finish.Click += (s, e) => scanner?.Command("finish");
            follow.Click += (s, e) => scanner?.Command("follow");
            open.Click += (s, e) => {
                string path = scanner == null ? null : Path.Combine(scanner.DirectoryPath, "scan.obj");
                if (path != null && File.Exists(path))
                {
                    string root = ScannerExport.Root(), python = Path.Combine(root, ".venv-scan", "Scripts", "pythonw.exe");
                    bool source = File.Exists(python);
                    try { Process.Start(new ProcessStartInfo {
                        FileName = source ? python : Path.Combine(root, "KinectHoard.Fusion.exe"),
                        Arguments = (source ? "\"" + Path.Combine(root, "fusion.py") + "\" " : "") + "--view \"" + path + "\"", UseShellExecute = false
                    }); } catch (Exception ex) { status.Text = ex.Message; }
                }
            };
            preview.MouseClick += (s, e) => {
                if (scanner == null || preview.Image == null) return;
                double scale = Math.Min((double)preview.ClientSize.Width / preview.Image.Width, (double)preview.ClientSize.Height / preview.Image.Height);
                double w = preview.Image.Width * scale, h = preview.Image.Height * scale;
                double u = (e.X - (preview.ClientSize.Width - w) / 2) / w, v = (e.Y - (preview.ClientSize.Height - h) / 2) / h;
                if (u >= 0 && u <= 1 && v >= 0 && v <= 1) scanner.Command("select", u, v);
            };
            surface.MouseDown += (s, e) => { if (e.Button == MouseButtons.Left) drag = e.Location; };
            surface.MouseMove += (s, e) => { if (e.Button == MouseButtons.Left) { scanner?.Command("orbit", (e.X - drag.X) * .008, (e.Y - drag.Y) * .008); drag = e.Location; } };
            timer.Tick += (s, e) => RefreshScan();
            Shown += async (s, e) => { Instruction(); timer.Start(); await Connect(); };
            FormClosing += async (s, e) => {
                if (closing) return;
                e.Cancel = true; closing = true; timer.Stop(); await Stop();
                preview.Image?.Dispose(); surface.Image?.Dispose(); Close();
            };
        }

        private static ComboBox Choice(int width, params object[] choices) { var box = new ComboBox { Width = width, DropDownStyle = ComboBoxStyle.DropDownList, Margin = new Padding(0, 0, 9, 0) }; box.Items.AddRange(choices); return box; }
        private static Button Button(string text) { return new Button { Text = text, AutoSize = true, Height = 32, FlatStyle = FlatStyle.Flat, Margin = new Padding(0, 0, 9, 0), Padding = new Padding(8, 0, 8, 0), BackColor = Color.FromArgb(38, 44, 54), ForeColor = Color.WhiteSmoke }; }
        private static PictureBox View() { return new PictureBox { Dock = DockStyle.Fill, SizeMode = PictureBoxSizeMode.Zoom, BackColor = Color.FromArgb(12, 15, 19), Margin = new Padding(0, 0, 8, 0) }; }
        private void Instruction() { instructions.Text = mode.SelectedIndex == 0 ? "Mueve la Kinect alrededor de la persona o del objeto. Conserva alguna zona ya vista entre movimientos." : "Deja la cámara en el trípode y gira la persona o el objeto delante de ella. No hace falta un eje de giro fijo."; }

        private async Task Connect()
        {
            connect.Enabled = false;
            try
            {
                await Stop();
                string directory = Path.Combine(ScannerExport.Root(), "captures", "live-" + DateTime.Now.ToString("yyyyMMdd-HHmmss-fff"));
                scanner = new FusionScanner(camera.SelectedIndex == 0 ? "360" : "one", mode.SelectedIndex == 0 ? "moving" : "fixed", target.SelectedIndex == 0 ? "person" : "object", directory);
                settingsDirty = false;
                var session = scanner;
                server = Task.Run(() => {
                    try { int result = CameraStreamServer.Run(port, KinectHoard.Core.StreamKind.ColorDepth, 0, session.Model, true, session); if (result != 0) session.SetError("El puerto " + port + " está ocupado. Reconecta la cámara."); }
                    catch (Exception ex) { session.SetError(ex.GetBaseException().Message); }
                });
            }
            finally { connect.Enabled = true; }
        }

        private async Task Stop()
        {
            if (server == null) return;
            try { using (var client = new WebClient()) await client.UploadStringTaskAsync("http://127.0.0.1:" + port + "/api/stop", "POST", ""); } catch (WebException) { }
            await server; server = null;
        }

        private void RefreshScan()
        {
            if (scanner == null) return;
            var json = new JavaScriptSerializer().Serialize(scanner.Status());
            var value = new JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string, object>>(json);
            string state = (string)value["state"];
            if (state == "closed" && !closing) { Close(); return; }
            status.Text = settingsDirty ? "Pulsa Aplicar ajustes para abrir la cámara y el modo seleccionados." :
                (string)value["detail"] + "   ·   " + Convert.ToDouble(value["fps"]).ToString("0.0") + " fps";
            bool busy = state == "scanning" || state == "tracking_lost" || state == "exporting";
            mode.Enabled = camera.Enabled = target.Enabled = !busy;
            connect.Enabled = !busy;
            connect.Text = settingsDirty ? "Aplicar ajustes" : "Nueva toma";
            start.Enabled = !settingsDirty && !busy && state != "finished" && state != "error";
            pause.Enabled = state == "scanning" || state == "tracking_lost";
            finish.Enabled = Convert.ToInt32(value["frames_integrated"]) > 0 && state != "exporting" && state != "finished";
            open.Enabled = state == "finished";
            SetImage(preview, scanner.Preview(false), ref lastPreview);
            SetImage(surface, scanner.Preview(true), ref lastSurface);
        }

        private static void SetImage(PictureBox view, byte[] png, ref byte[] previous)
        {
            if (png == null || ReferenceEquals(png, previous)) return;
            previous = png;
            using (var stream = new MemoryStream(png))
            using (var image = Image.FromStream(stream))
            { var old = view.Image; view.Image = new Bitmap(image); old?.Dispose(); }
        }
    }
}
