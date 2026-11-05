"""Native live Fusion keeps its mesh in the camera frame of its poses.

Run with .venv-scan/Scripts/python.exe tests/fusion-convention.py after build.ps1.
Replays a static synthetic person on the CPU Fusion engine (no sensor, no GPU)
and measures the native scan.ply against the ground-truth surface. Before
05-11-2026 the mesh came out mirrored in X and the median error was 12 mm.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import open3d as o3d

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from turn_benchmark import surface, trajectory  # noqa: E402
from turn_synthetic import generate  # noqa: E402


def main() -> None:
    exe = ROOT / "KinectHoard.App" / "bin" / "Release" / "net48" / "KinectHoard.App.exe"
    with tempfile.TemporaryDirectory() as temporary:
        synthetic, replay = Path(temporary) / "input", Path(temporary) / "native"
        generate(synthetic, turn_seconds=100_000, fps=10, turns=0.00003, swing_degrees=0, sway=False)
        subprocess.run([str(exe), "--scanner-replay", str(synthetic / "session.khr"), "one", "fixed", str(replay), "cpu"],
                       check=True, timeout=300)
        journal = json.loads((replay / "live.scan.json").read_text(encoding="utf-8"))
        assert journal.get("mesh_coordinate_space") == "camera", journal.keys()
        truth = {p["timestamp_ticks_utc"]: np.asarray(p["camera_to_world"])
                 for p in json.loads((synthetic / "ground_truth.json").read_text(encoding="utf-8"))["poses"]}
        native = {p["timestamp_ticks_utc"]: np.asarray(p["camera_to_world"]) for p in journal["poses"]}
        score, align = trajectory(truth, native)
        shape = surface(replay / "scan.ply", align, o3d.io.read_triangle_mesh(str(synthetic / "ground_truth_rigid.ply")),
                        o3d.io.read_triangle_mesh(str(synthetic / "ground_truth_arms.ply")))
        assert shape["accuracy_mm_median"] < 3.0 and shape["surface_beyond_1cm"] < 0.05, shape
        assert (replay / "scan.obj").is_file() and (replay / "scan-albedo.png").is_file()
        print(f"Fusion nativo en el marco de cámara: mediana {shape['accuracy_mm_median']:.2f} mm, "
              f"{shape['surface_beyond_1cm']:.1%} de superficie a más de 1 cm; rotación RMS {score['rotation_deg_rms']:.2f}°")


if __name__ == "__main__":
    main()
