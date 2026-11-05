"""Score a live-scanner replay against its reference.

A replay (``captures/replay-*``) is a saved take fed through the live engine
at its recorded pace (``--scanner-replay`` / ``--scanner-replay-server``).
Depending on the source take it measures:

* synthetic turn (``ground_truth.json``): rotation and translation error of
  the live trajectory against the known pose, and accuracy/completeness of
  the live mesh against the true surface;
* recorded take refined offline (``refined/refine.json``): pose error and
  overlap on the refine's held-out control pairs (cached in
  ``refined/control_pairs.json``) for the poses recorded live, this replay
  and the refined trajectory;
* both: mesh-to-depth residual of the live mesh with the refine's subject
  masks, and the live engine's per-frame latency against the 30 fps budget.

Writes ``replay-score.json`` in the replay folder.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

FORMAT = "KINECT_HOARD_REPLAY_SCORE_1"


def _angle(transform) -> float:
    return math.degrees(math.acos(float(np.clip((np.trace(transform[:3, :3]) - 1) / 2, -1, 1))))


def _poses(entries) -> dict:
    return {int(e["timestamp_ticks_utc"]): np.asarray(e["camera_to_world"], dtype=np.float64) for e in entries or []}


def trajectory_error(truth: dict, estimate: dict) -> tuple[dict | None, np.ndarray]:
    """Error of an estimated trajectory against ground truth, aligned on their first common frame."""
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
    import open3d as o3d

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


def control_pairs(source: Path, options, intrinsic, frames, o3d) -> tuple[dict, list]:
    """The refine's held-out pairs with their independent measurements, recomputed once and cached."""
    from turn_refine import _cloud, validation_pairs

    report = json.loads((source / "refined" / "refine.json").read_text(encoding="utf-8"))
    by_index = {f.index: f for f in frames}
    cache = source / "refined" / "control_pairs.json"
    pairs = None
    if cache.is_file():
        data = json.loads(cache.read_text(encoding="utf-8"))
        if data.get("refine_seconds") == report.get("seconds"):
            pairs = [(by_index[a], by_index[b], None if m is None else np.asarray(m)) for a, b, m in data["pairs"]]
    if pairs is None:
        accepted = []
        for entry in report["poses"]:
            frame = by_index[entry["frame"]]
            frame.pose = np.asarray(entry["camera_to_world"], dtype=np.float64)
            accepted.append(frame)
        for frame in accepted:
            frame.cloud = _cloud(frame, intrinsic, options, o3d)
        loops = [(a, b, None) for a, b in report.get("loop_pairs", [])]
        pairs = validation_pairs(accepted, loops, options, o3d, lambda *args: None)
        cache.write_text(json.dumps({"refine_seconds": report.get("seconds"),
                                     "pairs": [[a.index, b.index, None if m is None else m.tolist()] for a, b, m in pairs]}),
                         encoding="utf-8")
    for a, b, _ in pairs:
        for frame in (a, b):
            if frame.cloud is None:
                frame.cloud = _cloud(frame, intrinsic, options, o3d)
    return report, pairs


def score(replay: Path) -> dict:
    import open3d as o3d
    from turn_refine import RefineOptions, load, mesh_metrics, segment, trajectory_metrics

    started = time.time()
    replay = Path(replay).resolve()
    manifest = json.loads((replay / "live.scan.json").read_text(encoding="utf-8"))
    source = Path(manifest.get("replay_source") or "")
    if not (source / "session.khr").is_file():
        raise FileNotFoundError("La reproducción no indica una toma de origen con session.khr")
    tracked = _poses(manifest.get("trajectory"))
    archived = _poses(manifest.get("poses"))
    result = {"format": FORMAT, "replay": replay.name, "source": source.name, "tracker": manifest.get("tracker"),
              "replay_feed": manifest.get("replay"), "frames_tracked": len(tracked), "frames_archived": len(archived),
              "frames_integrated": manifest.get("frames_integrated"), "frames_rejected": manifest.get("frames_rejected"),
              "tracking": manifest.get("tracking"), "latency": manifest.get("latency")}

    options = RefineOptions()
    _, intrinsic, _, frames = load(source, options, o3d)
    segment(frames, intrinsic, options, o3d)
    by_ticks = {f.timestamp: f for f in frames}
    replay_by_index = {by_ticks[t].index: p for t, p in tracked.items() if t in by_ticks}

    truth_path = source / "ground_truth.json"
    if truth_path.is_file():
        truth_report = json.loads(truth_path.read_text(encoding="utf-8"))
        truth = _poses(truth_report["poses"])
        traj, align = trajectory_error(truth, tracked)
        archived_traj, _ = trajectory_error(truth, archived)
        rigid = o3d.io.read_triangle_mesh(str(source / "ground_truth_rigid.ply"))
        arms = o3d.io.read_triangle_mesh(str(source / "ground_truth_arms.ply"))
        result["synthetic"] = {"turns": truth_report.get("turns"), "frames": len(truth),
                               "trajectory": traj, "trajectory_archived": archived_traj,
                               "surface": surface(replay / "scan.ply", align, rigid, arms)}

    if (source / "refined" / "refine.json").is_file():
        report, pairs = control_pairs(source, options, intrinsic, frames, o3d)
        native = _poses(json.loads((source / "live.scan.json").read_text(encoding="utf-8")).get("poses"))
        native_by_index = {by_ticks[t].index: p for t, p in native.items() if t in by_ticks}
        refined_by_index = {e["frame"]: np.asarray(e["camera_to_world"], dtype=np.float64) for e in report["poses"]}
        result["control_pairs"] = {
            "pairs": len(pairs),
            "replay": trajectory_metrics(pairs, replay_by_index, o3d),
            "recorded_live": trajectory_metrics(pairs, native_by_index, o3d) if native_by_index else None,
            "refined": trajectory_metrics(pairs, refined_by_index, o3d)}
        result["reference_mesh"] = {"recorded_live": report["metrics"]["native"].get("mesh"),
                                    "refined": report["metrics"]["refined"].get("mesh")}

    mesh_path = replay / "scan.ply"
    if mesh_path.is_file() and replay_by_index:
        mesh = o3d.io.read_triangle_mesh(str(mesh_path))
        mesh.remove_duplicated_vertices()
        subject = [f for f in frames if f.index in replay_by_index and f.mask is not None]
        sample = subject[::max(1, len(subject) // 60)]
        result["mesh"] = mesh_metrics(mesh, sample, replay_by_index, intrinsic, o3d)
    result["subject_frames"] = sum(f.status == "subject" for f in frames)
    result["tracked_without_subject"] = sum(1 for f in frames if f.index in replay_by_index and f.mask is None)
    result["seconds"] = round(time.time() - started, 1)
    (replay / "replay-score.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--score-replay", dest="replay", type=Path, required=True,
                        help="Carpeta captures/replay-* escrita por el escáner en directo")
    args = parser.parse_args()
    result = score(args.replay)
    print(json.dumps({k: result.get(k) for k in ("replay", "tracker", "synthetic", "control_pairs", "mesh", "latency")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
