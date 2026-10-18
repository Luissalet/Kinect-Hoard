using System;
using System.Drawing;
using System.Linq;
using System.Windows.Forms;
using KinectHoard.Core;

namespace KinectHoard.App
{
    // Both games consume the same right-hand pointer from Skeleton frames.
    // Mouse and keyboard input make the rules testable without a person in view.
    internal sealed class InteractionGallery : Form
    {
        private readonly TabControl tabs = new TabControl { Dock = DockStyle.Fill };
        private readonly Label message = new Label { Dock = DockStyle.Bottom, Height = 56, TextAlign = ContentAlignment.MiddleCenter };
        private readonly Label pointer = new Label { Width = 20, Height = 20, BackColor = Color.Turquoise, Visible = false };
        private readonly Button[] shapeButtons = new Button[3];
        private readonly Button[] boardButtons = new Button[9];
        private readonly Button[] adaptiveButtons = new Button[3];
        private readonly Label distanceLabel = new Label { Dock = DockStyle.Top, Height = 115, TextAlign = ContentAlignment.MiddleCenter };
        private readonly Label target = new Label { Dock = DockStyle.Top, Height = 75, TextAlign = ContentAlignment.MiddleCenter };
        private readonly Random random = new Random();
        private readonly char[] board = new char[9];
        private readonly string[] shapes = { "●", "■", "▲" };
        private Button hover;
        private DateTime hoverSince;
        private DateTime cooldownUntil;
        private int targetShape;
        private int score;
        private bool gameOver;
        private int distanceBucket = -1;

        internal InteractionGallery()
        {
            Text = "Kinect Hoard · Galería de interacción";
            ClientSize = new Size(820, 650);
            MinimumSize = new Size(620, 500);
            Font = new Font("Segoe UI", 12);
            BackColor = Color.FromArgb(26, 30, 37);
            ForeColor = Color.WhiteSmoke;
            KeyPreview = true;
            message.Text = "Sitúa la mano derecha sobre un botón durante 1,2 s. También puedes usar ratón o teclado.";
            var shapePage = new TabPage("ShapeGame") { BackColor = BackColor, ForeColor = ForeColor };
            var boardPage = new TabPage("TicTacToe") { BackColor = BackColor, ForeColor = ForeColor };
            var adaptivePage = new TabPage("AdaptiveUI") { BackColor = BackColor, ForeColor = ForeColor };
            var shapeLayout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 2, Padding = new Padding(26) };
            shapeLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 100));
            shapeLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            for (int i = 0; i < 3; i++) shapeLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100 / 3f));
            target.Font = new Font("Segoe UI", 22, FontStyle.Bold);
            shapeLayout.Controls.Add(target, 0, 0);
            shapeLayout.SetColumnSpan(target, 3);
            for (int i = 0; i < 3; i++)
            {
                int index = i;
                shapeButtons[i] = GameButton(shapes[i], 50);
                shapeButtons[i].Click += (s, e) => SelectShape(index);
                shapeLayout.Controls.Add(shapeButtons[i], i, 1);
            }
            shapePage.Controls.Add(shapeLayout);
            var boardLayout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 3, Padding = new Padding(80, 20, 80, 20) };
            for (int i = 0; i < 3; i++)
            {
                boardLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100 / 3f));
                boardLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100 / 3f));
            }
            for (int i = 0; i < 9; i++)
            {
                int index = i;
                boardButtons[i] = GameButton("", 42);
                boardButtons[i].Click += (s, e) => SelectCell(index);
                boardLayout.Controls.Add(boardButtons[i], i % 3, i / 3);
            }
            boardPage.Controls.Add(boardLayout);
            var adaptivePanel = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(28), AutoScroll = true };
            string[] actions = { "Color", "Profundidad", "Infrarrojos" };
            for (int i = 0; i < adaptiveButtons.Length; i++)
            {
                string action = actions[i];
                adaptiveButtons[i] = GameButton(action, 20);
                adaptiveButtons[i].Dock = DockStyle.None;
                adaptiveButtons[i].Click += (s, e) => { message.Text = "AdaptiveUI: seleccionaste " + action + "."; };
                adaptivePanel.Controls.Add(adaptiveButtons[i]);
            }
            distanceLabel.Font = new Font("Segoe UI", 17, FontStyle.Bold);
            distanceLabel.Text = "Acércate o aléjate: los controles cambian de tamaño según tu distancia.";
            adaptivePage.Controls.Add(adaptivePanel);
            adaptivePage.Controls.Add(distanceLabel);
            tabs.TabPages.Add(shapePage);
            tabs.TabPages.Add(boardPage);
            tabs.TabPages.Add(adaptivePage);
            ResizeAdaptiveControls(1, 0);
            var footer = new FlowLayoutPanel { Dock = DockStyle.Bottom, Height = 45 };
            var reset = GameButton("Reiniciar juego", 12);
            reset.AutoSize = true;
            reset.Click += (s, e) => ResetCurrent();
            footer.Controls.Add(reset);
            Controls.Add(tabs);
            Controls.Add(message);
            Controls.Add(footer);
            Controls.Add(pointer);
            pointer.BringToFront();
            tabs.SelectedIndexChanged += (s, e) => { hover = null; ResetCurrent(); };
            KeyDown += (s, e) =>
            {
                if (e.KeyCode == Keys.R) { ResetCurrent(); e.Handled = true; }
                if (e.KeyCode == Keys.D1) { tabs.SelectedIndex = 0; e.Handled = true; }
                if (e.KeyCode == Keys.D2) { tabs.SelectedIndex = 1; e.Handled = true; }
                if (e.KeyCode == Keys.D3) { tabs.SelectedIndex = 2; e.Handled = true; }
            };
            NextShape();
        }

        private static Button GameButton(string text, int fontSize)
        {
            return new Button { Text = text, Dock = DockStyle.Fill, Margin = new Padding(6),
                Font = new Font("Segoe UI", fontSize, FontStyle.Bold),
                BackColor = Color.FromArgb(48, 65, 78), ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat, TabStop = true };
        }

        internal void Consume(CameraFrame frame)
        {
            if (IsDisposed || frame == null || frame.Kind != StreamKind.Skeleton) return;
            BodyJoint hand = null;
            BodyJoint head = null;
            foreach (var body in frame.Bodies ?? new TrackedBody[0])
            {
                hand = body.Joints == null ? null : body.Joints.FirstOrDefault(j => j.Name == "HandRight" && j.TrackingState == 2);
                head = body.Joints == null ? null : body.Joints.FirstOrDefault(j => j.Name == "Head" && j.TrackingState == 2);
                if (hand != null || head != null) break;
            }
            if (head != null && head.Z > 0 && head.Z < 8)
            {
                int bucket = head.Z < 1.6f ? 0 : head.Z < 2.8f ? 1 : 2;
                ResizeAdaptiveControls(bucket, head.Z);
            }
            if (hand == null || float.IsNaN(hand.DepthX) || float.IsNaN(hand.DepthY) ||
                hand.DepthX < 0 || hand.DepthY < 0 || hand.DepthX >= frame.Width || hand.DepthY >= frame.Height)
            { pointer.Visible = false; hover = null; return; }
            var location = new Point((int)(hand.DepthX * ClientSize.Width / frame.Width),
                                     (int)(hand.DepthY * ClientSize.Height / frame.Height));
            pointer.Location = new Point(location.X - 10, location.Y - 10);
            pointer.Visible = true;
            pointer.BringToFront();
            var screenPoint = PointToScreen(location);
            Button candidate = (tabs.SelectedIndex == 0 ? shapeButtons : tabs.SelectedIndex == 1 ? boardButtons : adaptiveButtons)
                .FirstOrDefault(b => b.RectangleToScreen(b.ClientRectangle).Contains(screenPoint));
            DateTime now = DateTime.UtcNow;
            if (candidate != hover) { hover = candidate; hoverSince = now; }
            if (candidate != null && now >= cooldownUntil && (now - hoverSince).TotalSeconds >= 1.2)
            {
                candidate.PerformClick();
                cooldownUntil = now.AddMilliseconds(800);
                hoverSince = now;
            }
        }

        private void ResizeAdaptiveControls(int bucket, float metres)
        {
            if (bucket != distanceBucket)
            {
                distanceBucket = bucket;
                int size = bucket == 0 ? 190 : bucket == 1 ? 250 : 350;
                int font = bucket == 0 ? 20 : bucket == 1 ? 24 : 30;
                foreach (var button in adaptiveButtons)
                {
                    button.Size = new Size(size, 145);
                    var previousFont = button.Font;
                    button.Font = new Font("Segoe UI", font, FontStyle.Bold);
                    previousFont.Dispose();
                }
            }
            distanceLabel.Text = metres <= 0
                ? "Acércate o aléjate: los controles cambian de tamaño según tu distancia."
                : "Distancia de cabeza: " + metres.ToString("0.00") + " m · tamaño " +
                  (bucket == 0 ? "cercano" : bucket == 1 ? "medio" : "lejano");
        }

        private void NextShape()
        {
            targetShape = random.Next(shapes.Length);
            target.Text = "Encuentra " + shapes[targetShape] + "  ·  aciertos: " + score;
        }

        private void SelectShape(int index)
        {
            if (index == targetShape) { score++; message.Text = "¡Bien! Sigue con la siguiente figura."; }
            else message.Text = "Esa no es la figura pedida. Inténtalo de nuevo.";
            NextShape();
        }

        private void SelectCell(int index)
        {
            if (gameOver || board[index] != '\0') return;
            board[index] = 'X';
            boardButtons[index].Text = "X";
            if (FinishIfWon('X')) return;
            int computer = BestMove();
            if (computer < 0) { gameOver = true; message.Text = "Empate. Pulsa Reiniciar juego."; return; }
            board[computer] = 'O';
            boardButtons[computer].Text = "O";
            FinishIfWon('O');
        }

        private int BestMove()
        {
            for (int player = 0; player < 2; player++)
                for (int i = 0; i < 9; i++)
                    if (board[i] == '\0')
                    {
                        board[i] = player == 0 ? 'O' : 'X';
                        bool win = HasWon(board[i]);
                        board[i] = '\0';
                        if (win) return i;
                    }
            if (board[4] == '\0') return 4;
            for (int i = 0; i < 9; i++) if (board[i] == '\0') return i;
            return -1;
        }

        private bool FinishIfWon(char player)
        {
            if (HasWon(player))
            {
                gameOver = true;
                message.Text = player == 'X' ? "Ganaste. Pulsa Reiniciar juego." : "Gana el ordenador. Pulsa Reiniciar juego.";
                return true;
            }
            if (board.All(c => c != '\0')) { gameOver = true; message.Text = "Empate. Pulsa Reiniciar juego."; return true; }
            message.Text = "Tu turno: coloca X con la mano derecha, el ratón o el teclado.";
            return false;
        }

        private bool HasWon(char c)
        {
            int[,] lines = { { 0, 1, 2 }, { 3, 4, 5 }, { 6, 7, 8 },
                             { 0, 3, 6 }, { 1, 4, 7 }, { 2, 5, 8 },
                             { 0, 4, 8 }, { 2, 4, 6 } };
            for (int i = 0; i < 8; i++)
                if (board[lines[i, 0]] == c && board[lines[i, 1]] == c && board[lines[i, 2]] == c) return true;
            return false;
        }

        private void ResetCurrent()
        {
            if (tabs.SelectedIndex == 0) { score = 0; NextShape(); }
            else if (tabs.SelectedIndex == 1)
            {
                Array.Clear(board, 0, board.Length);
                foreach (var button in boardButtons) button.Text = "";
                gameOver = false;
            }
            else distanceLabel.Text = "Acércate o aléjate: los controles cambian de tamaño según tu distancia.";
            message.Text = "Sitúa la mano derecha sobre un botón durante 1,2 s. Ratón y teclado también funcionan.";
        }
    }
}
