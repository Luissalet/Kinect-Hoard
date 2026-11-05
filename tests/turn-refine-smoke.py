"""Offline turn refinement on a synthetic person turning with swinging arms.

Run with .venv-scan/Scripts/python.exe tests/turn-refine-smoke.py
Checks the refined trajectory and surface against ground truth, the
front/back-swap guard, and the OBJ/MTL/PNG contract.
"""

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import open3d as o3d

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import turn_refine  # noqa: E402
from turn_benchmark import trajectory, surface  # noqa: E402
from turn_synthetic import generate  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary) / "live-synthetic"
        # 2.5 views per second, as the live scanner archives them.
        generate(folder, turn_seconds=24.0, fps=2.5, turns=1.12, swing_degrees=12.0)
        options = turn_refine.RefineOptions(texture_size=1024, texture_frames=12, max_triangles=60_000)
        report = turn_refine.refine(folder, options)
        truth = {p["timestamp_ticks_utc"]: np.asarray(p["camera_to_world"])
                 for p in json.loads((folder / "ground_truth.json").read_text(encoding="utf-8"))["poses"]}
        refined = {p["timestamp_ticks_utc"]: np.asarray(p["camera_to_world"]) for p in report["poses"]}
        score, align = trajectory(truth, refined)
        assert score["frames"] >= 0.9 * len(truth), score
        assert score["rotation_deg_rms"] < 4.0 and score["rotation_deg_max"] < 12.0, score
        assert score["rotation_deg_final"] < 4.0, score
        shape = surface(folder / "refined" / "refined.ply", align,
                        o3d.io.read_triangle_mesh(str(folder / "ground_truth_rigid.ply")),
                        o3d.io.read_triangle_mesh(str(folder / "ground_truth_arms.ply")))
        # 15 degrees between archived views; the native trajectory scores 34 mm here.
        assert shape["accuracy_mm_median"] < 5.0 and shape["completeness_within_1cm"] > 0.7, shape
        assert report["metrics"]["refined"]["turn_coverage"] > 0.9, report["metrics"]["refined"]
        assert report["metrics"]["native"]["trajectory"] is None  # synthetic input carries no native poses
        obj = (folder / "refined" / "refined.obj").read_text(encoding="ascii")
        assert obj.startswith("mtllib refined.mtl") and "\nvt " in obj
        assert "map_Kd refined-albedo.png" in (folder / "refined" / "refined.mtl").read_text(encoding="utf-8")
        assert (folder / "refined" / "refined-albedo.png").stat().st_size > 10_000
        progress = json.loads((folder / "refined" / "progress.json").read_text(encoding="utf-8"))
        assert progress["state"] == "finished"
        print(f"Refinado: {score['frames']} vistas, rotación RMS {score['rotation_deg_rms']:.2f}°, "
              f"final {score['rotation_deg_final']:.2f}°, superficie mediana {shape['accuracy_mm_median']:.2f} mm, "
              f"completitud a 1 cm {shape['completeness_within_1cm']:.0%}, {report['seconds']:.0f} s")


if __name__ == "__main__":
    main()
