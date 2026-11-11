"""Motion capture without Kinect, end to end on a synthetic two-camera take with ground truth.

Run with .venv-mocap/Scripts/python.exe tests/mocap-smoke.py. Checks: ChArUco PDF at true
scale; ChArUco calibration against the true cameras; triangulation with the known calibration
and with the ChArUco one; calibration from body points; monocular root solve; the BVH read back
and compared with the points; the GLB read back and compared with the BVH; the check video;
the command line with its progress file; and, when Blender is installed, Blender importing the
BVH and the GLB headless.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import mocap  # noqa: E402
import mocap_synthetic as synthetic  # noqa: E402


def load_points(take: Path) -> np.ndarray:
    data = json.loads((take / "skeleton.json").read_text(encoding="utf-8"))
    return np.array([[p if p is not None else [np.nan] * 3 for p in frame] for frame in data["positions"]], float)


def calibration_frame_points(take: Path, report: dict) -> np.ndarray:
    """skeleton.json is aligned to the floor; undo that to get points in the calibration's frame."""
    rotation = np.array(report["world_alignment"]["rotation"])
    offset = np.array(report["world_alignment"]["offset"])
    return (load_points(take) + offset) @ rotation


def similarity_error(a: np.ndarray, b: np.ndarray):
    ok = np.isfinite(a).all(1) & np.isfinite(b).all(1)
    a, b = a[ok], b[ok]
    ma, mb = a.mean(0), b.mean(0)
    A, B = a - ma, b - mb
    U, S, Vt = np.linalg.svd(B.T @ A)
    D = np.eye(3)
    D[2, 2] = np.sign(np.linalg.det(U @ Vt))
    R = U @ D @ Vt
    s = (S * np.diag(D)).sum() / (A ** 2).sum()
    return np.linalg.norm((s * (R @ A.T)).T + mb - b, axis=1), s


def blender() -> Path | None:
    roots = sorted(Path(os.environ.get("ProgramFiles", r"C:\Program Files")).glob("Blender Foundation/Blender */blender.exe"),
                   key=lambda p: [int(v) for v in re.findall(r"\d+", p.parent.name)], reverse=True)
    return roots[0] if roots else None


BLENDER_CHECK = r'''
import bpy, json, sys
bvh, glb, out = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_anim.bvh(filepath=bvh, global_scale=0.01, update_scene_fps=True, update_scene_duration=True)
arm = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
scene = bpy.context.scene
scene.frame_set(scene.frame_start)
start, end = arm.animation_data.action.frame_range
bvh_info = {"bones": len(arm.data.bones), "frame_start": int(round(start)), "frame_end": int(round(end)),
            "head_z": (arm.matrix_world @ arm.pose.bones["Head"].head).z}
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
glb_info = {"armatures": len(arms), "bones": len(arms[0].data.bones) if arms else 0, "meshes": len(meshes),
            "actions": len(bpy.data.actions)}
json.dump({"bvh": bvh_info, "glb": glb_info}, open(out, "w"))
'''


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="kinect-mocap-"))
    results = {}

    # 1. Board PDF at true scale.
    pdf = mocap.board_pdf(work / "board.pdf", mocap.board_spec())
    text = (work / "board.pdf").read_bytes()
    box = [float(v) for v in re.search(rb"/MediaBox \[\s*0 0 ([\d.]+) ([\d.]+)", text).groups()]
    assert abs(box[0] - 595.3) < 2 and abs(box[1] - 841.9) < 2, box  # A4 in points
    results["board_pdf_points"] = box

    # 2. Synthetic take and ChArUco calibration.
    take = work / "mocap-synthetic"
    truth = synthetic.build(take, frames=90, board_frames=90)
    calibration = mocap.calibrate_charuco(mocap.list_videos(take / "calib"), synthetic.BOARD, mocap.Progress(take, "c.json"))
    gt = synthetic.ground_truth_cameras()
    R_rel = gt[1]["R"] @ gt[0]["R"].T
    t_rel = gt[1]["t"] - R_rel @ gt[0]["t"]
    cam1 = calibration["cameras"][1]
    rotation_error = math.degrees(np.linalg.norm(cv2.Rodrigues(np.asarray(cam1["R"]) @ R_rel.T)[0]))
    translation_error = float(np.linalg.norm(np.asarray(cam1["t"]) - t_rel))
    focal_error = max(abs(c["K"][0, 0] / synthetic.FOCAL - 1) for c in calibration["cameras"])
    assert rotation_error < 0.5 and translation_error < 0.03 and focal_error < 0.02, (rotation_error, translation_error, focal_error)
    results["charuco"] = {"rotation_deg": rotation_error, "translation_m": translation_error, "focal_rel": focal_error,
                          "rms_px": calibration["reprojection_rms_px"]}

    # 3. Triangulation with the known calibration.
    known = {"method": "known", "cameras": [{"name": f"cam{c}", "size": [synthetic.WIDTH, synthetic.HEIGHT], "K": g["K"],
                                             "dist": np.zeros(5), "R": g["R"], "t": g["t"]} for c, g in enumerate(gt)]}
    mocap.write_json(take / "calibration.json", known)
    report = mocap.process(take, {"detector": "synthetic-markers", "check_video": True}, mocap.Progress(take))
    error = np.linalg.norm(calibration_frame_points(take, report)[:, mocap.CORE] - truth[:, mocap.CORE], axis=-1)
    assert np.nanmedian(error) < 0.005 and np.nanpercentile(error, 95) < 0.02, (np.nanmedian(error), np.nanpercentile(error, 95))
    assert report["reprojection_px_median"] < 0.5 and report["core_points_valid"] == 1.0
    results["known_calibration_mm"] = {"median": 1000 * float(np.nanmedian(error)), "p95": 1000 * float(np.nanpercentile(error, 95))}

    # 4. BVH read back: frames, channels and forward kinematics against the points.
    bvh = mocap.read_bvh(take / "motion.bvh")
    assert bvh["frames"] == len(truth) and bvh["channels"] == 6 + 3 * (len(mocap.JOINT_NAMES) - 1)
    assert abs(bvh["frame_time"] - 1 / synthetic.FPS) < 1e-5
    assert report["bvh"]["fk_error_mm_median"] < 5 and report["bvh"]["fk_error_mm_p95"] < 15, report["bvh"]
    results["bvh_fk_mm"] = {k: report["bvh"][k] for k in ("fk_error_mm_median", "fk_error_mm_p95")}

    # 5. GLB read back: same joints and same world positions as the BVH (metres vs centimetres).
    glb = mocap.read_glb(take / "motion.glb")
    assert glb["keys"] == len(truth)
    worst = 0.0
    for name in mocap.JOINT_NAMES:
        a = glb["positions"][:, glb["names"].index(name)]
        b = bvh["positions"][:, bvh["names"].index(name)] / 100.0
        worst = max(worst, float(np.max(np.linalg.norm(a - b, axis=-1))))
    assert worst < 1e-3, worst
    results["glb_vs_bvh_max_mm"] = worst * 1000

    # 6. Check video: one frame per instant, browser-friendly size.
    capture = cv2.VideoCapture(str(take / "check.mp4"))
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    ok, frame = capture.read()
    capture.release()
    assert ok and abs(frames - len(truth)) <= 1 and frame.shape[1] == 1280, (frames, frame.shape if ok else None)

    # 7. ChArUco calibration used for triangulation.
    mocap.write_json(take / "calibration.json", calibration)
    report = mocap.process(take, {"detector": "synthetic-markers", "check_video": False}, mocap.Progress(take))
    truth_cam0 = truth @ gt[0]["R"].T + gt[0]["t"]
    error = np.linalg.norm(calibration_frame_points(take, report)[:, mocap.CORE] - truth_cam0[:, mocap.CORE], axis=-1)
    assert np.nanmedian(error) < 0.03, np.nanmedian(error)
    results["charuco_triangulation_mm"] = 1000 * float(np.nanmedian(error))

    # 8. Calibration from body points (no board), with the true field of view and the subject's height.
    (take / "calibration.json").unlink()
    fov = math.degrees(2 * math.atan(synthetic.WIDTH / 2 / synthetic.FOCAL))
    report = mocap.process(take, {"detector": "synthetic-markers", "check_video": False, "fov_degrees": fov,
                                  "subject_height_m": synthetic.HEIGHT_M}, mocap.Progress(take))
    assert report["method"] == "triangulation (body)"
    error, scale = similarity_error(load_points(take)[:, mocap.CORE].reshape(-1, 3), truth[:, mocap.CORE].reshape(-1, 3))
    assert np.median(error) < 0.01 and abs(scale - 1) < 0.05, (np.median(error), scale)
    results["body_calibration"] = {"shape_error_mm": 1000 * float(np.median(error)), "scale_error": float(scale - 1)}

    # 9. Monocular root: hip-centred metric landmarks plus 2D points give the camera-space body back.
    R, t = synthetic.camera(synthetic.CAMERA_POSITIONS[0])
    camera_points = truth @ R.T + t
    hips = (camera_points[:, mocap.IDX["left_hip"]] + camera_points[:, mocap.IDX["right_hip"]]) / 2
    world = camera_points - hips[:, None]
    norm = camera_points[..., :2] / camera_points[..., 2:3]
    conf = np.where(np.isfinite(norm).all(axis=-1), 1.0, 0.0)
    mono = mocap.mono_root(norm, conf, world)
    mono_error = np.nanmax(np.linalg.norm(mono[:, mocap.CORE] - camera_points[:, mocap.CORE], axis=-1))
    assert mono_error < 1e-6, mono_error

    # 10. Command line and progress file, as the MCP tool runs it.
    (take / "calibration.json").unlink()
    mocap.write_json(take / "calibration.json", known)
    run = subprocess.run([sys.executable, str(ROOT / "mocap.py"), "process", str(take), "--detector", "synthetic-markers",
                          "--no-video", "--filter", "savgol"], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr[-2000:]
    progress = json.loads((take / "progress.json").read_text(encoding="utf-8"))
    assert progress["state"] == "finished" and progress["result"]["frames"] == len(truth), progress

    # 11. Blender imports the BVH and the GLB headless (skipped when Blender is not installed).
    executable = blender()
    if executable:
        script = work / "blender_check.py"
        script.write_text(BLENDER_CHECK, encoding="utf-8")
        out = work / "blender.json"
        run = subprocess.run([str(executable), "-b", "--factory-startup", "--python", str(script), "--",
                              str(take / "motion.bvh"), str(take / "motion.glb"), str(out)],
                             capture_output=True, text=True, timeout=300)
        assert out.is_file(), run.stdout[-2000:] + run.stderr[-2000:]
        imported = json.loads(out.read_text(encoding="utf-8"))
        assert imported["bvh"]["bones"] == len(mocap.JOINT_NAMES)
        assert imported["bvh"]["frame_end"] - imported["bvh"]["frame_start"] + 1 == len(truth), imported
        assert 1.3 < imported["bvh"]["head_z"] < 1.9, imported
        assert imported["glb"]["armatures"] == 1 and imported["glb"]["meshes"] >= 1 and imported["glb"]["actions"] >= 1
        results["blender"] = {"version": executable.parent.name, **imported}
    else:
        results["blender"] = "no instalado"
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(results, ensure_ascii=False, indent=1, default=float))
    print("Captura de movimiento: calibración, triangulación, BVH, GLB y vídeo verificados")


if __name__ == "__main__":
    main()
