"""Read Kinect Hoard depth, IR or body-index uint16 frames into NumPy/OpenCV.

Start KinectHoard.App.exe --webserver 8765 Depth 0 in another terminal.
Install dependencies with: python -m pip install opencv-python numpy
"""

import argparse
import json
import time
from urllib.request import urlopen

import cv2
import numpy as np


def fetch(base: str, path: str) -> bytes:
    with urlopen(base + path, timeout=3) as response:
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--no-window", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.seconds <= 0:
        parser.error("port must be 1–65535 and seconds must be positive")
    base = f"http://127.0.0.1:{args.port}"
    deadline = time.monotonic() + args.seconds
    count = 0
    last_sequence = -1
    while time.monotonic() < deadline:
        try:
            info = json.loads(fetch(base, "/api/frame"))
            if info.get("raw_format") != "uint16_le":
                raise ValueError("select Depth, Infrared, LongExposureInfrared, BodyIndex or ColorDepth")
            if info["sequence"] == last_sequence:
                time.sleep(0.02)
                continue
            raw = fetch(base, "/frame.raw")
            values = np.frombuffer(raw, dtype="<u2")
            if values.size != info["width"] * info["height"]:
                raise ValueError("frame changed between metadata and raw data; retrying")
            values = values.reshape(info["height"], info["width"])
            valid = values[(values > 0) & (values < 65535)]
            count += 1
            last_sequence = info["sequence"]
            if count == 1:
                print(f"{info['stream']}: {values.shape[1]}x{values.shape[0]}, "
                      f"unit={info['raw_unit']}, median={np.median(valid) if valid.size else 'none'}")
            if not args.no_window:
                lo, hi = np.percentile(valid, [2, 98]) if valid.size else (0, 1)
                if hi <= lo:
                    hi = lo + 1
                preview = np.clip((values.astype(np.float32) - lo) * 255 / (hi - lo), 0, 255).astype(np.uint8)
                cv2.imshow("Kinect Hoard / raw", cv2.applyColorMap(preview, cv2.COLORMAP_TURBO))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        except Exception as exc:
            print(f"Esperando datos crudos: {exc}")
            time.sleep(0.5)
    if not args.no_window:
        cv2.destroyAllWindows()
    print(f"OpenCV recibió {count} matrices uint16")
    if count == 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
