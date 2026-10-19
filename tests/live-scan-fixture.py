"""Known rigid motion with a stationary distant background, for native Fusion replay."""
import gzip
import json
from pathlib import Path
import struct

import numpy as np
import open3d as o3d


def make_session(folder: Path, textured: bool = False, unique: bool = False):
    folder.mkdir(parents=True, exist_ok=True)
    width, height = 160, 120
    focal = 160.0
    intrinsic = np.array([[focal, 0, width / 2], [0, focal, height / 2], [0, 0, 1]])
    body = o3d.geometry.TriangleMesh.create_sphere(1.0, 30)
    body.vertices = o3d.utility.Vector3dVector(np.asarray(body.vertices) * [0.23, 0.31, 0.15])
    nose = o3d.geometry.TriangleMesh.create_sphere(.10, 20).translate([.13, -.08, -.12])
    shape = body + nose
    palette = np.random.default_rng(19).integers(20, 240, (32, 32, 32, 3), dtype=np.uint8)
    truth = []
    path = folder / "rigid.khr"
    with gzip.open(path, "wb") as output:
        name = b"KINECT_HOARD_SESSION_1"
        output.write(bytes([len(name)]) + name + struct.pack("<iq", 7, 0))
        for index in range(48):
            angle = np.deg2rad(index * 7.5)
            rotation = shape.get_rotation_matrix_from_xyz([.08 * np.sin(angle), angle, .04 * np.cos(angle)])
            transform = np.eye(4)
            transform[:3, :3] = rotation
            transform[:3, 3] = [.025 * np.sin(angle * 2), .01 * np.sin(angle), 1.20]
            moved = o3d.geometry.TriangleMesh(shape).transform(transform)
            scene = o3d.t.geometry.RaycastingScene()
            scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(moved))
            rays = scene.create_rays_pinhole(intrinsic, np.eye(4), width, height)
            hit = scene.cast_rays(rays)["t_hit"].numpy()
            valid = np.isfinite(hit)
            depth = np.full((height, width), 2700, dtype="<u2")
            depth[valid] = np.rint(hit[valid] * 1000).astype("<u2")
            ray_data = rays.numpy()
            world = ray_data[:, :, :3] + ray_data[:, :, 3:] * np.nan_to_num(hit, posinf=0)[:, :, None]
            local = (world - transform[:3, 3]) @ rotation
            rgb = np.clip((local + [.25, .35, .25]) * [450, 330, 450], 0, 255).astype(np.uint8)
            if textured:
                checker = np.floor((local + .5) * 22).sum(axis=2).astype(np.int32) % 2
                rgb = np.clip(rgb.astype(np.float32) * .35 + checker[:, :, None] * 170, 0, 255).astype(np.uint8)
            if unique:
                grid = np.clip(np.floor((local + .5) * 22).astype(np.int32), 0, 31)
                rgb = palette[grid[:, :, 0], grid[:, :, 1], grid[:, :, 2]]
            bgra = np.empty((height, width, 4), dtype=np.uint8)
            bgra[:, :, :3] = rgb[:, :, ::-1]
            bgra[:, :, 3] = 255
            bgra[~valid, :3] = [24, 35, 48]
            timestamp = 638000000000000000 + index * 333333
            output.write(struct.pack("<bqiii", 1, timestamp, width, height, bgra.nbytes))
            output.write(bgra.tobytes())
            output.write(struct.pack("<i", width * height) + depth.tobytes() + struct.pack("<i", 0))
            truth.append({"timestamp_ticks_utc": timestamp, "object_to_camera": transform.tolist()})
    path.with_suffix(".intrinsics.json").write_text(json.dumps({
        "format": "KINECT_HOARD_RGBD_1", "image_orientation": "camera", "intrinsics": {
            "width": width, "height": height, "fx": focal, "fy": focal,
            "cx": width / 2, "cy": height / 2, "method": "synthetic pinhole",
        }}), encoding="utf-8")
    (folder / "ground-truth.json").write_text(json.dumps(truth), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    import sys
    textured = "--textured" in sys.argv
    unique = "--unique" in sys.argv
    make_session(Path(__file__).resolve().parents[1] / ".cache" / ("live-scan-unique-test" if unique else "live-scan-textured-test" if textured else "live-scan-test"), textured, unique)
