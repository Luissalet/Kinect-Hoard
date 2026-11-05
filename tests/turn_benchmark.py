"""Score native and refined turn scans of a synthetic sequence against its ground truth.

Usage: turn_benchmark.py SYNTHETIC_DIR REPLAY_DIR [--json OUT]
SYNTHETIC_DIR holds ground_truth.json and the ground-truth meshes written by
turn_synthetic.py; REPLAY_DIR is the native ``--scanner-replay`` output, after
``turn_refine.py REPLAY_DIR`` has written REPLAY_DIR/refined/.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import open3d as o3d


def _angle(transform) -> float:
    return math.degrees(math.acos(float(np.clip((np.trace(transform[:3, :3]) - 1) / 2, -1, 1))))


def trajectory(truth: dict, estimate: dict) -> tuple[dict | None, np.ndarray]:
    common = sorted(set(truth) & set(estimate))
    if not common:
        return None, np.eye(4)
    align = truth[common[0]] @ np.linalg.inv(estimate[common[0]])
    rotation, translation = [], []
    for key in common:
        error = np.linalg.inv(truth[key]) @ (align @ estimate[key])
        rotation.append(_angle(error))
        translation.append(float(np.linalg.norm(error[:3, 3])) * 1000)
    return {"frames": len(common), "rotation_deg_rms": round(float(np.sqrt(np.mean(np.square(rotation)))), 3),
            "rotation_deg_max": round(float(np.max(rotation)), 3), "rotation_deg_final": round(rotation[-1], 3),
            "translation_mm_rms": round(float(np.sqrt(np.mean(np.square(translation)))), 2),
            "translation_mm_max": round(float(np.max(translation)), 2),
            "translation_mm_final": round(translation[-1], 2)}, align


def surface(mesh_path: Path, align: np.ndarray, rigid, arms, legacy_mirror: bool = False) -> dict | None:
    """Accuracy/completeness against ground truth; legacy native exports are tried X-mirrored too."""
    if not mesh_path.is_file():
        return None
    results = [_surface(mesh_path, align, rigid, arms, False)]
    if legacy_mirror:
        results.append(_surface(mesh_path, align, rigid, arms, True))
    results = [r for r in results if r is not None]
    return max(results, key=lambda r: r["completeness_within_1cm"]) if results else None


def _surface(mesh_path: Path, align: np.ndarray, rigid, arms, mirror: bool) -> dict | None:
    mesh = o3d.io.read_triangle_mesh(str(mesh_path))
    if not mesh.has_triangles():
        return None
    mesh.remove_duplicated_vertices()
    if mirror:
        # Same correction as quality_scan.legacy_fusion_to_camera, One intrinsics.
        intrinsics = json.loads((mesh_path.parent / "session.intrinsics.json").read_text(encoding="utf-8"))["intrinsics"]
        legacy = np.eye(4)
        legacy[0, 0] = -1.0
        legacy[0, 2] = (intrinsics["width"] - 1 - 2 * intrinsics["cx"]) / intrinsics["fx"]
        mesh.transform(legacy)
    mesh.transform(align)
    truth = o3d.t.geometry.RaycastingScene()
    truth.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(rigid))
    truth.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(arms))
    points = np.asarray(mesh.sample_points_uniformly(60_000).points, dtype=np.float32)
    accuracy = truth.compute_distance(o3d.core.Tensor(points)).numpy() * 1000
    reconstruction = o3d.t.geometry.RaycastingScene()
    reconstruction.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    reference = np.asarray(rigid.sample_points_uniformly(60_000).points, dtype=np.float32)
    # Leg tips touch the floor, which the subject mask removes on purpose.
    reference = reference[reference[:, 1] < np.percentile(reference[:, 1], 97)]
    completeness = reconstruction.compute_distance(o3d.core.Tensor(reference)).numpy() * 1000
    return {"orientation": "legacy_fusion_corrected" if mirror else "as_saved",
            "accuracy_mm_median": round(float(np.median(accuracy)), 2),
            "accuracy_mm_p90": round(float(np.percentile(accuracy, 90)), 2),
            "surface_beyond_1cm": round(float(np.mean(accuracy > 10)), 4),
            "completeness_within_1cm": round(float(np.mean(completeness < 10)), 4),
            "completeness_within_5mm": round(float(np.mean(completeness < 5)), 4)}


def score(synthetic: Path, replay: Path) -> dict:
    truth_report = json.loads((synthetic / "ground_truth.json").read_text(encoding="utf-8"))
    truth = {p["timestamp_ticks_utc"]: np.asarray(p["camera_to_world"]) for p in truth_report["poses"]}
    native_journal = json.loads((replay / "live.scan.json").read_text(encoding="utf-8"))
    native = {p["timestamp_ticks_utc"]: np.asarray(p["camera_to_world"]) for p in native_journal["poses"]}
    refined_report = json.loads((replay / "refined" / "refine.json").read_text(encoding="utf-8"))
    refined = {p["timestamp_ticks_utc"]: np.asarray(p["camera_to_world"]) for p in refined_report["poses"]}
    rigid = o3d.io.read_triangle_mesh(str(synthetic / "ground_truth_rigid.ply"))
    arms = o3d.io.read_triangle_mesh(str(synthetic / "ground_truth_arms.ply"))
    native_traj, native_align = trajectory(truth, native)
    refined_traj, refined_align = trajectory(truth, refined)
    return {"format": "KINECT_HOARD_TURN_BENCHMARK_1", "synthetic": str(synthetic),
            "turns": truth_report["turns"], "arm_swing_degrees": truth_report["arm_swing_degrees"],
            "archived_frames": len(native),
            "native": {"trajectory": native_traj,
                       "surface": surface(replay / "scan.ply", native_align, rigid, arms,
                                          native_journal.get("mesh_coordinate_space") != "camera")},
            "refined": {"trajectory": refined_traj,
                        "surface": surface(replay / "refined" / "refined.ply", refined_align, rigid, arms),
                        "loop_edges": refined_report["loop_edges"], "seconds": refined_report["seconds"]}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("synthetic", type=Path)
    parser.add_argument("replay", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = score(args.synthetic, args.replay)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if args.json:
        args.json.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
