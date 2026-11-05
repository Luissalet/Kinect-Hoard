using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace KinectHoard.App
{
    // Keyframe pose graph: odometry edges between consecutive keyframes and
    // verified loop edges when a side is seen again after most of a turn.
    // Gauss-Newton on the left (world) perturbation, first node fixed; loop
    // edges that still disagree after a solve are pruned and it solves again.
    internal sealed class PoseGraph
    {
        internal sealed class Edge { internal int From, To; internal double[] Measured; internal double Weight; internal bool Loop; }
        internal readonly List<Edge> Edges = new List<Edge>();

        private static readonly double[] Scale = { 1 / .01, 1 / .01, 1 / .01, 1 / .005, 1 / .005, 1 / .005 };

        private static double[] Error(double[] a, double[] b, double[] measured)
        {
            var e = Rigid.ToVector(Rigid.Mul(Rigid.Inverse(measured), Rigid.Relative(a, b)));
            for (int i = 0; i < 6; i++) e[i] *= Scale[i];
            return e;
        }

        private static double[] Perturb(double[] pose, int axis, double epsilon)
        {
            var d = new double[6]; d[axis] = epsilon;
            return Rigid.Mul(Rigid.FromVector(d[0], d[1], d[2], d[3], d[4], d[5]), pose);
        }

        // Returns optimised poses for `poses` (node index = keyframe id).
        internal static double[][] Optimise(double[][] poses, IList<Edge> edges, out int pruned)
        {
            pruned = 0;
            var current = poses.Select(p => (double[])p.Clone()).ToArray();
            var active = edges.ToList();
            for (int pass = 0; pass < 2; pass++)
            {
                Solve(current, active);
                var bad = active.Where(e => e.Loop && Norm(Error(current[e.From], current[e.To], e.Measured)) > 6).ToList();
                if (bad.Count == 0) break;
                pruned += bad.Count;
                active = active.Except(bad).ToList();
                current = poses.Select(p => (double[])p.Clone()).ToArray();
            }
            return current;
        }

        private static double Norm(double[] v) { double s = 0; foreach (var x in v) s += x * x; return Math.Sqrt(s / 2); }

        private static void Solve(double[][] poses, IList<Edge> edges)
        {
            int nodes = poses.Length, n = 6 * (nodes - 1);
            if (n <= 0 || !edges.Any(e => e.Loop)) return;
            const double eps = 1e-6;
            for (int iteration = 0; iteration < 6; iteration++)
            {
                var h = new double[n * n]; var b = new double[n];
                double total = 0;
                foreach (var edge in edges)
                {
                    var e = Error(poses[edge.From], poses[edge.To], edge.Measured);
                    total += e.Sum(x => x * x) * edge.Weight;
                    var jac = new double[12][];
                    for (int axis = 0; axis < 12; axis++)
                    {
                        int node = axis < 6 ? edge.From : edge.To;
                        if (node == 0) continue;
                        var a = axis < 6 ? Perturb(poses[edge.From], axis, eps) : poses[edge.From];
                        var c = axis < 6 ? poses[edge.To] : Perturb(poses[edge.To], axis - 6, eps);
                        var ep = Error(a, c, edge.Measured);
                        jac[axis] = new double[6];
                        for (int i = 0; i < 6; i++) jac[axis][i] = (ep[i] - e[i]) / eps;
                    }
                    for (int p = 0; p < 12; p++)
                    {
                        if (jac[p] == null) continue;
                        int row = 6 * ((p < 6 ? edge.From : edge.To) - 1) + p % 6;
                        double gp = 0; for (int i = 0; i < 6; i++) gp += jac[p][i] * e[i];
                        b[row] -= edge.Weight * gp;
                        for (int q = 0; q < 12; q++)
                        {
                            if (jac[q] == null) continue;
                            int col = 6 * ((q < 6 ? edge.From : edge.To) - 1) + q % 6;
                            double s = 0; for (int i = 0; i < 6; i++) s += jac[p][i] * jac[q][i];
                            h[row * n + col] += edge.Weight * s;
                        }
                    }
                }
                for (int i = 0; i < n; i++) h[i * n + i] += 1e-6 + 1e-4 * h[i * n + i];
                if (!Rigid.Solve(h, b, n)) return;
                double step = 0;
                for (int k = 1; k < nodes; k++)
                {
                    int o = 6 * (k - 1);
                    poses[k] = Rigid.Orthonormalize(Rigid.Mul(Rigid.FromVector(b[o], b[o + 1], b[o + 2], b[o + 3], b[o + 4], b[o + 5]), poses[k]));
                    for (int i = 0; i < 6; i++) step = Math.Max(step, Math.Abs(b[o + i]));
                }
                if (step < 1e-7) break;
            }
        }
    }

    // Live tracking of the masked subject, the refine's method made
    // incremental: frame-to-keyframe coloured ICP with a constant-velocity
    // prior, relocalisation (SIFT proposal, then a sweep over keyframes ranked
    // by overlap x colour agreement, bounded by the prior after a short gap),
    // and loop closure on keyframes with a pose graph solved in the
    // background. The caller rebuilds the volume when the graph moves poses.
    internal sealed class LiveIcpTracker
    {
        internal static readonly int LocalKeyframes = (int)ColorIcp.Tuning("KINECT_HOARD_ICP_LOCAL", 4), MaxKeyframes = 160;
        // A fixed camera orbits a turning subject: 6 degrees at 1.2 m is already
        // 13 cm of camera travel, so translation only adds keyframes for a
        // handheld camera that moves without turning.
        internal static readonly double KeyframeDegrees = ColorIcp.Tuning("KINECT_HOARD_KEYFRAME_DEGREES", 6),
            KeyframeMetres = ColorIcp.Tuning("KINECT_HOARD_KEYFRAME_METRES", .15), LoopTurnDegrees = 150, LoopViewDegrees = 40;
        internal readonly List<IcpFrame> Keyframes = new List<IcpFrame>();
        private readonly List<PoseGraph.Edge> edges = new List<PoseGraph.Edge>();
        private readonly HashSet<long> loopKeys = new HashSet<long>();
        private double[] lastPose, velocity = Rigid.Identity();
        private int frameNumber, lastTracked = -1000, pendingLoops, solvedNodes;
        private long lastTicks, velocityTicks;

        private static double[] Scale(double[] motion, double factor)
        {
            if (Math.Abs(factor - 1) < 1e-6) return motion;
            var v = Rigid.ToVector(motion);
            return Rigid.FromVector(v[0] * factor, v[1] * factor, v[2] * factor, v[3] * factor, v[4] * factor, v[5] * factor);
        }
        private Task<double[][]> optimisation;
        private int optimisationNodes;
        internal int Tracked, Relocalised, Lost, LoopClosures, GraphSolves, PrunedLoops, SiftProposals, Swept;
        internal double LastFitness, LastRmse, LastColour, LastCorrectionDegrees, LastCorrectionMetres;
        internal string LastStatus = "", LastLoop = "";
        internal int LoopAttempts;

        internal sealed class Outcome { internal bool Accepted, Keyframe; internal double[] Pose; internal string Status; internal int Anchor; internal double[] Relative; }

        internal double[] CurrentPose { get { return lastPose; } }

        // KINECT_HOARD_TRACK_LOG=file writes one line per tracked frame (benchmarks).
        private static readonly System.IO.TextWriter Log = string.IsNullOrEmpty(Environment.GetEnvironmentVariable("KINECT_HOARD_TRACK_LOG")) ? null
            : System.IO.TextWriter.Synchronized(new System.IO.StreamWriter(Environment.GetEnvironmentVariable("KINECT_HOARD_TRACK_LOG")) { AutoFlush = true });

        // How far the subject itself moves between two poses of its view: the
        // camera translation of a turning subject is mostly its orbit.
        internal static double Moved(double[] a, double[] b, double[] point)
        {
            double ax, ay, az, bx, by, bz;
            Rigid.Apply(a, point[0], point[1], point[2], out ax, out ay, out az);
            Rigid.Apply(b, point[0], point[1], point[2], out bx, out by, out bz);
            return Math.Sqrt((ax - bx) * (ax - bx) + (ay - by) * (ay - by) + (az - bz) * (az - bz));
        }

        private static bool Tracking(IcpResult r, double[] prediction, double[] centroid)
        {
            if (r == null || r.Rmse > .008) return false;
            var deviation = Rigid.Relative(prediction, r.Pose);
            double angle = Rigid.Angle(deviation), shift = Moved(prediction, r.Pose, centroid);
            if (angle >= 25 || shift >= .15) return false;
            if (r.Inliers >= 50 && r.Colour < .15) return false;
            return r.Fitness >= .45 || (r.Fitness >= .3 && angle < 10 && shift < .05);
        }

        private static bool Verified(IcpResult r) { return r != null && r.Fitness >= .45 && r.Rmse <= .008 && r.Colour >= .3; }

        private List<IcpFrame> Near(double[] pose, int count, int skipNewest = 0)
        {
            return Keyframes.Take(Math.Max(0, Keyframes.Count - skipNewest))
                .Select(k => new { k, a = Rigid.Angle(Rigid.Relative(k.Pose, pose)) + 200 * Rigid.Shift(Rigid.Relative(k.Pose, pose)) })
                .OrderBy(x => x.a).Take(count).Select(x => x.k).ToList();
        }

        private List<IcpFrame> LocalModel(double[] prediction)
        {
            // Only recent keyframes: an older surface would put the drift into
            // one odometry edge, which the pose graph could not spread again.
            return Keyframes.Skip(Math.Max(0, Keyframes.Count - LocalKeyframes)).ToList();
        }

        internal Outcome Track(IcpFrame frame, Func<double[]> siftProposal)
        {
            frameNumber++;
            var outcome = new Outcome { Status = "lost", Anchor = -1 };
            if (Keyframes.Count == 0)
            {
                frame.Pose = Rigid.Identity();
                AddKeyframe(frame);
                lastPose = frame.Pose; lastTracked = frameNumber; lastTicks = frame.Ticks; Tracked++;
                LastStatus = outcome.Status = "tracked"; outcome.Accepted = outcome.Keyframe = true; outcome.Pose = frame.Pose;
                outcome.Anchor = frame.Id; outcome.Relative = Rigid.Identity();
                return outcome;
            }
            int gap = frameNumber - lastTracked;
            // Recent: the subject was tracked a moment ago (frames without the subject do not count as gaps).
            bool recent = gap <= 3 && frame.Ticks - lastTicks <= 15000000;
            // Constant velocity per unit of time: a dropped frame doubles the
            // interval, not the predicted step of the next one.
            var prediction = recent ? Rigid.Mul(lastPose, Scale(velocity, velocityTicks <= 0 ? 1 : Math.Min(3, (double)(frame.Ticks - lastTicks) / velocityTicks))) : lastPose;
            var local = LocalModel(prediction);
            // The turn rate is a reliable prior only over a short interval (a live sensor).
            var prior = recent && frame.Ticks - lastTicks <= 1500000 ? prediction : null;
            var result = ColorIcp.Align(frame, local, prediction, ColorIcp.Standard, prior);
            string status = "tracked";
            if (!Tracking(result, prediction, frame.Centroid)) result = ColorIcp.Align(frame, local, prediction, ColorIcp.Wide, prior);
            if (!Tracking(result, prediction, frame.Centroid) && recent)
            {
                // A faster turn than predicted (or a low frame rate): try turns of
                // the subject about its vertical axis before relocalising.
                var swept = Sweep(frame, local, prediction, 45);
                if (Verified(swept) && Rigid.Angle(Rigid.Relative(prediction, swept.Pose)) <= 45) { result = swept; Swept++; }
            }
            if (Log != null && result != null)
                Log.WriteLine(string.Format(System.Globalization.CultureInfo.InvariantCulture, "{0} track fit {1:0.000} rmse {2:0.0} col {3:0.00} dev {4:0.0} n {5} recent {6}",
                    frame.Ticks, result.Fitness, result.Rmse * 1000, result.Colour, Rigid.Angle(Rigid.Relative(prediction, result.Pose)), frame.Count, recent));
            if (!Tracking(result, prediction, frame.Centroid) && !(result != null && Verified(result) && recent && Rigid.Angle(Rigid.Relative(prediction, result.Pose)) <= 45))
            {
                result = Relocalise(frame, prediction, recent, siftProposal);
                if (Log != null) Log.WriteLine(frame.Ticks + (result == null ? " lost" : string.Format(System.Globalization.CultureInfo.InvariantCulture, " relocalised fit {0:0.000} col {1:0.00}", result.Fitness, result.Colour)));
                if (result == null)
                {
                    Lost++; LastStatus = "lost";
                    return outcome;
                }
                status = "relocalised"; Relocalised++;
            }
            else Tracked++;
            frame.Pose = result.Pose;
            LastFitness = result.Fitness; LastRmse = result.Rmse; LastColour = result.Colour; LastStatus = status;
            velocity = status == "tracked" && recent ? Rigid.Relative(lastPose, frame.Pose) : Rigid.Identity();
            velocityTicks = frame.Ticks - lastTicks;
            lastPose = frame.Pose; lastTracked = frameNumber; lastTicks = frame.Ticks;
            var relative = Rigid.Relative(Keyframes[Keyframes.Count - 1].Pose, frame.Pose);
            if (Keyframes.Count < MaxKeyframes && (Rigid.Angle(relative) >= KeyframeDegrees || Rigid.Shift(relative) >= KeyframeMetres))
            {
                AddKeyframe(frame);
                outcome.Keyframe = true;
                outcome.Anchor = frame.Id; outcome.Relative = Rigid.Identity();
            }
            else
            {
                frame.Release();
                var anchor = Keyframes[Keyframes.Count - 1];
                outcome.Anchor = anchor.Id; outcome.Relative = Rigid.Relative(anchor.Pose, frame.Pose);
            }
            outcome.Accepted = true; outcome.Pose = frame.Pose; outcome.Status = status;
            return outcome;
        }

        private IcpResult Relocalise(IcpFrame frame, double[] prediction, bool shortGap, Func<double[]> siftProposal)
        {
            var proposals = new List<IcpResult>();
            double[] sift = siftProposal == null ? null : siftProposal();
            if (sift != null)
            {
                SiftProposals++;
                proposals.Add(ColorIcp.Align(frame, Near(sift, LocalKeyframes), sift, ColorIcp.Wide));
            }
            // A turning subject shows a side some keyframe already saw: start
            // from that keyframe's pose and keep the proposals that fit best.
            var candidates = shortGap ? Near(prediction, 8) : Keyframes.Where((k, i) => i % Math.Max(1, Keyframes.Count / 16) == 0).ToList();
            var coarse = candidates.Select(k => Sweep(frame, new[] { k }, k.Pose, 30, false))
                .Where(r => r != null).OrderByDescending(r => r.Fitness * Math.Max(r.Colour, .01)).Take(3);
            foreach (var r in coarse) proposals.Add(ColorIcp.Align(frame, Near(r.Pose, LocalKeyframes), r.Pose, ColorIcp.Standard));
            IcpResult best = null;
            foreach (var r in proposals)
            {
                if (!Verified(r)) continue;
                // Right after a tracked frame the subject cannot have turned far;
                // the bound stops a symmetric front/back swap.
                if (shortGap && Rigid.Angle(Rigid.Relative(prediction, r.Pose)) > 30) continue;
                if (best == null || r.Fitness * r.Colour > best.Fitness * best.Colour) best = r;
            }
            return best;
        }

        private static readonly double[] SweepDegrees = { 0, -10, 10, -20, 20, -30, 30, -40, 40 };

        // Coarse alignments from the base pose turned about the vertical axis
        // through the subject; the best by overlap x colour agreement, refined
        // at full precision unless only the coarse proposal is wanted.
        private static IcpResult Sweep(IcpFrame frame, IList<IcpFrame> targets, double[] basePose, double limitDegrees, bool refine = true)
        {
            double cx, cy, cz, tx, ty, tz;
            Rigid.Apply(basePose, frame.Centroid[0], frame.Centroid[1], frame.Centroid[2], out cx, out cy, out cz);
            // The subject also sways and steps: each turn is tried as is and with
            // its centre moved onto the centre of the newest target view.
            var newest = targets[targets.Count - 1];
            Rigid.Apply(newest.Pose, newest.Centroid[0], newest.Centroid[1], newest.Centroid[2], out tx, out ty, out tz);
            IcpResult best = null;
            foreach (double degrees in SweepDegrees)
            {
                if (Math.Abs(degrees) > limitDegrees) continue;
                var turn = Rigid.FromVector(0, degrees * Math.PI / 180, 0, 0, 0, 0);
                double rx, ry, rz;
                Rigid.Apply(turn, cx, cy, cz, out rx, out ry, out rz);
                turn[3] = cx - rx; turn[7] = cy - ry; turn[11] = cz - rz;
                for (int centred = 0; centred < 2; centred++)
                {
                    var hypothesis = Rigid.Mul(turn, basePose);
                    if (centred == 1) { hypothesis[3] += tx - cx; hypothesis[7] += ty - cy; hypothesis[11] += tz - cz; }
                    var result = ColorIcp.Align(frame, targets, hypothesis, ColorIcp.Coarse);
                    if (result != null && (best == null || result.Fitness * Math.Max(result.Colour, .01) > best.Fitness * Math.Max(best.Colour, .01))) best = result;
                }
            }
            if (best == null || !refine) return best;
            return ColorIcp.Align(frame, targets, best.Pose, ColorIcp.Standard);
        }

        private void AddKeyframe(IcpFrame frame)
        {
            frame.Id = Keyframes.Count;
            // Later frames should not align to this view's moving limbs.
            for (int i = 0; i < frame.Moving.Length; i++) if (frame.Moving[i]) frame.Ok[i] = false;
            if (Keyframes.Count > 0)
            {
                var previous = Keyframes[Keyframes.Count - 1];
                var relative = Rigid.Relative(previous.Pose, frame.Pose);
                frame.Travelled = previous.Travelled + Rigid.Angle(relative);
                edges.Add(new PoseGraph.Edge { From = previous.Id, To = frame.Id, Measured = relative, Weight = 1 });
            }
            Keyframes.Add(frame);
            CloseLoops(frame);
        }

        private void CloseLoops(IcpFrame frame)
        {
            var candidates = Keyframes.Take(frame.Id)
                .Where(k => frame.Travelled - k.Travelled >= LoopTurnDegrees)
                .Select(k => new { k, view = Rigid.Angle(Rigid.Relative(k.Pose, frame.Pose)) })
                .Where(x => x.view <= LoopViewDegrees).OrderBy(x => x.view).Take(2).ToList();
            foreach (var candidate in candidates)
            {
                long key = (long)(candidate.k.Id / 3) << 32 | (uint)(frame.Id / 3);
                if (loopKeys.Contains(key)) continue;
                LoopAttempts++;
                var result = ColorIcp.Align(frame, new[] { candidate.k }, frame.Pose, ColorIcp.Wide);
                var disagreement = result == null ? null : Rigid.Relative(frame.Pose, result.Pose);
                LastLoop = result == null ? "sin convergencia" : string.Format(System.Globalization.CultureInfo.InvariantCulture,
                    "kf {0}->{1} fitness {2:0.00} rmse {3:0.0} mm colour {4:0.00} change {5:0.0} deg", candidate.k.Id, frame.Id,
                    result.Fitness, result.Rmse * 1000, result.Colour, Rigid.Angle(disagreement));
                if (result == null || result.Fitness < .4 || result.Rmse > .008 || result.Colour < .3) continue;
                if (Rigid.Angle(disagreement) > 35 || Moved(frame.Pose, result.Pose, frame.Centroid) > .10) continue;
                loopKeys.Add(key);
                edges.Add(new PoseGraph.Edge { From = candidate.k.Id, To = frame.Id, Measured = Rigid.Relative(candidate.k.Pose, result.Pose), Weight = 2, Loop = true });
                LoopClosures++; pendingLoops++;
            }
            if (pendingLoops > 0 && optimisation == null) StartOptimisation();
        }

        private void StartOptimisation()
        {
            var poses = Keyframes.Select(k => (double[])k.Pose.Clone()).ToArray();
            var snapshot = edges.ToList();
            optimisationNodes = poses.Length; pendingLoops = 0;
            optimisation = Task.Run(() => { int pruned; var r = PoseGraph.Optimise(poses, snapshot, out pruned); lock (edges) PrunedLoops += pruned; return r; });
        }

        // Applies a finished graph solve; keyframes added meanwhile follow the
        // correction of the newest optimised node. True when poses moved.
        internal bool TryApplyOptimisation(bool wait = false)
        {
            if (optimisation == null) return false;
            if (!optimisation.IsCompleted && !wait) return false;
            double[][] optimised = optimisation.GetAwaiter().GetResult();
            optimisation = null; GraphSolves++;
            int n = optimisationNodes; solvedNodes = n;
            double rotation = 0, shift = 0;
            var leftCorrection = Rigid.Mul(optimised[n - 1], Rigid.Inverse(Keyframes[n - 1].Pose));
            for (int i = 0; i < Keyframes.Count; i++)
            {
                var updated = i < n ? optimised[i] : Rigid.Mul(leftCorrection, Keyframes[i].Pose);
                var change = Rigid.Relative(Keyframes[i].Pose, updated);
                rotation = Math.Max(rotation, Rigid.Angle(change)); shift = Math.Max(shift, Rigid.Shift(change));
                Keyframes[i].Pose = updated;
            }
            if (lastPose != null) lastPose = Rigid.Mul(leftCorrection, lastPose);
            LastCorrectionDegrees = rotation; LastCorrectionMetres = shift;
            if (pendingLoops > 0) StartOptimisation();
            return rotation >= .2 || shift >= .002;
        }

        // Final solve over every loop found, before the mesh is extracted.
        internal bool Finish()
        {
            bool moved = false;
            while (optimisation != null) moved |= TryApplyOptimisation(true);
            if (edges.Any(e => e.Loop) && solvedNodes != Keyframes.Count)
            {
                StartOptimisation();
                while (optimisation != null) moved |= TryApplyOptimisation(true);
            }
            return moved;
        }

        internal double[] Corrected(int anchor, double[] relative)
        {
            return anchor >= 0 && anchor < Keyframes.Count ? Rigid.Mul(Keyframes[anchor].Pose, relative) : null;
        }
    }
}
