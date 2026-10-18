"""End-to-end UV, texture and measured-extrinsics smoke test for quality_scan.py."""

import gzip
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from quality_scan import scan  # noqa: E402


def make_session(path: Path, high_res: bool = False) -> None:
    width, height = 64, 48
    color = bytes(channel for y in range(height) for x in range(width)
                  for channel in ((50, 50, 50, 255) if high_res else (30 + x * 3, 40 + y * 3, 120, 255)))
    full_color = bytes(channel for y in range(height * 2) for x in range(width * 2)
                       for channel in (20 + x, 30 + y, 100, 255)) if high_res else b""
    mapping = struct.pack("<" + "f" * (width * height * 2),
                          *(value for y in range(height) for x in range(width)
                            for value in (float(x * 2), float(y * 2)))) if high_res else b""
    depth = struct.pack("<" + "H" * (width * height), *([2000] * (width * height)))
    with gzip.open(path, "wb") as output:
        name = b"KINECT_HOARD_SESSION_2" if high_res else b"KINECT_HOARD_SESSION_1"
        output.write(bytes([len(name)]) + name)
        output.write(struct.pack("<iq", 7, 0))
        for index in range(3):
            output.write(struct.pack("<bqiii", 1, 638000000000000000 + index * 2_000_000,
                                     width, height, len(color)))
            output.write(color)
            output.write(struct.pack("<i", width * height))
            output.write(depth)
            output.write(struct.pack("<i", 0))
            if high_res:
                output.write(struct.pack("<iii", width * 2, height * 2, len(full_color)))
                output.write(full_color)
                output.write(struct.pack("<i", width * height))
                output.write(mapping)
    path.with_suffix(".intrinsics.json").write_text(json.dumps({
        "format": "KINECT_HOARD_RGBD_1", "intrinsics": {
            "width": width, "height": height, "fx": 55, "fy": 55,
            "cx": 31.5, "cy": 23.5, "method": "synthetic",
        },
    }), encoding="utf-8")


def main() -> None:
    import numpy as np
    import open3d as o3d

    folder = ROOT / ".cache" / "quality-scan-smoke"
    folder.mkdir(parents=True, exist_ok=True)
    first, second = folder / "one.khr", folder / "360.khr"
    make_session(first)
    make_session(second)
    calibration = folder / "measured.json"
    calibration.write_text(json.dumps({
        "format": "KINECT_HOARD_DUAL_EXTRINSICS_1",
        "calibration_method": "synthetic colocated cameras",
        "rms_error_metres": 0.0,
        "world_from_second": np.eye(4).tolist(),
    }), encoding="utf-8")

    report = scan([first, second], folder / "dual.obj", folder / "dual.scan.json",
                  tracking="fixed", extrinsics=calibration, voxel=0.02,
                  texture_size=1024, max_triangles=10_000)
    imported = o3d.io.read_triangle_mesh(report["obj"], True)
    assert imported.has_triangles() and imported.has_triangle_uvs() and imported.has_textures()
    assert len(report["sessions"]) == 2 and all(s["frames_accepted"] == 3 for s in report["sessions"])
    assert report["capture_overlap_seconds"] > 0
    assert report["texture_observed_coverage"] > 0.95
    assert Path(report["texture"]).is_file() and Path(report["mtl"]).is_file()

    high_res = folder / "one-quality.khr"
    make_session(high_res, high_res=True)
    high_res_report = scan([high_res], folder / "one-quality.obj", folder / "one-quality.scan.json",
                           tracking="fixed", voxel=0.02, texture_size=1024, max_triangles=10_000)
    atlas = np.asarray(o3d.io.read_image(high_res_report["texture"]))
    assert high_res_report["full_resolution_color_frames"] == 3
    assert int(atlas[:, :, 2].max()) - int(atlas[:, :, 2].min()) > 50

    invalid = json.loads(calibration.read_text(encoding="utf-8"))
    invalid["world_from_second"][0][0] = -1
    calibration.write_text(json.dumps(invalid), encoding="utf-8")
    try:
        scan([first, second], folder / "invalid.obj", folder / "invalid.scan.json",
             tracking="fixed", extrinsics=calibration, voxel=0.02,
             texture_size=1024, max_triangles=10_000)
    except ValueError as error:
        assert "rotación" in str(error)
    else:
        raise AssertionError("Se aceptó un reflejo como transformación rígida")
    print(f"OBJ texturizado y dos sesiones verificados: {report['triangles']} caras")


if __name__ == "__main__":
    main()
