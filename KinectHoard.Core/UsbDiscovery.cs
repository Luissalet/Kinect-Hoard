using System;
using System.Management;

namespace KinectHoard.Core
{
    public static class UsbDiscovery
    {
        // These IDs are checked directly in Windows PnP, independently of either Kinect SDK.
        public static bool IsPresent(string model)
        {
            string[] ids;
            if (model == "one") ids = new[] { "PID_02C4", "PID_02D8" };
            else if (model == "360") ids = new[] { "PID_02AE", "PID_02BF", "PID_02B0" };
            else throw new ArgumentException("Modelo desconocido", "model");

            using (var search = new ManagementObjectSearcher("SELECT PNPDeviceID, ConfigManagerErrorCode FROM Win32_PnPEntity"))
            using (var results = search.Get())
                foreach (ManagementObject item in results)
                {
                    string id = item["PNPDeviceID"] as string ?? "";
                    if (!id.StartsWith("USB\\VID_045E&", StringComparison.OrdinalIgnoreCase)) continue;
                    if (Convert.ToUInt32(item["ConfigManagerErrorCode"] ?? 1) != 0) continue;
                    foreach (string pid in ids)
                        if (id.IndexOf(pid, StringComparison.OrdinalIgnoreCase) >= 0) return true;
                }
            return false;
        }
    }
}
