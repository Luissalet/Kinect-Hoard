"""Read Kinect Hoard's local HTTP camera stream with OpenCV.

Start KinectHoard.App.exe --webserver 8765 Color 0 in another terminal.
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
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--no-window", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.seconds <= 0:
        parser.error("port must be 1–65535 and seconds must be positive")
    base = f"http://127.0.0.1:{args.port}"
    deadline = time.monotonic() + args.seconds
    frames = 0
    while time.monotonic() < deadline:
        try:
            metadata = json.loads(fetch(base, "/api/frame"))
            pixels = np.frombuffer(fetch(base, "/frame.png"), dtype=np.uint8)
            image = cv2.imdecode(pixels, cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("invalid PNG from Kinect Hoard")
            frames += 1
            cv2.putText(image, f"{metadata['stream']} {image.shape[1]}x{image.shape[0]}",
                        (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            if not args.no_window:
                cv2.imshow("Kinect Hoard / OpenCV", image)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        except Exception as exc:
            print(f"Esperando el servidor: {exc}")
            time.sleep(0.5)
    if not args.no_window:
        cv2.destroyAllWindows()
    print(f"OpenCV recibió {frames} imágenes")
    if frames == 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
