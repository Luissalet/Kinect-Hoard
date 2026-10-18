using System;
using System.Runtime.InteropServices;
using System.Text;
using KinectHoard.Core;

namespace KinectHoard.Driver.ThreeSixty.Native
{
    // This backend uses libfreenect and libusbK on the 360 camera, without Kinect SDK 1.8.
    public sealed class NativeThreeSixtyCamera : MarshalByRefObject, ICameraBackend
    {
        private const string Library = "KinectHoard.Native360.dll";
        private IntPtr session;
        private StreamKind stream;
        private byte[] raw;
        private byte[] pixels;
        private ushort[] values;
        private int width;
        private int height;

        public string Model { get { return "Kinect 360 / v1"; } }
        public string BackendName { get { return "OpenKinect/libfreenect + libusbK"; } }
        public string Detail { get; private set; }
        public bool IsAvailable
        {
            get
            {
                var status = UsbDiscovery.GetStatus("360");
                bool compatible = status.Service.Equals("libusbK", StringComparison.OrdinalIgnoreCase) ||
                    status.Service.Equals("WinUSB", StringComparison.OrdinalIgnoreCase);
                Detail = status.Description + (status.Usable && !compatible ?
                    "; cámara requiere libusbK (servicio actual: " + status.Service + ")" : "");
                return status.Usable && compatible;
            }
        }

        public void Open(StreamKind requestedStream)
        {
            Close();
            int kind;
            switch (requestedStream)
            {
                case StreamKind.Color: kind = 0; break;
                case StreamKind.Depth: kind = 1; break;
                case StreamKind.Infrared: kind = 2; break;
                default: throw new NotSupportedException("El controlador nativo 360 admite color, profundidad e infrarrojos en este momento.");
            }
            var error = new StringBuilder(256);
            session = OpenNative(kind, 0, error, error.Capacity);
            if (session == IntPtr.Zero) throw new InvalidOperationException(error.ToString());
            stream = requestedStream;
            width = WidthNative(session);
            height = HeightNative(session);
            raw = new byte[FrameBytesNative(session)];
            if (width <= 0 || height <= 0 || raw.Length <= 0) { Close(); throw new InvalidOperationException("Formato nativo inválido."); }
            pixels = new byte[checked(width * height * 4)];
            if (stream != StreamKind.Color) values = new ushort[checked(width * height)];
            Detail = "Cámara 360 abierta mediante libfreenect.";
        }

        public bool TryRead(out CameraFrame frame)
        {
            frame = null;
            if (session == IntPtr.Zero) return false;
            uint timestamp;
            int result = ReadNative(session, raw, raw.Length, out timestamp);
            if (result < 0) throw new InvalidOperationException("Error leyendo la Kinect 360: libfreenect " + result);
            if (result == 0) return false;
            int count = width * height;
            if (stream == StreamKind.Color)
            {
                if (raw.Length < count * 3) throw new InvalidOperationException("RGB 360 incompleto.");
                for (int i = 0, src = 0, dst = 0; i < count; i++, src += 3, dst += 4)
                { pixels[dst] = raw[src + 2]; pixels[dst + 1] = raw[src + 1]; pixels[dst + 2] = raw[src]; pixels[dst + 3] = 255; }
            }
            else if (stream == StreamKind.Depth)
            {
                if (raw.Length < count * 2) throw new InvalidOperationException("Profundidad 360 incompleta.");
                Buffer.BlockCopy(raw, 0, values, 0, count * 2);
                pixels = FrameRenderer.RenderDepth(values, pixels, 500, 4500);
            }
            else
            {
                if (raw.Length < count) throw new InvalidOperationException("Infrarrojos 360 incompletos.");
                for (int i = 0; i < count; i++) values[i] = (ushort)(raw[i] * 257);
                pixels = FrameRenderer.RenderInfrared(values, pixels);
            }
            frame = new CameraFrame { Width = width, Height = height, Bgra = (byte[])pixels.Clone(),
                Values = values == null ? null : (ushort[])values.Clone(), Kind = stream, TimestampUtc = DateTime.UtcNow };
            return true;
        }

        public bool TryReadPointCloud(out PointCloudFrame frame)
        {
            frame = null;
            if (stream != StreamKind.Depth || session == IntPtr.Zero)
                throw new InvalidOperationException("Abre profundidad antes de pedir la nube de puntos.");
            CameraFrame depth;
            if (!TryRead(out depth)) return false;
            var intrinsics = GetDepthIntrinsics();
            var xyz = new float[values.Length * 3];
            for (int i = 0, j = 0; i < values.Length; i++, j += 3)
            {
                float z = values[i] / 1000f;
                if (z <= 0 || z > 10) { xyz[j] = xyz[j + 1] = xyz[j + 2] = float.NaN; continue; }
                xyz[j] = ((i % width) - intrinsics.Cx) * z / intrinsics.Fx;
                xyz[j + 1] = (intrinsics.Cy - (i / width)) * z / intrinsics.Fy;
                xyz[j + 2] = z;
            }
            frame = new PointCloudFrame { Width = width, Height = height, Xyz = xyz };
            return true;
        }

        public DepthIntrinsics GetDepthIntrinsics()
        {
            if (stream != StreamKind.Depth || width == 0) throw new InvalidOperationException("Abre profundidad primero.");
            // Approximate factory field of view. A future calibration path should replace this estimate.
            const double horizontalFov = 58.5 * Math.PI / 180.0;
            const double verticalFov = 45.6 * Math.PI / 180.0;
            return new DepthIntrinsics { Width = width, Height = height,
                Fx = (float)(width / (2 * Math.Tan(horizontalFov / 2))),
                Fy = (float)(height / (2 * Math.Tan(verticalFov / 2))),
                Cx = (width - 1) / 2f, Cy = (height - 1) / 2f,
                Method = "Approximate Kinect v1 depth field of view; not factory calibrated" };
        }

        public void Close()
        {
            if (session != IntPtr.Zero) { CloseNative(session); session = IntPtr.Zero; }
            raw = null; pixels = null; values = null; width = height = 0;
        }
        public void Dispose() { Close(); }
        public override object InitializeLifetimeService() { return null; }

        [DllImport(Library, CallingConvention = CallingConvention.Cdecl, EntryPoint = "kh360_open", CharSet = CharSet.Ansi)]
        private static extern IntPtr OpenNative(int kind, int index, StringBuilder error, int errorCapacity);
        [DllImport(Library, CallingConvention = CallingConvention.Cdecl, EntryPoint = "kh360_close")]
        private static extern void CloseNative(IntPtr session);
        [DllImport(Library, CallingConvention = CallingConvention.Cdecl, EntryPoint = "kh360_width")]
        private static extern int WidthNative(IntPtr session);
        [DllImport(Library, CallingConvention = CallingConvention.Cdecl, EntryPoint = "kh360_height")]
        private static extern int HeightNative(IntPtr session);
        [DllImport(Library, CallingConvention = CallingConvention.Cdecl, EntryPoint = "kh360_frame_bytes")]
        private static extern int FrameBytesNative(IntPtr session);
        [DllImport(Library, CallingConvention = CallingConvention.Cdecl, EntryPoint = "kh360_read")]
        private static extern int ReadNative(IntPtr session, [Out] byte[] target, int capacity, out uint timestamp);
    }
}
