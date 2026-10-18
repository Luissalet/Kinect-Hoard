"""Run with .venv-scan/Scripts/python.exe tests/fusion-smoke.py."""

import gzip
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fusion import fuse  # noqa: E402


def main() -> None:
    folder = ROOT / ".cache" / "fusion-smoke"
    folder.mkdir(parents=True, exist_ok=True)
    session = folder / "plane.khr"
    mesh = folder / "plane.ply"
    report = folder / "plane.fusion.json"
    width, height = 64, 48
    color = bytes(value for y in range(height) for x in range(width)
                  for value in (x * 4, y * 5, 100, 255))
    depth = struct.pack("<" + "H" * (width * height), *([2000] * (width * height)))
    with gzip.open(session, "wb") as output:
        name = b"KINECT_HOARD_SESSION_1"
        output.write(bytes([len(name)]) + name)
        output.write(struct.pack("<iq", 7, 0))
        for index in range(3):
            output.write(struct.pack("<bqiii", 1, 638000000000000000 + index * 2_000_000,
                                     width, height, len(color)))
            output.write(color)
            output.write(struct.pack("<i", width * height))
            output.write(depth)
            output.write(struct.pack("<i", 0))
    session.with_suffix(".intrinsics.json").write_text(json.dumps({
        "format": "KINECT_HOARD_RGBD_1", "intrinsics": {
            "width": width, "height": height, "fx": 55, "fy": 55,
            "cx": 31.5, "cy": 23.5, "method": "synthetic",
        },
    }), encoding="utf-8")
    result = fuse(session, mesh, report, 0.02, "fixed", 10)
    assert result["frames_integrated"] == 3
    assert result["vertices"] > 0 and result["triangles"] > 0
    assert mesh.is_file() and report.is_file()
    foreground_mesh = folder / "foreground.ply"
    cropped = fuse(session, foreground_mesh, folder / "foreground.fusion.json",
                   0.02, "fixed", 10, 2.5, (8, 2, 48, 40))
    assert cropped["frames_integrated"] == 3
    assert cropped["vertices"] > 0 and cropped["triangles"] > 0
    assert cropped["foreground_max_depth_metres"] == 2.5
    assert cropped["roi_depth_pixels"] == [8, 2, 48, 40]
    print(f"TSDF verificado: {result['vertices']} vértices, {result['triangles']} caras")


if __name__ == "__main__":
    main()
