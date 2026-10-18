using System;
using System.Collections.Generic;

namespace KinectHoard.Core
{
    public sealed class GestureEvent
    {
        public ulong TrackingId { get; set; }
        public string Gesture { get; set; }
        public string State { get; set; }
        public DateTime TimestampUtc { get; set; }
        public float Confidence { get; set; }
    }

    // Coordinates are Kinect camera metres: X right, Y up, Z away from the sensor.
    public sealed class GestureEngine
    {
        private readonly Dictionary<ulong, BodyState> bodies = new Dictionary<ulong, BodyState>();

        public GestureEvent[] Process(CameraFrame frame)
        {
            if (frame == null || frame.Kind != StreamKind.Skeleton) throw new ArgumentException("Se requiere un fotograma de esqueleto.", "frame");
            DateTime time = frame.TimestampUtc == default(DateTime) ? DateTime.UtcNow : frame.TimestampUtc.ToUniversalTime();
            var events = new List<GestureEvent>();
            var seen = new HashSet<ulong>();
            foreach (TrackedBody body in frame.Bodies ?? new TrackedBody[0])
            {
                if (body == null || body.Joints == null) continue;
                seen.Add(body.TrackingId);
                BodyState state;
                if (!bodies.TryGetValue(body.TrackingId, out state)) bodies[body.TrackingId] = state = new BodyState();
                var joints = new Dictionary<string, BodyJoint>(StringComparer.Ordinal);
                foreach (BodyJoint joint in body.Joints)
                    if (joint != null && joint.Name != null && joint.TrackingState == 2) joints[joint.Name] = joint;
                BodyJoint head = null, shoulderLeft = null, shoulderRight = null, left, right;
                bool upper = joints.TryGetValue("Head", out head) &&
                    joints.TryGetValue("ShoulderLeft", out shoulderLeft) && joints.TryGetValue("ShoulderRight", out shoulderRight);
                bool hasLeft = joints.TryGetValue("HandLeft", out left);
                bool hasRight = joints.TryGetValue("HandRight", out right);
                bool leftRaised = upper && hasLeft && left.Y > shoulderLeft.Y + 0.1f;
                bool rightRaised = upper && hasRight && right.Y > shoulderRight.Y + 0.1f;
                bool together = hasLeft && hasRight && Distance(left, right) < 0.18f &&
                    (!upper || Math.Min(left.Y, right.Y) > Math.Min(shoulderLeft.Y, shoulderRight.Y) - 0.25f);
                Toggle(events, state, body.TrackingId, "left_hand_raised", leftRaised, time);
                Toggle(events, state, body.TrackingId, "right_hand_raised", rightRaised, time);
                Toggle(events, state, body.TrackingId, "hands_together", together, time);
                Swipe(events, state, body.TrackingId, left, hasLeft, "left", time);
                Swipe(events, state, body.TrackingId, right, hasRight, "right", time);
                state.LastSeen = time;
            }
            foreach (ulong id in new List<ulong>(bodies.Keys))
                if (!seen.Contains(id) && (time - bodies[id].LastSeen).TotalMilliseconds >= 500)
                {
                    foreach (string gesture in bodies[id].Active)
                        events.Add(new GestureEvent { TrackingId = id, Gesture = gesture, State = "ended", TimestampUtc = time, Confidence = 1 });
                    bodies.Remove(id);
                }
            return events.ToArray();
        }

        private static float Distance(BodyJoint a, BodyJoint b)
        {
            float x = a.X - b.X, y = a.Y - b.Y, z = a.Z - b.Z;
            return (float)Math.Sqrt(x * x + y * y + z * z);
        }

        private static void Toggle(List<GestureEvent> output, BodyState body, ulong id, string name, bool active, DateTime time)
        {
            bool previous = body.Active.Contains(name);
            if (active == previous) return;
            if (active) body.Active.Add(name);
            else body.Active.Remove(name);
            output.Add(new GestureEvent { TrackingId = id, Gesture = name, State = active ? "started" : "ended", TimestampUtc = time, Confidence = 1 });
        }

        private static void Swipe(List<GestureEvent> output, BodyState body, ulong id, BodyJoint hand, bool tracked, string side, DateTime time)
        {
            HandSample previous = side == "left" ? body.Left : body.Right;
            if (!tracked)
            {
                if (side == "left") body.Left = null; else body.Right = null;
                return;
            }
            if (previous != null)
            {
                double seconds = (time - previous.Time).TotalSeconds;
                if (seconds > 0.12 && seconds <= 0.8 && Math.Abs(hand.Y - previous.Y) < 0.18f && Math.Abs(hand.Z - previous.Z) < 0.25f &&
                    Math.Abs(hand.X - previous.X) >= 0.35f && (time - body.LastSwipe).TotalMilliseconds >= 750)
                {
                    output.Add(new GestureEvent {
                        TrackingId = id, Gesture = side + "_hand_swipe_" + (hand.X > previous.X ? "right" : "left"),
                        State = "detected", TimestampUtc = time, Confidence = 1
                    });
                    body.LastSwipe = time;
                    previous = null;
                }
                else if (seconds > 0.8 || Math.Abs(hand.Y - previous.Y) >= 0.18f || Math.Abs(hand.Z - previous.Z) >= 0.25f)
                    previous = null;
            }
            if (previous == null)
                previous = new HandSample { X = hand.X, Y = hand.Y, Z = hand.Z, Time = time };
            if (side == "left") body.Left = previous; else body.Right = previous;
        }

        private sealed class BodyState
        {
            internal readonly HashSet<string> Active = new HashSet<string>(StringComparer.Ordinal);
            internal DateTime LastSeen;
            internal DateTime LastSwipe;
            internal HandSample Left, Right;
        }
        private sealed class HandSample { internal float X, Y, Z; internal DateTime Time; }
    }
}
