"""Synthetic person turning in front of a fixed Kinect One, with ground truth.

Writes a ColorDepth session (``session.khr``), its intrinsics and a
``live.scan.json`` journal whose ``foreground_runs`` hold the body mask, so the
native replay and the offline refinement read exactly the same input. The
torso/head pose is known (``ground_truth.json``); the arms swing about the
shoulders, which no rigid transform can explain. Depth carries Kinect-like
noise, millimetre quantisation, flying-pixel dropout and a wall, floor and a
box behind the subject to exercise segmentation.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import struct
from pathlib import Path

import numpy as np
import open3d as o3d

WIDTH, HEIGHT = 512, 424
FX = FY = 366.5698
CX, CY = 250.1807, 210.5814
START_TICKS = 639_300_000_000_000_000


def _rot(axis: str, angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def _pose(rotation: np.ndarray, translation) -> np.ndarray:
    pose = np.eye(4)
    pose[:3, :3] = rotation
    pose[:3, 3] = translation
    return pose


def _ellipsoid(radii, centre, resolution=40) -> o3d.geometry.TriangleMesh:
    mesh = o3d.geometry.TriangleMesh.create_sphere(1.0, resolution)
    vertices = np.asarray(mesh.vertices) * np.asarray(radii) + np.asarray(centre)
    mesh.vertices = o3d.utility.Vector3dVector(vertices)
    return mesh


def _cylinder(radius, length, top, resolution=28) -> o3d.geometry.TriangleMesh:
    # Open3D cylinders run along Z; turn them to hang along +Y (down).
    mesh = o3d.geometry.TriangleMesh.create_cylinder(radius, length, resolution, 4)
    mesh.rotate(_rot("x", math.pi / 2), center=(0, 0, 0))
    mesh.translate(np.asarray(top) + (0, length / 2, 0))
    return mesh


def _paint(mesh: o3d.geometry.TriangleMesh, part: str) -> o3d.geometry.TriangleMesh:
    """Colour in body coordinates so the pattern travels with each part."""
    p = np.asarray(mesh.vertices)
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    if part == "torso":
        # Two-colour shirt with a crest and smooth shading, like a football top.
        red = np.array([0.72, 0.12, 0.22])
        blue = np.array([0.10, 0.16, 0.42])
        colour = np.where((x > 0)[:, None], red, blue)
        crest = ((x - 0.07) ** 2 + (y + 0.05) ** 2 < 0.03 ** 2) & (z > 0)
        colour[crest] = (0.85, 0.75, 0.25)
        stripe = (np.abs(y + 0.18) < 0.015)
        colour[stripe] = (0.90, 0.55, 0.10)
        colour = colour * (0.85 + 0.15 * np.sin(18 * x + 11 * y)[:, None])
    elif part in ("head", "neck", "arm", "nose"):
        colour = np.tile((0.80, 0.60, 0.48), (len(p), 1)) * (0.9 + 0.1 * np.sin(25 * y + 9 * x)[:, None])
        if part == "head":
            hair = (y < -0.40) | (z < -0.02) & (y < -0.30)
            colour[hair] = (0.12, 0.08, 0.06)
            beard = (z > 0.03) & (y > -0.33)
            colour[beard] = (0.18, 0.12, 0.09)
            eyes = (z > 0.06) & (np.abs(y + 0.38) < 0.012) & (np.abs(np.abs(x) - 0.035) < 0.014)
            colour[eyes] = (0.05, 0.05, 0.05)
        if part == "arm":
            sleeve = y < 0.05
            colour[sleeve] = (0.10, 0.16, 0.42)
    elif part == "legs":
        colour = np.tile((0.16, 0.18, 0.24), (len(p), 1)) * (0.9 + 0.1 * np.sin(30 * y)[:, None])
    elif part == "wall":
        colour = np.tile((0.82, 0.83, 0.86), (len(p), 1)) * (0.92 + 0.08 * np.sin(6 * x + 4 * y)[:, None])
    elif part == "floor":
        colour = np.tile((0.55, 0.38, 0.22), (len(p), 1)) * (0.85 + 0.15 * np.sin(14 * x)[:, None])
    else:
        colour = np.tile((0.45, 0.30, 0.18), (len(p), 1))
    mesh.vertex_colors = o3d.utility.Vector3dVector(np.clip(colour, 0, 1))
    return mesh


def body_parts(swing: float):
    """Return rigid parts and swinging arms in body coordinates: X right, Y down, Z out of the chest."""
    rigid = [
        _paint(_ellipsoid((0.19, 0.30, 0.12), (0, 0.10, 0)), "torso"),
        _paint(_cylinder(0.055, 0.12, (0, -0.28, 0)), "neck"),
        _paint(_ellipsoid((0.085, 0.115, 0.10), (0, -0.38, 0.01)), "head"),
        _paint(_ellipsoid((0.018, 0.025, 0.02), (0, -0.37, 0.105), 16), "nose"),
        _paint(_cylinder(0.075, 0.62, (-0.09, 0.36, 0)), "legs"),
        _paint(_cylinder(0.075, 0.62, (0.09, 0.36, 0)), "legs"),
    ]
    arms = []
    for side in (-1, 1):
        joint = np.array([side * 0.235, -0.13, 0.0])
        arm = _paint(_cylinder(0.045, 0.56, joint), "arm")
        # Opposite phase, as in a natural walk-in-place turn.
        arm.rotate(_rot("x", swing * side), center=joint)
        arms.append(arm)
    return rigid, arms


def background() -> o3d.geometry.TriangleMesh:
    """Static room in camera coordinates: wall, floor and a box beside the subject."""
    wall = o3d.geometry.TriangleMesh.create_box(4.0, 3.0, 0.02)
    wall.translate((-2.0, -1.5, 2.6))
    floor = o3d.geometry.TriangleMesh.create_box(4.0, 0.02, 2.4)
    floor.translate((-2.0, 0.93, 0.4))
    box = o3d.geometry.TriangleMesh.create_box(0.45, 0.5, 0.45)
    box.translate((0.55, 0.43, 1.55))
    scene = o3d.geometry.TriangleMesh()
    for mesh, part in ((wall, "wall"), (floor, "floor"), (box, "box")):
        mesh = mesh.subdivide_midpoint(3)
        scene += _paint(mesh, part)
    return scene


def object_pose(t: float, turn_seconds: float, sway: bool = True) -> np.ndarray:
    """Body -> camera transform at time t; the subject faces the camera at t=0."""
    angle = math.pi + 2 * math.pi * t / turn_seconds + 0.12 * math.sin(0.7 * t)
    tilt = math.radians(2.0) * math.sin(0.8 * t) if sway else 0.0
    offset = np.array([0.012 * math.sin(1.3 * t), 0.004 * math.sin(2.1 * t), 0.012 * math.cos(0.9 * t)]) if sway else np.zeros(3)
    return _pose(_rot("y", angle) @ _rot("z", tilt), np.array([0.0, -0.05, 1.25]) + offset)


def render(meshes, body_triangles: int):
    """Ray-cast depth (metres), RGB and body mask through the One intrinsics."""
    combined = o3d.geometry.TriangleMesh()
    for mesh in meshes:
        combined += mesh
    vertices = np.asarray(combined.vertices, dtype=np.float32)
    triangles = np.asarray(combined.triangles, dtype=np.uint32)
    colours = np.asarray(combined.vertex_colors, dtype=np.float32)
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.core.Tensor(vertices), o3d.core.Tensor(triangles))
    u, v = np.meshgrid(np.arange(WIDTH, dtype=np.float32), np.arange(HEIGHT, dtype=np.float32))
    directions = np.stack(((u - CX) / FX, (v - CY) / FY, np.ones_like(u)), axis=-1)
    rays = np.concatenate((np.zeros_like(directions), directions), axis=-1).astype(np.float32)
    hit = scene.cast_rays(o3d.core.Tensor(rays))
    depth = hit["t_hit"].numpy()  # direction has z = 1, so t is the depth
    ids = hit["primitive_ids"].numpy().astype(np.int64)
    uvs = hit["primitive_uvs"].numpy()
    valid = np.isfinite(depth)
    ids[~valid] = 0
    corners = triangles[ids]
    a, b = uvs[..., 0:1], uvs[..., 1:2]
    rgb = (1 - a - b) * colours[corners[..., 0]] + a * colours[corners[..., 1]] + b * colours[corners[..., 2]]
    rgb[~valid] = 0
    depth[~valid] = 0
    body = valid & (ids < body_triangles)
    return depth, rgb, body


def kinect_noise(depth: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Axial noise growing with distance, 1 mm quantisation, edge and random dropout."""
    noisy = depth + rng.normal(0, 1, depth.shape) * (0.0012 + 0.0019 * np.maximum(depth - 0.4, 0) ** 2)
    noisy[depth == 0] = 0
    jump = np.zeros(depth.shape, dtype=bool)
    jump[:, 1:] |= np.abs(depth[:, 1:] - depth[:, :-1]) > 0.04
    jump[1:, :] |= np.abs(depth[1:, :] - depth[:-1, :]) > 0.04
    noisy[jump & (rng.random(depth.shape) < 0.6)] = 0
    noisy[rng.random(depth.shape) < 0.004] = 0
    return np.clip(np.rint(noisy * 1000), 0, 8000).astype(np.uint16)


def _dotnet_string(text: str) -> bytes:
    data = text.encode("utf-8")
    size, prefix = len(data), bytearray()
    while size >= 0x80:
        prefix.append(size & 0x7F | 0x80)
        size >>= 7
    prefix.append(size)
    return bytes(prefix) + data


def _runs(mask: np.ndarray) -> list[int]:
    flat = np.concatenate(([0], mask.ravel().astype(np.int8), [0]))
    edges = np.flatnonzero(np.diff(flat))
    starts, ends = edges[::2], edges[1::2]
    return [int(v) for pair in zip(starts, ends - starts) for v in pair]


def generate(directory: Path, turn_seconds: float = 24.0, fps: float = 10.0, turns: float = 1.12,
             swing_degrees: float = 12.0, sway: bool = True, seed: int = 7) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    room = background()
    count = int(round(turn_seconds * turns * fps))
    first = object_pose(0, turn_seconds, sway)
    poses, truth = [], []
    with gzip.open(directory / "session.khr", "wb", compresslevel=3) as output:
        output.write(_dotnet_string("KINECT_HOARD_SESSION_1"))
        output.write(struct.pack("<iq", 7, START_TICKS))
        for index in range(count):
            t = index / fps
            ticks = START_TICKS + int(round(t * 10_000_000))
            swing = math.radians(swing_degrees) * math.sin(2 * math.pi * t / 2.6)
            rigid, arms = body_parts(swing)
            pose = object_pose(t, turn_seconds, sway)
            body = o3d.geometry.TriangleMesh()
            for part in rigid + arms:
                body += part
            body.transform(pose)
            depth, rgb, mask = render([body, room], len(body.triangles))
            values = kinect_noise(depth, rng)
            mask &= values > 0
            bgra = np.dstack((np.clip(rgb[..., ::-1] * 255 + rng.normal(0, 2, rgb.shape), 0, 255).astype(np.uint8),
                              np.full(values.shape, 255, np.uint8)))
            output.write(b"\x01" + struct.pack("<qiii", ticks, WIDTH, HEIGHT, bgra.size))
            output.write(bgra.tobytes())
            output.write(struct.pack("<i", values.size) + values.astype("<u2").tobytes() + struct.pack("<i", 0))
            camera_to_world = first @ np.linalg.inv(pose)
            # Input journal for --scanner-replay: masks only, no poses.
            poses.append({"timestamp_ticks_utc": ticks, "foreground_runs": _runs(mask)})
            truth.append({"timestamp_ticks_utc": ticks, "camera_to_world": camera_to_world.tolist(),
                          "turn_degrees": math.degrees(2 * math.pi * t / turn_seconds), "arm_swing_degrees": math.degrees(swing)})
    (directory / "session.intrinsics.json").write_text(json.dumps({
        "format": "KINECT_HOARD_RGBD_1", "image_orientation": "camera",
        "intrinsics": {"width": WIDTH, "height": HEIGHT, "fx": FX, "fy": FY, "cx": CX, "cy": CY,
                       "method": "Synthetic Kinect One pinhole"}}), encoding="utf-8")
    (directory / "live.scan.json").write_text(json.dumps({
        "format": "KINECT_HOARD_LIVE_SCAN_1", "model": "one", "mode": "fixed", "target": "person",
        "synthetic_input": True, "poses": poses}), encoding="utf-8")
    rigid, arms = body_parts(0.0)
    rest = o3d.geometry.TriangleMesh()
    for part in rigid:
        rest += part
    rest_arms = o3d.geometry.TriangleMesh()
    for part in arms:
        rest_arms += part
    rest.transform(first)
    rest_arms.transform(first)
    o3d.io.write_triangle_mesh(str(directory / "ground_truth_rigid.ply"), rest)
    o3d.io.write_triangle_mesh(str(directory / "ground_truth_arms.ply"), rest_arms)
    report = {"format": "KINECT_HOARD_SYNTHETIC_TURN_1", "frames": count, "fps": fps,
              "turn_seconds": turn_seconds, "turns": turns, "arm_swing_degrees": swing_degrees,
              "sway": sway, "seed": seed, "poses": truth,
              "coordinate_space": "first camera: X right, Y down, Z forward, metres"}
    (directory / "ground_truth.json").write_text(json.dumps(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--turn-seconds", type=float, default=24.0)
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--turns", type=float, default=1.12)
    parser.add_argument("--swing", type=float, default=12.0, help="Arm swing amplitude in degrees")
    parser.add_argument("--no-sway", action="store_true")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    report = generate(args.directory, args.turn_seconds, args.fps, args.turns, args.swing, not args.no_sway, args.seed)
    print(f"{report['frames']} frames -> {args.directory}")


if __name__ == "__main__":
    main()
