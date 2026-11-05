"""Score native and refined turn scans of a synthetic sequence against its ground truth.

Usage: turn_benchmark.py SYNTHETIC_DIR REPLAY_DIR [--json OUT]
SYNTHETIC_DIR holds ground_truth.json and the ground-truth meshes written by
turn_synthetic.py; REPLAY_DIR is the native ``--scanner-replay`` output, after
``turn_refine.py REPLAY_DIR`` has written REPLAY_DIR/refined/. The live replay
itself is scored by replay_score.py (replay-score.json), which shares these
trajectory and surface measures.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from replay_score import surface, trajectory_error as trajectory  # noqa: E402,F401


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
