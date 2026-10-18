using System;
using System.Management;

namespace KinectHoard.Core
{
    public static class UsbDiscovery
    {
        public sealed class DeviceStatus
        {
            public bool Detected { get; internal set; }
            public bool Usable { get; internal set; }
            public uint ProblemCode { get; internal set; }
            public string Name { get; internal set; }
            public string InstanceId { get; internal set; }
            public string Service { get; internal set; }

            public string Description
            {
                get
                {
                    if (Usable) return "dispositivo USB operativo: " + Name;
                    if (Detected) return "USB enumerado, controlador con código " + ProblemCode + ": " + Name + " (" + InstanceId + ")";
                    return "no se encontró ningún dispositivo USB de este modelo";
                }
            }
        }

        // These IDs are checked directly in Windows PnP, independently of either Kinect SDK.
        public static bool IsPresent(string model)
        {
            return GetStatus(model).Usable;
        }

        public static DeviceStatus GetStatus(string model)
        {
            string[] ids;
            if (model == "one") ids = new[] { "PID_02C4", "PID_02D8" };
            else if (model == "360") ids = new[] { "PID_02AE", "PID_02BF" };
            else throw new ArgumentException("Modelo desconocido", "model");

            var status = new DeviceStatus();
            using (var search = new ManagementObjectSearcher("SELECT PNPDeviceID, Name, Service, ConfigManagerErrorCode FROM Win32_PnPEntity"))
            using (var results = search.Get())
                foreach (ManagementObject item in results)
                {
                    string id = item["PNPDeviceID"] as string ?? "";
                    if (!id.StartsWith("USB\\VID_045E&", StringComparison.OrdinalIgnoreCase)) continue;
                    foreach (string pid in ids)
                        if (id.IndexOf(pid, StringComparison.OrdinalIgnoreCase) >= 0)
                        {
                            uint code = Convert.ToUInt32(item["ConfigManagerErrorCode"] ?? 1);
                            if (!status.Detected || (code == 0 && !status.Usable))
                            {
                                status.Detected = true;
                                status.Usable = code == 0;
                                status.ProblemCode = code;
                                status.Name = item["Name"] as string ?? "sensor Kinect";
                                status.InstanceId = id;
                                status.Service = item["Service"] as string ?? "";
                            }
                            break;
                        }
                }
            return status;
        }
    }
}
