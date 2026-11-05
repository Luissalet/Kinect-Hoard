"""Offline refinement of a live turn scan from its archived keyframes.

Runs on a ``captures/live-*`` folder written by the native live scanner (a
person or object turning before a fixed Kinect, or a camera moving around
it) and leaves the native result untouched. Outputs go to ``refined/``:

1. Subject mask: depth band, floor plane removal, depth-edge connected
   components, a vertical cylinder around the tracked subject axis and a
   continuity test that drops frames where the subject left the view.
2. Tracking: coarse-to-fine coloured ICP with a Tukey robust kernel against a
   local model of recent keyframes and a constant-velocity prior. Failures
   relocalise with FPFH + RANSAC against every keyframe so far.
3. Loop closure: frames that see the same side again after a long rotation
   are registered independently; a pose graph distributes the drift.
4. Small non-rigid motion: the robust kernel ignores moving limbs while
   tracking; before the final fusion, pixels that disagree with a first
   consensus surface are removed per frame (swinging arms, hands, cloth).
5. TSDF fusion, small-fragment removal, OBJ + MTL + PNG atlas.

``refine.json`` reports objective metrics computed with the same masks for
the native trajectory/mesh and the refined one: pairwise geometric
consistency on held-out frame pairs, mesh-to-depth residuals, loop-closure
error and turn coverage. There is no deformation field: posture changes
larger than the residual threshold are removed, not modelled.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from fusion import frames as read_frames, reconstruction_intrinsics

FORMAT = "KINECT_HOARD_TURN_REFINE_1"


@dataclass
class RefineOptions:
    radius: float = 0.5            # subject cylinder radius, metres
    near: float = 0.4
    far: float = 3.0
    min_pixels: int = 1500
    tsdf_voxel: float = 0.004
    icp_scales: tuple = (0.02, 0.01, 0.005)
    keyframe_degrees: float = 6.0
    local_keyframes: int = 6
    min_fitness: float = 0.45
    max_rmse: float = 0.008
    nonrigid_metres: float = 0.015
    texture_size: int = 2048
    texture_frames: int = 32
    max_triangles: int = 150_000
    stride: int = 1
    max_frames: int = 900


@dataclass
class TurnFrame:
    index: int
    timestamp: int
    rgb: np.ndarray
    depth: np.ndarray
    native_pose: np.ndarray | None = None
    base: np.ndarray | None = None
    mask: np.ndarray | None = None
    status: str = "pending"
    pose: np.ndarray | None = None
    cloud: object = None
    nonrigid_fraction: float = 0.0
    extra: dict = field(default_factory=dict)


def _angle(transform: np.ndarray) -> float:
    return math.degrees(math.acos(float(np.clip((np.trace(transform[:3, :3]) - 1) / 2, -1, 1))))


def _runs_mask(runs, size: int) -> np.ndarray:
    mask = np.zeros(size, dtype=bool)
    if len(runs) % 2:
        raise ValueError("Máscara de escaneo truncada")
    for start, count in zip(runs[::2], runs[1::2]):
        if start < 0 or count < 1 or start + count > size:
            raise ValueError("Máscara de escaneo fuera del fotograma")
        mask[start:start + count] = True
    return mask


class Progress:
    def __init__(self, path: Path | None):
        self.path, self.started = path, time.time()

    def __call__(self, stage: str, fraction: float, detail: str = "") -> None:
        if self.path is None:
            return
        self.path.write_text(json.dumps({"state": "running", "stage": stage, "progress": round(fraction, 3),
                                         "detail": detail, "elapsed_seconds": round(time.time() - self.started, 1)},
                                        ensure_ascii=False), encoding="utf-8")


def load(directory: Path, options: RefineOptions, o3d):
    manifest = json.loads((directory / "live.scan.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "KINECT_HOARD_LIVE_SCAN_1":
        raise ValueError("Sesión de escáner en directo incompatible")
    session = directory / "session.khr"
    data, mirrored = reconstruction_intrinsics(session)
    width, height = int(data["width"]), int(data["height"])
    intrinsic = o3d.camera.PinholeCameraIntrinsic(width, height, float(data["fx"]), float(data["fy"]),
                                                  float(data["cx"]), float(data["cy"]))
    journal = {entry["timestamp_ticks_utc"]: entry for entry in manifest.get("poses", [])}
    result = []
    for index, (timestamp, w, h, bgra, depth_bytes) in enumerate(read_frames(session)):
        if len(result) >= options.max_frames:
            break
        if index % options.stride:
            continue
        if (w, h) != (width, height):
            raise ValueError("Dimensiones distintas de los intrínsecos")
        depth = np.frombuffer(depth_bytes, dtype="<u2").reshape(h, w).copy()
        rgb = np.frombuffer(bgra, dtype=np.uint8).reshape(h, w, 4)[:, :, [2, 1, 0]].copy()
        entry = journal.get(timestamp, {})
        base = _runs_mask(entry["foreground_runs"], w * h).reshape(h, w) if "foreground_runs" in entry else None
        if mirrored:
            depth, rgb = depth[:, ::-1].copy(), rgb[:, ::-1].copy()
            base = None if base is None else base[:, ::-1].copy()
        native = np.asarray(entry["camera_to_world"], dtype=np.float64) if "camera_to_world" in entry else None
        result.append(TurnFrame(index, timestamp, rgb, depth, native, base))
    if not result:
        raise ValueError("La sesión no contiene fotogramas")
    return manifest, intrinsic, mirrored, result


def _floor_plane(frame: TurnFrame, intrinsic, options: RefineOptions, o3d):
    """Find a horizontal plane (camera Y points down) below the image centre, if one is visible."""
    fx, fy = intrinsic.get_focal_length()
    cx, cy = intrinsic.get_principal_point()
    v, u = np.mgrid[0:frame.depth.shape[0]:3, 0:frame.depth.shape[1]:3]
    z = frame.depth[::3, ::3].astype(np.float64) / 1000
    valid = (z > options.near) & (z < options.far + 1.5)
    points = np.column_stack(((u[valid] - cx) * z[valid] / fx, (v[valid] - cy) * z[valid] / fy, z[valid]))
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    for _ in range(3):
        if len(cloud.points) < 500:
            return None
        plane, inliers = cloud.segment_plane(0.015, 3, 400)
        normal = np.asarray(plane[:3])
        if abs(normal[1]) > 0.88 and len(inliers) > 0.05 * len(points):
            plane = np.asarray(plane) / np.linalg.norm(normal)
            if plane[1] > 0:  # make the normal point up (towards -Y)
                plane = -plane
            floor_points = np.asarray(cloud.points)[inliers]
            if np.median(floor_points[:, 1]) > np.median(points[:, 1]) - 0.05:
                return plane
        cloud = cloud.select_by_index(inliers, invert=True)
    return None


def segment(frames: list[TurnFrame], intrinsic, options: RefineOptions, o3d) -> dict:
    """Mask the subject in every frame and drop frames where it is not in view."""
    import cv2

    fx, fy = intrinsic.get_focal_length()
    cx, cy = intrinsic.get_principal_point()
    height, width = frames[0].depth.shape
    v, u = np.mgrid[0:height, 0:width]
    ray_x, ray_y = (u - cx) / fx, (v - cy) / fy
    floor = None
    for frame in frames[:10]:
        floor = _floor_plane(frame, intrinsic, options, o3d)
        if floor is not None:
            break
    axis = None          # subject axis (x, z) and mean height in camera space
    areas: list[int] = []
    absent = 0
    for frame in frames:
        z = frame.depth.astype(np.float32) / 1000
        valid = (z > options.near) & (z < options.far)
        if frame.base is not None:
            valid &= frame.base
        x, y = ray_x * z, ray_y * z
        if floor is not None:
            valid &= (floor[0] * x + floor[1] * y + floor[2] * z + floor[3]) > 0.025
        # Cut depth discontinuities so the subject separates from what lies behind it.
        jump = 0.02 + 0.01 * z
        cut = np.zeros_like(valid)
        dx = np.abs(z[:, 1:] - z[:, :-1]) > jump[:, 1:]
        dy = np.abs(z[1:, :] - z[:-1, :]) > jump[1:, :]
        cut[:, 1:] |= dx
        cut[:, :-1] |= dx
        cut[1:, :] |= dy
        cut[:-1, :] |= dy
        count, labels, stats, _ = cv2.connectedComponentsWithStats((valid & ~cut).astype(np.uint8), connectivity=4)
        order = [label for label in np.argsort(-stats[:, cv2.CC_STAT_AREA]) if label != 0][:16]
        components = []
        for label in order:
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < 250:
                break
            selected = labels == label
            centre = np.array([float(np.median(x[selected])), float(np.median(y[selected])), float(np.median(z[selected]))])
            components.append((label, area, centre, float(stats[label, cv2.CC_STAT_LEFT] + stats[label, cv2.CC_STAT_WIDTH] / 2)))
        if not components:
            frame.status, frame.mask = "subject_absent", None
            absent += 1
            continue
        if axis is None:
            # First view: the largest component, favouring the image centre.
            label, area, centre, column = max(components, key=lambda c: c[1] * (1.25 - abs(c[3] / width - 0.5)))
            candidate_axis = np.array([centre[0], centre[1], centre[2] + 0.08])
        else:
            candidate_axis = axis
        near_axis = [c for c in components if math.hypot(c[2][0] - candidate_axis[0], c[2][2] - candidate_axis[2]) < options.radius]
        if not near_axis:
            frame.status, frame.mask = "subject_absent", None
            absent += 1
            continue
        mask = np.isin(labels, [c[0] for c in near_axis])
        mask &= (x - candidate_axis[0]) ** 2 + (z - candidate_axis[2]) ** 2 < options.radius ** 2
        area = int(mask.sum())
        typical = float(np.median(areas[-15:])) if areas else area
        if area < max(options.min_pixels, 0.3 * typical):
            frame.status, frame.mask = "subject_absent", None
            absent += 1
            continue
        centre = np.array([float(np.median(x[mask])), float(np.median(y[mask])), float(np.median(z[mask])) + 0.08])
        if axis is not None and math.hypot(centre[0] - axis[0], centre[2] - axis[2]) > 0.35:
            frame.status, frame.mask = "subject_absent", None
            absent += 1
            continue
        axis = centre if axis is None else 0.85 * axis + 0.15 * centre
        areas.append(area)
        frame.mask, frame.status = mask, "subject"
    return {"floor_plane": None if floor is None else [round(float(c), 5) for c in floor],
            "subject_frames": sum(f.status == "subject" for f in frames), "subject_absent_frames": absent,
            "subject_axis_camera_metres": None if axis is None else [round(float(c), 4) for c in axis]}


def _masked_depth(frame: TurnFrame) -> np.ndarray:
    return np.where(frame.mask, frame.depth, 0).astype(np.uint16)


def _cloud(frame: TurnFrame, intrinsic, options: RefineOptions, o3d, depth=None):
    depth = _masked_depth(frame) if depth is None else depth
    rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
        o3d.geometry.Image(np.ascontiguousarray(frame.rgb)), o3d.geometry.Image(np.ascontiguousarray(depth)),
        depth_scale=1000.0, depth_trunc=options.far, convert_rgb_to_intensity=False)
    cloud = o3d.geometry.PointCloud.create_from_rgbd_image(rgbd, intrinsic)
    cloud = cloud.voxel_down_sample(0.004)
    cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=0.015, max_nn=30))
    cloud.orient_normals_towards_camera_location(np.zeros(3))
    return cloud


def _prepare(cloud, voxel, o3d):
    down = cloud.voxel_down_sample(voxel)
    down.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel * 2.5, max_nn=30))
    return down


def colored_icp(source, target, init, options: RefineOptions, o3d):
    """Coarse-to-fine coloured ICP; the Tukey kernel discounts limbs that moved."""
    reg = o3d.pipelines.registration
    transform = init
    result = None
    scales = tuple(options.icp_scales)
    for scale, iterations in zip(scales, [40] + [25] * (len(scales) - 2) + [15]):
        src, tgt = _prepare(source, scale, o3d), _prepare(target, scale, o3d)
        if len(src.points) < 30 or len(tgt.points) < 30:
            return None
        try:
            result = reg.registration_colored_icp(
                src, tgt, scale * 2.5, transform,
                reg.TransformationEstimationForColoredICP(0.95, reg.TukeyLoss(k=scale * 1.5)),
                reg.ICPConvergenceCriteria(relative_fitness=1e-6, relative_rmse=1e-6, max_iteration=iterations))
        except RuntimeError:
            return None
        transform = result.transformation
    check = reg.evaluate_registration(source, target, 0.01, transform)
    return transform, float(check.fitness), float(check.inlier_rmse)


def colour_agreement(source, target, transform, o3d, distance: float = 0.01) -> float:
    """Share of overlapping points whose colours match after alignment.

    Bodies and many objects are nearly symmetric in shape: a front/back
    swap can fit the geometry well but puts the wrong colours together.
    """
    points = np.asarray(source.points)
    colours = np.asarray(source.colors)
    if len(points) == 0 or not target.has_colors():
        return 0.0
    pick = np.linspace(0, len(points) - 1, min(len(points), 3000)).astype(int)
    moved = points[pick] @ transform[:3, :3].T + transform[:3, 3]
    tree = o3d.geometry.KDTreeFlann(target)
    # Chromaticity ignores the shading change of a surface turning towards
    # or away from the room lights.
    chroma = lambda c: c / np.maximum(c.sum(axis=-1, keepdims=True), 0.05)
    target_colours = chroma(np.asarray(target.colors))
    agree = total = 0
    for point, colour in zip(moved, chroma(colours[pick])):
        found, index, squared = tree.search_knn_vector_3d(point, 1)
        if found and squared[0] <= distance * distance:
            total += 1
            agree += float(np.abs(target_colours[index[0]] - colour).max()) < 0.05
    return agree / total if total >= 50 else 0.0


def global_register(source, target, options: RefineOptions, o3d, prior=None, max_deviation=None):
    """FPFH + RANSAC proposals refined by coloured ICP, for relocalisation and loops.

    Proposals are ranked by overlap times colour agreement, and with a prior
    only those within ``max_deviation`` degrees of it are kept.
    """
    reg = o3d.pipelines.registration
    voxel = 0.01
    src, tgt = _prepare(source, voxel, o3d), _prepare(target, voxel, o3d)
    if len(src.points) < 100 or len(tgt.points) < 100:
        return None
    param = o3d.geometry.KDTreeSearchParamHybrid(radius=voxel * 5, max_nn=100)
    src_f, tgt_f = reg.compute_fpfh_feature(src, param), reg.compute_fpfh_feature(tgt, param)
    best, best_score = None, 0.0
    for seed in range(3):
        o3d.utility.random.seed(seed + 1)
        proposal = reg.registration_ransac_based_on_feature_matching(
            src, tgt, src_f, tgt_f, True, voxel * 1.5, reg.TransformationEstimationPointToPoint(False), 3,
            [reg.CorrespondenceCheckerBasedOnEdgeLength(0.9), reg.CorrespondenceCheckerBasedOnDistance(voxel * 1.5)],
            reg.RANSACConvergenceCriteria(200_000, 0.999))
        refined = colored_icp(source, target, proposal.transformation, options, o3d)
        if refined is None:
            continue
        if prior is not None and max_deviation is not None and _angle(np.linalg.inv(prior) @ refined[0]) > max_deviation:
            continue
        agreement = colour_agreement(source, target, refined[0], o3d)
        if agreement < 0.3:
            continue
        if refined[1] * agreement > best_score:
            best, best_score = refined, refined[1] * agreement
    return best


def _accept(result, options: RefineOptions) -> bool:
    return result is not None and result[1] >= options.min_fitness and result[2] <= options.max_rmse


def _tracked(result, prediction, options: RefineOptions) -> bool:
    """Accept frame-to-model ICP near the motion prior; less overlap is allowed when very close to it."""
    if result is None or result[2] > options.max_rmse:
        return False
    deviation = np.linalg.inv(prediction) @ result[0]
    angle, shift = _angle(deviation), float(np.linalg.norm(deviation[:3, 3]))
    if angle >= 25 or shift >= 0.15:
        return False
    return result[1] >= options.min_fitness or (result[1] >= 0.3 and angle < 10 and shift < 0.05)


def _merge(clouds, poses, voxel, o3d):
    merged = o3d.geometry.PointCloud()
    for cloud, pose in zip(clouds, poses):
        merged += o3d.geometry.PointCloud(cloud).transform(pose)
    return merged.voxel_down_sample(voxel)


def track(frames: list[TurnFrame], intrinsic, options: RefineOptions, o3d, progress) -> dict:
    """Frame-to-model coloured ICP with constant-velocity prior and global relocalisation."""
    subject = [f for f in frames if f.status == "subject"]
    keyframes: list[TurnFrame] = []
    accepted: list[TurnFrame] = []
    relocalised = lost = 0
    velocity = np.eye(4)
    for number, frame in enumerate(subject):
        progress("tracking", number / max(1, len(subject)), f"{number}/{len(subject)}")
        frame.cloud = _cloud(frame, intrinsic, options, o3d)
        if len(frame.cloud.points) < 200:
            frame.status = "too_few_points"
            continue
        if not accepted:
            frame.pose, frame.status = np.eye(4), "tracked"
            accepted.append(frame)
            keyframes.append(frame)
            continue
        previous = accepted[-1]
        gap = frame.index - previous.index
        prediction = previous.pose @ (velocity if gap <= 3 else np.eye(4))
        local = keyframes[-options.local_keyframes:]
        model = _merge([k.cloud for k in local], [k.pose for k in local], 0.004, o3d)
        result = colored_icp(frame.cloud, model, prediction, options, o3d)
        if not _tracked(result, prediction, options):
            # Faster turn than predicted: widen the coarse scale before giving up.
            wide = RefineOptions(**{**options.__dict__, "icp_scales": (0.04, 0.02, 0.01, 0.005)})
            result = colored_icp(frame.cloud, model, prediction, wide, o3d)
        if not _tracked(result, prediction, options):
            everything = _merge([k.cloud for k in keyframes], [k.pose for k in keyframes], 0.005, o3d)
            # Right after a tracked frame the subject cannot have turned far;
            # the bound stops a symmetric front/back swap from being accepted.
            short_gap = gap <= 3
            result = global_register(frame.cloud, everything, options, o3d,
                                     prediction if short_gap else None, 30 if short_gap else None)
            if not _accept(result, options):
                frame.status = "lost"
                lost += 1
                continue
            frame.status = "relocalised"
            relocalised += 1
        else:
            frame.status = "tracked"
        frame.pose = result[0]
        frame.extra["fitness"], frame.extra["rmse"] = result[1], result[2]
        step = np.linalg.inv(previous.pose) @ frame.pose
        velocity = step if frame.status == "tracked" and gap <= 3 else np.eye(4)
        accepted.append(frame)
        last_key = keyframes[-1]
        relative = np.linalg.inv(last_key.pose) @ frame.pose
        if _angle(relative) >= options.keyframe_degrees or np.linalg.norm(relative[:3, 3]) >= 0.03:
            keyframes.append(frame)
    # A frame lost early may fit once the model covers more of the subject.
    retried = 0
    if lost and len(keyframes) >= 3:
        everything = _merge([k.cloud for k in keyframes], [k.pose for k in keyframes], 0.005, o3d)
        for frame in [f for f in subject if f.status == "lost"]:
            neighbour = min(accepted, key=lambda f: abs(f.index - frame.index))
            close = abs(neighbour.index - frame.index) <= 3
            result = global_register(frame.cloud, everything, options, o3d,
                                     neighbour.pose if close else None, 30 if close else None)
            if _accept(result, options):
                frame.pose, frame.status = result[0], "relocalised"
                frame.extra["fitness"], frame.extra["rmse"] = result[1], result[2]
                retried += 1
        accepted = [f for f in subject if f.status in ("tracked", "relocalised")]
        accepted.sort(key=lambda f: f.index)
    return {"accepted": accepted, "keyframes": len(keyframes), "relocalised": relocalised + retried,
            "lost": sum(f.status == "lost" for f in subject)}


def _cumulative_rotation(poses) -> np.ndarray:
    steps = [0.0] + [_angle(np.linalg.inv(a) @ b) for a, b in zip(poses[:-1], poses[1:])]
    return np.cumsum(steps)


def _measure(a: TurnFrame, b: TurnFrame, options: RefineOptions, o3d, allow_global: bool):
    """Independent relative transform a -> b (maps a's camera points into b's camera)."""
    guess = np.linalg.inv(b.pose) @ a.pose
    result = colored_icp(a.cloud, b.cloud, guess, options, o3d)
    if not _accept(result, options) and allow_global:
        result = global_register(a.cloud, b.cloud, options, o3d, guess, 35)
    if not _accept(result, options):
        return None
    disagreement = np.linalg.inv(guess) @ result[0]
    if _angle(disagreement) > 35 or np.linalg.norm(disagreement[:3, 3]) > 0.25:
        return None
    return result


def loop_candidates(accepted: list[TurnFrame], minimum_turn: float = 150, limit: int = 48):
    poses = [f.pose for f in accepted]
    turn = _cumulative_rotation(poses)
    candidates = []
    for i in range(0, len(accepted), 2):
        for j in range(i + 6, len(accepted), 2):
            travelled = turn[j] - turn[i]
            if travelled < minimum_turn:
                continue
            view = _angle(np.linalg.inv(poses[j]) @ poses[i])
            if view <= 40:
                candidates.append((travelled - 2 * view, i, j))
    candidates.sort(reverse=True)
    chosen, used = [], set()
    for _, i, j in candidates:
        if (i // 4, j // 4) in used:
            continue
        used.add((i // 4, j // 4))
        chosen.append((i, j))
        if len(chosen) >= limit:
            break
    return chosen, float(turn[-1]) if len(turn) else 0.0


def optimise(accepted: list[TurnFrame], options: RefineOptions, o3d, progress) -> dict:
    """Pose graph over accepted frames: odometry edges plus verified loop closures."""
    reg = o3d.pipelines.registration
    graph = reg.PoseGraph()
    for frame in accepted:
        graph.nodes.append(reg.PoseGraphNode(frame.pose.copy()))
    for s in range(len(accepted) - 1):
        a, b = accepted[s], accepted[s + 1]
        transform = np.linalg.inv(b.pose) @ a.pose
        info = reg.get_information_matrix_from_point_clouds(a.cloud, b.cloud, 0.01, transform)
        graph.edges.append(reg.PoseGraphEdge(s, s + 1, transform, info, uncertain=b.status == "relocalised"))
    pairs, travelled = loop_candidates(accepted)
    loops = []
    for number, (i, j) in enumerate(pairs):
        progress("loop_closure", number / max(1, len(pairs)), f"{number}/{len(pairs)}")
        result = _measure(accepted[i], accepted[j], options, o3d, allow_global=True)
        if result is None:
            continue
        info = reg.get_information_matrix_from_point_clouds(accepted[i].cloud, accepted[j].cloud, 0.01, result[0])
        graph.edges.append(reg.PoseGraphEdge(i, j, result[0], info, uncertain=True))
        loops.append((i, j, result[0]))
    before = loop_errors(accepted, [f.pose for f in accepted], loops)
    if loops:
        reg.global_optimization(
            graph, reg.GlobalOptimizationLevenbergMarquardt(), reg.GlobalOptimizationConvergenceCriteria(),
            reg.GlobalOptimizationOption(max_correspondence_distance=0.01, edge_prune_threshold=0.25,
                                         preference_loop_closure=2.0, reference_node=0))
        for frame, node in zip(accepted, graph.nodes):
            frame.pose = np.asarray(node.pose).copy()
    after = loop_errors(accepted, [f.pose for f in accepted], loops)
    return {"loop_candidates": len(pairs), "loop_edges": len(loops),
            "rotation_travelled_degrees": round(travelled, 1),
            "loop_error_before": before, "loop_error_after": after,
            "loops": [(accepted[i].index, accepted[j].index, t) for i, j, t in loops]}


def loop_errors(accepted, poses, loops) -> dict | None:
    if not loops:
        return None
    rotations, translations = [], []
    for i, j, measured in loops:
        error = np.linalg.inv(measured) @ (np.linalg.inv(poses[j]) @ poses[i])
        rotations.append(_angle(error))
        translations.append(float(np.linalg.norm(error[:3, 3])) * 1000)
    return {"pairs": len(loops), "rotation_deg_median": round(float(np.median(rotations)), 3),
            "rotation_deg_max": round(float(np.max(rotations)), 3),
            "translation_mm_median": round(float(np.median(translations)), 2),
            "translation_mm_max": round(float(np.max(translations)), 2)}


def _renderer(mesh, intrinsic, o3d):
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    fx, fy = intrinsic.get_focal_length()
    cx, cy = intrinsic.get_principal_point()
    v, u = np.mgrid[0:intrinsic.height, 0:intrinsic.width].astype(np.float32)
    rays = np.stack(((u - cx) / fx, (v - cy) / fy, np.ones_like(u)), axis=-1)

    def render(pose):
        directions = rays @ pose[:3, :3].T.astype(np.float32)
        origins = np.broadcast_to(pose[:3, 3].astype(np.float32), directions.shape)
        hit = scene.cast_rays(o3d.core.Tensor(np.ascontiguousarray(np.concatenate((origins, directions), axis=-1))))
        depth = hit["t_hit"].numpy()
        depth[~np.isfinite(depth)] = 0
        return depth
    return render


def integrate(frames, intrinsic, options: RefineOptions, o3d, depths=None):
    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=options.tsdf_voxel, sdf_trunc=options.tsdf_voxel * 4,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    for number, frame in enumerate(frames):
        depth = _masked_depth(frame) if depths is None else depths[number]
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(np.ascontiguousarray(frame.rgb)), o3d.geometry.Image(np.ascontiguousarray(depth)),
            depth_scale=1000.0, depth_trunc=options.far, convert_rgb_to_intensity=False)
        volume.integrate(rgbd, intrinsic, np.linalg.inv(frame.pose))
    mesh = volume.extract_triangle_mesh()
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_unreferenced_vertices()
    return mesh


def keep_main_surface(mesh, o3d) -> tuple:
    """Drop floating fragments: keep clusters with at least 3 % of the largest one."""
    if not mesh.has_triangles():
        return mesh, 0
    clusters, counts, _ = mesh.cluster_connected_triangles()
    clusters, counts = np.asarray(clusters), np.asarray(counts)
    keep = counts >= max(50, 0.03 * counts.max())
    mesh.remove_triangles_by_mask(~keep[clusters])
    mesh.remove_unreferenced_vertices()
    return mesh, int((~keep).sum())


def nonrigid_masks(frames, mesh, intrinsic, options: RefineOptions, o3d, progress) -> list[np.ndarray]:
    """Remove per-frame pixels that disagree with the consensus surface (moved limbs)."""
    render = _renderer(mesh, intrinsic, o3d)
    depths = []
    for number, frame in enumerate(frames):
        progress("nonrigid", number / max(1, len(frames)), f"{number}/{len(frames)}")
        observed = _masked_depth(frame).astype(np.float32) / 1000
        predicted = render(frame.pose)
        both = (observed > 0) & (predicted > 0)
        outlier = both & (np.abs(observed - predicted) > options.nonrigid_metres)
        # Grow the rejected region slightly so the boundary of a moved limb goes too.
        import cv2
        outlier = cv2.dilate(outlier.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & (observed > 0)
        frame.nonrigid_fraction = float(outlier.sum() / max(1, (observed > 0).sum()))
        depths.append(np.where(outlier, 0, _masked_depth(frame)).astype(np.uint16))
    return depths


def validation_pairs(accepted: list[TurnFrame], loops, options: RefineOptions, o3d, progress, limit: int = 40):
    """Held-out pairs 15-45 degrees apart, measured independently and never added to the graph."""
    used = {(a, b) for a, b, _ in loops}
    turn = _cumulative_rotation([f.pose for f in accepted])
    chosen = []
    step = max(1, len(accepted) // limit)
    for i in range(0, len(accepted), step):
        for j in range(i + 2, len(accepted)):
            travelled = turn[j] - turn[i]
            if travelled > 45:
                break
            if travelled >= 15 and (accepted[i].index, accepted[j].index) not in used:
                chosen.append((accepted[i], accepted[j]))
                break
    measured = []
    for number, (a, b) in enumerate(chosen[:limit]):
        progress("validation", number / max(1, len(chosen)), f"{number}/{len(chosen)}")
        result = _measure(a, b, options, o3d, allow_global=True)
        measured.append((a, b, None if result is None else result[0]))
    return measured


def trajectory_metrics(pairs, poses: dict, o3d) -> dict:
    reg = o3d.pipelines.registration
    fitness, rmse, rotation, translation = [], [], [], []
    missing = 0
    for a, b, measured in pairs:
        if a.index not in poses or b.index not in poses:
            missing += 1
            continue
        relative = np.linalg.inv(poses[b.index]) @ poses[a.index]
        check = reg.evaluate_registration(a.cloud, b.cloud, 0.01, relative)
        fitness.append(check.fitness)
        rmse.append(check.inlier_rmse * 1000)
        if measured is not None:
            error = np.linalg.inv(measured) @ relative
            rotation.append(_angle(error))
            translation.append(float(np.linalg.norm(error[:3, 3])) * 1000)
    if not fitness:
        return {"pairs": 0, "pairs_without_pose": missing}
    result = {"pairs": len(fitness), "pairs_without_pose": missing,
              "overlap_within_1cm_median": round(float(np.median(fitness)), 4),
              "inlier_rmse_mm_median": round(float(np.median(rmse)), 3)}
    if rotation:
        result.update({"pose_error_deg_median": round(float(np.median(rotation)), 3),
                       "pose_error_deg_p90": round(float(np.percentile(rotation, 90)), 3),
                       "pose_error_mm_median": round(float(np.median(translation)), 2),
                       "pose_error_mm_p90": round(float(np.percentile(translation, 90)), 2)})
    return result


def mesh_metrics(mesh, frames, poses: dict, intrinsic, o3d, depths: dict | None = None) -> dict | None:
    """How well a mesh explains the observed subject depth from each frame's pose."""
    if mesh is None or not mesh.has_triangles():
        return None
    render = _renderer(mesh, intrinsic, o3d)
    residuals, coverage = [], []
    for frame in frames:
        if frame.index not in poses or frame.mask is None:
            continue
        observed = (_masked_depth(frame) if depths is None else depths[frame.index]).astype(np.float32) / 1000
        subject = observed > 0
        if subject.sum() < 100:
            continue
        predicted = render(poses[frame.index])
        both = subject & (predicted > 0)
        coverage.append(both.sum() / subject.sum())
        if both.any():
            residuals.append(np.abs(observed - predicted)[both])
    if not residuals:
        return None
    values = np.concatenate(residuals) * 1000
    clusters, counts, _ = mesh.cluster_connected_triangles()
    return {"frames": len(coverage), "depth_residual_mm_median": round(float(np.median(values)), 3),
            "depth_residual_mm_p90": round(float(np.percentile(values, 90)), 2),
            "within_1cm": round(float(np.mean(values < 10)), 4),
            "subject_pixels_explained": round(float(np.mean(coverage)), 4),
            "triangles": len(mesh.triangles), "connected_components": len(counts)}


def turn_coverage(poses, centre) -> float:
    """Fraction of 10-degree sectors around the subject seen at least once."""
    sectors = set()
    for pose in poses:
        offset = pose[:3, 3] - centre
        sectors.add(int((math.degrees(math.atan2(offset[0], -offset[2])) % 360) // 10))
    return round(len(sectors) / 36, 3)


def _texture_frames(accepted, depths: dict, centre, count: int) -> list[TurnFrame]:
    """One frame per sector around the subject, preferring the least non-rigid motion."""
    best: dict[int, TurnFrame] = {}
    sectors = max(4, count)
    for frame in accepted:
        offset = frame.pose[:3, 3] - centre
        sector = int((math.degrees(math.atan2(offset[0], -offset[2])) % 360) // (360 / sectors))
        if sector not in best or frame.nonrigid_fraction < best[sector].nonrigid_fraction:
            best[sector] = frame
    return sorted(best.values(), key=lambda f: f.index)[:count]


def bake(directory: Path, mesh, chosen, depths: dict, intrinsic, mirrored, options: RefineOptions, o3d, obj_path: Path):
    from quality_scan import ScanFrame, _bake_texture

    wanted = {frame.timestamp: frame for frame in chosen}
    group = []
    for timestamp, w, h, bgra, depth, cw, ch, full, mapping in read_frames(directory / "session.khr", with_quality=True):
        frame = wanted.get(timestamp)
        if frame is None:
            continue
        full_rgb = depth_to_color = None
        if full:
            full_rgb = np.frombuffer(full, dtype=np.uint8).reshape(ch, cw, 4)[:, :, [2, 1, 0]].copy()
            depth_to_color = np.frombuffer(mapping, dtype="<f4").reshape(h, w, 2).copy()
            if mirrored:
                depth_to_color = depth_to_color[:, ::-1].copy()
        group.append(ScanFrame(timestamp, frame.rgb, depths[frame.index], None, frame.pose, "refined",
                               full_rgb, depth_to_color))
        if len(group) == len(wanted):
            break
    return _bake_texture(mesh, [group], [intrinsic], obj_path, options.texture_size, len(group), np, o3d)


def _summary(frames) -> dict:
    statuses: dict[str, int] = {}
    for frame in frames:
        statuses[frame.status] = statuses.get(frame.status, 0) + 1
    return statuses


def refine(directory: Path, options: RefineOptions | None = None, texture: bool = True) -> dict:
    import open3d as o3d

    options = options or RefineOptions()
    directory = Path(directory).resolve()
    output = directory / "refined"
    output.mkdir(exist_ok=True)
    progress = Progress(output / "progress.json")
    started = time.time()
    try:
        progress("loading", 0.0)
        manifest, intrinsic, mirrored, frames = load(directory, options, o3d)
        progress("segmenting", 0.0)
        segmentation = segment(frames, intrinsic, options, o3d)
        tracking = track(frames, intrinsic, options, o3d, progress)
        accepted = tracking.pop("accepted")
        if len(accepted) < 3:
            raise ValueError("Menos de tres vistas del sujeto con seguimiento verificado")
        odometry_poses = {f.index: f.pose.copy() for f in accepted}
        graph = optimise(accepted, options, o3d, progress)
        loops_local = [(next(i for i, f in enumerate(accepted) if f.index == a),
                        next(i for i, f in enumerate(accepted) if f.index == b), t) for a, b, t in graph.pop("loops")]
        progress("fusion", 0.0, "primera pasada")
        consensus, _ = keep_main_surface(integrate(accepted, intrinsic, options, o3d), o3d)
        cleaned = nonrigid_masks(accepted, consensus, intrinsic, options, o3d, progress)
        depths = {f.index: d for f, d in zip(accepted, cleaned)}
        progress("fusion", 0.5, "segunda pasada sin movimiento no rígido")
        mesh, fragments = keep_main_surface(integrate(accepted, intrinsic, options, o3d, cleaned), o3d)
        if not mesh.has_triangles():
            raise ValueError("La fusión no produjo superficie")
        if len(mesh.triangles) > options.max_triangles:
            mesh = mesh.simplify_quadric_decimation(options.max_triangles)
        mesh.compute_vertex_normals()
        ply_path = output / "refined.ply"
        if not o3d.io.write_triangle_mesh(str(ply_path), mesh, write_ascii=False):
            raise OSError("No se pudo escribir refined.ply")

        progress("metrics", 0.0)
        refined_poses = {f.index: f.pose for f in accepted}
        native_poses = {f.index: f.native_pose for f in frames if f.native_pose is not None}
        held_out = validation_pairs(accepted, [(accepted[i].index, accepted[j].index, t) for i, j, t in loops_local],
                                    options, o3d, progress)
        sample = accepted[::max(1, len(accepted) // 60)]
        native_mesh_metrics = None
        if (directory / "scan.ply").is_file() and native_poses:
            native_mesh = o3d.io.read_triangle_mesh(str(directory / "scan.ply"))
            native_mesh.remove_duplicated_vertices()
            candidates = [("as_saved", native_mesh)]
            if manifest.get("mesh_coordinate_space") != "camera":
                # Takes saved before 05-11-2026 hold the Fusion mesh mirrored in X.
                from quality_scan import legacy_fusion_to_camera
                candidates.append(("legacy_fusion_corrected", o3d.geometry.TriangleMesh(native_mesh).transform(
                    legacy_fusion_to_camera(intrinsic, np))))
            scored = [(name, mesh_metrics(m, sample, native_poses, intrinsic, o3d)) for name, m in candidates]
            scored = [s for s in scored if s[1] is not None]
            if scored:
                name, best = max(scored, key=lambda s: s[1]["within_1cm"])
                native_mesh_metrics = {**best, "orientation": name}
        centre = mesh.get_axis_aligned_bounding_box().get_center()
        metrics = {
            "held_out_pairs": len(held_out),
            "native": {
                "trajectory": trajectory_metrics(held_out, native_poses, o3d) if native_poses else None,
                "loop_error": loop_errors(accepted, [native_poses.get(f.index) for f in accepted], loops_local)
                if native_poses and all(f.index in native_poses for f in accepted) else None,
                "mesh": native_mesh_metrics,
                "frames_with_pose": len(native_poses),
                "frames_with_pose_but_no_subject": sum(1 for f in frames if f.native_pose is not None and f.status == "subject_absent"),
            },
            "odometry_only": {"trajectory": trajectory_metrics(held_out, odometry_poses, o3d),
                              "loop_error": graph["loop_error_before"]},
            "refined": {
                "trajectory": trajectory_metrics(held_out, refined_poses, o3d),
                "loop_error": graph["loop_error_after"],
                "mesh": mesh_metrics(mesh, sample, refined_poses, intrinsic, o3d),
                "frames_with_pose": len(refined_poses),
                "turn_coverage": turn_coverage([f.pose for f in accepted], centre),
            },
        }
        result = {"format": FORMAT, "source": str(directory), "model": manifest.get("model"),
                  "mode": manifest.get("mode"), "target": manifest.get("target"),
                  "options": {k: (list(v) if isinstance(v, tuple) else v) for k, v in options.__dict__.items()},
                  "frames": len(frames), "frame_status": _summary(frames), **segmentation, **tracking,
                  **{k: v for k, v in graph.items() if not k.startswith("loop_error")},
                  "nonrigid_pixels_removed_median": round(float(np.median([f.nonrigid_fraction for f in accepted])), 4),
                  "fragments_removed": fragments, "ply": str(ply_path), "metrics": metrics,
                  "loop_pairs": [[accepted[i].index, accepted[j].index] for i, j, _ in loops_local],
                  "coordinate_space": "first tracked camera: X right, Y down, Z forward, metres",
                  "nonrigid_model": "robust kernel + per-frame consensus residual masking; no deformation field"}
        if texture:
            progress("texture", 0.0)
            chosen = _texture_frames(accepted, depths, centre, options.texture_frames)
            result.update(bake(directory, mesh, chosen, depths, intrinsic, mirrored, options, o3d, output / "refined.obj"))
        result["poses"] = [{"timestamp_ticks_utc": f.timestamp, "frame": f.index, "status": f.status,
                            "camera_to_world": f.pose.tolist()} for f in accepted]
        result["seconds"] = round(time.time() - started, 1)
        (output / "refine.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        (output / "progress.json").write_text(json.dumps({"state": "finished", "progress": 1.0,
                                                          "seconds": result["seconds"]}), encoding="utf-8")
        return result
    except Exception as error:
        (output / "progress.json").write_text(json.dumps({"state": "error", "detail": str(error)}, ensure_ascii=False),
                                              encoding="utf-8")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", type=Path, help="Carpeta captures/live-* con session.khr y live.scan.json")
    parser.add_argument("--radius", type=float, default=0.5, help="Radio del cilindro del sujeto, metros")
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--no-texture", action="store_true")
    args = parser.parse_args()
    if not 0.2 <= args.radius <= 1.5 or not 1 <= args.stride <= 10:
        parser.error("radius 0,2-1,5 m y stride 1-10")
    result = refine(args.directory, RefineOptions(radius=args.radius, stride=args.stride), not args.no_texture)
    refined = result["metrics"]["refined"]
    print(json.dumps({"tracked": len(result["poses"]), "loop_edges": result["loop_edges"],
                      "refined": refined, "native": result["metrics"]["native"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
