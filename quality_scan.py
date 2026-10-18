"""High quality Kinect RGBD reconstruction with an OBJ texture atlas.

The input is one or two Hoard ColorDepth sessions. A second session requires a
measured camera-to-camera transform; this program never guesses that transform.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from fusion import frames


@dataclass
class ScanFrame:
    timestamp: int
    rgb: object
    depth: object
    rgbd: object
    pose: object
    sensor: str
    full_rgb: object = None
    depth_to_color: object = None


def _intrinsics(path, o3d):
    metadata = json.loads(path.with_suffix(".intrinsics.json").read_text(encoding="utf-8"))
    if metadata.get("format") != "KINECT_HOARD_RGBD_1":
        raise ValueError(f"Calibración RGBD incompatible: {path}")
    data = metadata["intrinsics"]
    width, height = int(data["width"]), int(data["height"])
    fx, fy, cx, cy = (float(data[key]) for key in ("fx", "fy", "cx", "cy"))
    if width < 1 or height < 1 or min(fx, fy) <= 0 or not all(map(math.isfinite, (fx, fy, cx, cy))):
        raise ValueError(f"Intrínsecos inválidos: {path}")
    return o3d.camera.PinholeCameraIntrinsic(width, height, fx, fy, cx, cy), data


def _measured_extrinsics(path, np):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != "KINECT_HOARD_DUAL_EXTRINSICS_1":
        raise ValueError("Formato de extrínsecos incompatible")
    if data.get("test_only"):
        raise ValueError("Esta calibración procede de una prueba sintética y no debe usarse con cámaras físicas")
    pose = np.asarray(data.get("world_from_second"), dtype=np.float64)
    if pose.shape != (4, 4) or not np.isfinite(pose).all():
        raise ValueError("world_from_second debe ser una matriz 4x4 finita")
    if not np.allclose(pose[3], [0, 0, 0, 1], atol=1e-5):
        raise ValueError("Última fila de extrínsecos inválida")
    rotation = pose[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=0.02) or abs(np.linalg.det(rotation) - 1) > 0.02:
        raise ValueError("La rotación de extrínsecos no es rígida")
    if np.linalg.norm(pose[:3, 3]) > 10:
        raise ValueError("La traslación de extrínsecos supera 10 metros")
    if not data.get("calibration_method") or not math.isfinite(float(data.get("rms_error_metres", math.inf))):
        raise ValueError("Indica método y error RMS medido de calibración")
    if not 0 <= float(data["rms_error_metres"]) <= 0.03:
        raise ValueError("El error RMS debe ser medido y no superar 3 cm")
    return pose, data


def _filter_depth(depth, edge_mm, foreground_max_depth, roi, np):
    filtered = depth.copy()
    if foreground_max_depth is not None:
        filtered[filtered > int(foreground_max_depth * 1000)] = 0
    if roi is not None:
        x, y, w, h = roi
        height, width = filtered.shape
        if x < 0 or y < 0 or w < 1 or h < 1 or x + w > width or y + h > height:
            raise ValueError("La ROI queda fuera de la imagen")
        filtered[:y, :] = 0
        filtered[y + h:, :] = 0
        filtered[y:y + h, :x] = 0
        filtered[y:y + h, x + w:] = 0
    if edge_mm > 0:
        base = filtered.copy()
        bad = np.zeros(base.shape, dtype=bool)
        delta_x = np.abs(base[:, 1:].astype(np.int32) - base[:, :-1].astype(np.int32))
        delta_y = np.abs(base[1:, :].astype(np.int32) - base[:-1, :].astype(np.int32))
        sharp_x = (base[:, 1:] > 0) & (base[:, :-1] > 0) & (delta_x > edge_mm)
        sharp_y = (base[1:, :] > 0) & (base[:-1, :] > 0) & (delta_y > edge_mm)
        bad[:, 1:] |= sharp_x
        bad[:, :-1] |= sharp_x
        bad[1:, :] |= sharp_y
        bad[:-1, :] |= sharp_y
        filtered[bad] = 0
    return filtered


def _load_session(path, sensor, tracking, max_frames, depth_limit, edge_mm, roi, np, o3d):
    intrinsic, intrinsics_data = _intrinsics(path, o3d)
    width, height = intrinsic.width, intrinsic.height
    odometry = o3d.pipelines.odometry
    option = odometry.OdometryOption()
    option.depth_max = depth_limit
    option.depth_diff_max = 0.06
    pose_graph = o3d.pipelines.registration.PoseGraph()
    pose_graph.nodes.append(o3d.pipelines.registration.PoseGraphNode(np.eye(4)))
    accepted = []
    seen = lost = 0
    pose = np.eye(4)
    for timestamp, fw, fh, bgra, depth_bytes, color_width, color_height, full_bgra, map_bytes in frames(path, with_quality=True):
        if seen >= max_frames:
            break
        seen += 1
        if (fw, fh) != (width, height):
            raise ValueError(f"Dimensiones de {path} distintas de sus intrínsecos")
        raw = np.frombuffer(depth_bytes, dtype="<u2").reshape(height, width)
        depth = _filter_depth(raw, edge_mm, depth_limit, roi, np)
        if np.count_nonzero(depth) < 1000:
            lost += 1
            continue
        bgra_array = np.frombuffer(bgra, dtype=np.uint8).reshape(height, width, 4)
        rgb = bgra_array[:, :, [2, 1, 0]].copy()
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(rgb), o3d.geometry.Image(depth),
            depth_scale=1000.0, depth_trunc=depth_limit, convert_rgb_to_intensity=False,
        )
        if accepted and tracking == "auto":
            previous = accepted[-1]
            success, motion, information = odometry.compute_rgbd_odometry(
                previous.rgbd, rgbd, intrinsic, np.eye(4),
                odometry.RGBDOdometryJacobianFromHybridTerm(), option,
            )
            distance = float(np.linalg.norm(motion[:3, 3])) if success else math.inf
            angle = math.acos(float(np.clip((np.trace(motion[:3, :3]) - 1) / 2, -1, 1))) if success else math.inf
            if not success or distance > 0.25 or angle > math.radians(25):
                lost += 1
                continue
            pose = pose @ np.linalg.inv(motion)
            old_index = len(accepted) - 1
            pose_graph.edges.append(o3d.pipelines.registration.PoseGraphEdge(
                old_index, old_index + 1, motion, information, uncertain=False,
            ))
        elif accepted:
            old_index = len(accepted) - 1
            pose_graph.edges.append(o3d.pipelines.registration.PoseGraphEdge(
                old_index, old_index + 1, np.eye(4), np.eye(6), uncertain=False,
            ))
        if accepted:
            pose_graph.nodes.append(o3d.pipelines.registration.PoseGraphNode(pose.copy()))
        full_rgb = None
        depth_to_color = None
        if full_bgra:
            full_rgb = np.frombuffer(full_bgra, dtype=np.uint8).reshape(color_height, color_width, 4)[:, :, [2, 1, 0]].copy()
            depth_to_color = np.frombuffer(map_bytes, dtype="<f4").reshape(height, width, 2).copy()
        accepted.append(ScanFrame(timestamp, rgb, depth, rgbd, pose.copy(), sensor, full_rgb, depth_to_color))
    if not accepted:
        raise ValueError(f"Ningún fotograma RGBD válido en {path}")

    loop_edges = 0
    if tracking == "auto" and len(accepted) >= 12:
        # Geometric proximity limits expensive non-adjacent RGBD comparisons.
        for target in range(10, len(accepted), 5):
            for source in range(0, target - 8, 5):
                guess = np.linalg.inv(accepted[target].pose) @ accepted[source].pose
                if np.linalg.norm(guess[:3, 3]) > 0.35:
                    continue
                angle = math.acos(float(np.clip((np.trace(guess[:3, :3]) - 1) / 2, -1, 1)))
                if angle > math.radians(35):
                    continue
                success, motion, info = odometry.compute_rgbd_odometry(
                    accepted[source].rgbd, accepted[target].rgbd, intrinsic, guess,
                    odometry.RGBDOdometryJacobianFromHybridTerm(), option,
                )
                if not success or np.linalg.norm((np.linalg.inv(guess) @ motion)[:3, 3]) > 0.08:
                    continue
                pose_graph.edges.append(o3d.pipelines.registration.PoseGraphEdge(
                    source, target, motion, info, uncertain=True,
                ))
                loop_edges += 1
        if loop_edges:
            reg = o3d.pipelines.registration
            reg.global_optimization(
                pose_graph, reg.GlobalOptimizationLevenbergMarquardt(),
                reg.GlobalOptimizationConvergenceCriteria(),
                reg.GlobalOptimizationOption(max_correspondence_distance=0.07,
                                             edge_prune_threshold=0.25,
                                             preference_loop_closure=0.1, reference_node=0),
            )
            for frame, node in zip(accepted, pose_graph.nodes):
                frame.pose = np.asarray(node.pose).copy()
    return accepted, intrinsic, {
        "session": str(path), "sensor": sensor, "intrinsics_method": intrinsics_data.get("method"),
        "frames_seen": seen, "frames_accepted": len(accepted), "tracking_losses": lost,
        "loop_edges": loop_edges,
    }


def _rasterize_uv(vertices, faces, uv, vertex_colors, width, height, np):
    count = width * height
    positions = np.zeros((count, 3), dtype=np.float32)
    normals = np.zeros((count, 3), dtype=np.float32)
    fallback = np.zeros((count, 3), dtype=np.uint8)
    covered = np.zeros(count, dtype=bool)
    xy = np.column_stack((uv[:, 0] * (width - 1), (1 - uv[:, 1]) * (height - 1)))
    for face in faces:
        triangle = xy[face]
        vertex = vertices[face]
        x0 = max(0, int(np.floor(triangle[:, 0].min())))
        x1 = min(width - 1, int(np.ceil(triangle[:, 0].max())))
        y0 = max(0, int(np.floor(triangle[:, 1].min())))
        y1 = min(height - 1, int(np.ceil(triangle[:, 1].max())))
        if x1 < x0 or y1 < y0:
            continue
        ax, ay = triangle[0]
        bx, by = triangle[1]
        cx, cy = triangle[2]
        denominator = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(denominator) < 1e-8:
            continue
        yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        x = xx + 0.5
        y = yy + 0.5
        a = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / denominator
        b = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / denominator
        c = 1 - a - b
        inside = (a >= -0.001) & (b >= -0.001) & (c >= -0.001)
        if not inside.any():
            continue
        flat = (yy[inside] * width + xx[inside]).astype(np.intp)
        weights = np.column_stack((a[inside], b[inside], c[inside]))
        positions[flat] = weights @ vertex
        normal = np.cross(vertex[1] - vertex[0], vertex[2] - vertex[0])
        length = np.linalg.norm(normal)
        if length > 1e-9:
            normals[flat] = normal / length
        fallback[flat] = np.clip(weights @ vertex_colors[face], 0, 255).astype(np.uint8)
        covered[flat] = True
    return positions, normals, fallback, covered


def _pad_texture(texture, covered, width, height, pixels, np):
    image = texture.reshape(height, width, 3)
    mask = covered.reshape(height, width).copy()
    for _ in range(pixels):
        new_image = image.copy()
        new_mask = mask.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            target_y = slice(max(0, dy), min(height, height + dy))
            target_x = slice(max(0, dx), min(width, width + dx))
            source_y = slice(max(0, -dy), min(height, height - dy))
            source_x = slice(max(0, -dx), min(width, width - dx))
            fill = ~new_mask[target_y, target_x] & mask[source_y, source_x]
            new_image[target_y, target_x][fill] = image[source_y, source_x][fill]
            new_mask[target_y, target_x][fill] = True
        image, mask = new_image, new_mask
    return image


def _bake_texture(mesh, frame_groups, intrinsics, obj_path, texture_size, texture_frames, np, o3d):
    try:
        import xatlas
    except ImportError as error:
        raise RuntimeError("Instala xatlas con setup-scan.ps1 para crear el atlas UV") from error
    vertices = np.asarray(mesh.vertices, dtype=np.float32)
    original_faces = np.asarray(mesh.triangles, dtype=np.uint32)
    colors = np.asarray(mesh.vertex_colors)
    if len(colors) != len(vertices):
        colors = np.full((len(vertices), 3), 0.65)
    atlas = xatlas.Atlas()
    atlas.add_mesh(vertices, original_faces)
    options = xatlas.PackOptions()
    options.resolution = texture_size
    options.padding = 4
    atlas.generate(pack_options=options)
    mapping, faces, uv = atlas[0]
    # xatlas' resolution is a packing hint and can exceed it for dense meshes.
    # UVs remain normalized, so rasterize into the explicit memory-bounded size.
    width = height = texture_size
    new_vertices = vertices[mapping]
    new_colors = (colors[mapping] * 255).astype(np.float32)
    positions, normals, fallback, covered = _rasterize_uv(
        new_vertices, faces, uv, new_colors, width, height, np,
    )
    points_index = np.flatnonzero(covered)
    if len(points_index) == 0:
        raise ValueError("El atlas UV no contiene triángulos rasterizados")
    texture = fallback.copy()
    best_score = np.zeros(len(points_index), dtype=np.float32)
    source_count = 0
    for group, intrinsic in zip(frame_groups, intrinsics):
        chosen = np.unique(np.linspace(0, len(group) - 1, min(len(group), texture_frames), dtype=int))
        fx, fy = intrinsic.get_focal_length()
        cx, cy = intrinsic.get_principal_point()
        for frame_index in chosen:
            frame = group[int(frame_index)]
            source_count += 1
            rotation = frame.pose[:3, :3]
            translation = frame.pose[:3, 3]
            for offset in range(0, len(points_index), 250_000):
                subset = points_index[offset:offset + 250_000]
                xyz = positions[subset]
                camera = (xyz - translation) @ rotation
                z = camera[:, 2]
                forward = z > 0.15
                if not forward.any():
                    continue
                safe_z = np.maximum(z, 1e-6)
                u = fx * camera[:, 0] / safe_z + cx
                v = fy * camera[:, 1] / safe_z + cy
                ix = np.rint(u).astype(np.int32)
                iy = np.rint(v).astype(np.int32)
                in_view = forward & (ix >= 0) & (iy >= 0) & (ix < frame.rgb.shape[1]) & (iy < frame.rgb.shape[0])
                if not in_view.any():
                    continue
                local = np.flatnonzero(in_view)
                ixv, iyv = ix[local], iy[local]
                observed = frame.depth[iyv, ixv].astype(np.float32) / 1000.0
                depth_match = (observed > 0) & (np.abs(observed - z[local]) < np.maximum(0.03, z[local] * 0.015))
                if frame.full_rgb is not None:
                    # Interpolate the depth-to-full-RGB map at subpixel depth
                    # coordinates; nearest-neighbour mapping would throw away
                    # most of the One sensor's 1920x1080 color detail.
                    depth_h, depth_w = frame.depth.shape
                    map_u = np.clip(u[local], 0, depth_w - 1.001)
                    map_v = np.clip(v[local], 0, depth_h - 1.001)
                    map_x0, map_y0 = np.floor(map_u).astype(np.int32), np.floor(map_v).astype(np.int32)
                    mu, mv = (map_u - map_x0)[:, None], (map_v - map_y0)[:, None]
                    coord_map = frame.depth_to_color
                    corners = (coord_map[map_y0, map_x0], coord_map[map_y0, map_x0 + 1],
                               coord_map[map_y0 + 1, map_x0], coord_map[map_y0 + 1, map_x0 + 1])
                    finite_corners = np.logical_and.reduce([np.isfinite(corner).all(axis=1) for corner in corners])
                    mapping = ((1 - mu) * (1 - mv) * np.nan_to_num(corners[0]) +
                               mu * (1 - mv) * np.nan_to_num(corners[1]) +
                               (1 - mu) * mv * np.nan_to_num(corners[2]) +
                               mu * mv * np.nan_to_num(corners[3]))
                    mx, my = mapping[:, 0], mapping[:, 1]
                    valid_map = np.isfinite(mx) & np.isfinite(my) & (mx >= 0) & (my >= 0) & (
                        mx < frame.full_rgb.shape[1] - 1) & (my < frame.full_rgb.shape[0] - 1)
                    valid_map &= finite_corners
                    safe_x = np.clip(np.nan_to_num(mx, nan=0, posinf=0, neginf=0), 0, frame.full_rgb.shape[1] - 2)
                    safe_y = np.clip(np.nan_to_num(my, nan=0, posinf=0, neginf=0), 0, frame.full_rgb.shape[0] - 2)
                    x0, y0 = np.floor(safe_x).astype(np.int32), np.floor(safe_y).astype(np.int32)
                    dx, dy = (safe_x - x0)[:, None], (safe_y - y0)[:, None]
                    source = frame.full_rgb
                    color = ((1 - dx) * (1 - dy) * source[y0, x0] +
                             dx * (1 - dy) * source[y0, x0 + 1] +
                             (1 - dx) * dy * source[y0 + 1, x0] +
                             dx * dy * source[y0 + 1, x0 + 1]).astype(np.uint8)
                    depth_match &= valid_map
                else:
                    color = frame.rgb[iyv, ixv]
                depth_match &= np.any(color != 0, axis=1)
                if not depth_match.any():
                    continue
                local = local[depth_match]
                color = color[depth_match]
                view_vector = translation - xyz[local]
                cosine = np.abs(np.einsum("ij,ij->i", normals[subset[local]], view_vector)) / np.maximum(
                    np.linalg.norm(view_vector, axis=1), 1e-6,
                )
                score = (cosine ** 2 / np.maximum(z[local] ** 2, 0.01)).astype(np.float32)
                best_slice = best_score[offset:offset + len(subset)]
                take = score > best_slice[local]
                if take.any():
                    best_slice[local[take]] = score[take]
                    texture[subset[local[take]]] = color[take]
    coverage = float(np.count_nonzero(best_score) / len(best_score))
    image = _pad_texture(texture, covered, width, height, 4, np)
    texture_path = obj_path.with_name(obj_path.stem + "-albedo.png")
    if not o3d.io.write_image(str(texture_path), o3d.geometry.Image(np.ascontiguousarray(image))):
        raise OSError("No se pudo escribir la textura PNG")
    mtl_path = obj_path.with_suffix(".mtl")
    mtl_path.write_text("newmtl KinectHoard\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nd 1\nillum 1\nmap_Kd "
                        + texture_path.name + "\n", encoding="utf-8")
    with obj_path.open("w", encoding="ascii", newline="\n") as output:
        output.write(f"mtllib {mtl_path.name}\no KinectHoardScan\nusemtl KinectHoard\n")
        for x, y, z in new_vertices:
            output.write(f"v {x:.7f} {y:.7f} {z:.7f}\n")
        for u, v in uv:
            output.write(f"vt {u:.7f} {v:.7f}\n")
        for a, b, c in faces:
            output.write(f"f {a + 1}/{a + 1} {b + 1}/{b + 1} {c + 1}/{c + 1}\n")
    return {"obj": str(obj_path), "texture": str(texture_path), "mtl": str(mtl_path),
            "texture_width": width, "texture_height": height, "texture_source_frames": source_count,
            "texture_observed_coverage": coverage, "uv_triangles": len(faces)}


def scan(sessions: list[Path], output: Path, report_path: Path, tracking: str = "auto",
         extrinsics: Path | None = None, voxel: float = 0.005, texture_size: int = 2048,
         max_frames: int = 120, texture_frames: int = 24, depth_limit: float = 4.0,
         edge_mm: int = 50, roi: tuple[int, int, int, int] | None = None,
         max_triangles: int = 100_000) -> dict:
    import numpy as np
    import open3d as o3d
    if len(sessions) not in (1, 2):
        raise ValueError("Indica una o dos sesiones RGBD")
    if len(sessions) == 2 and extrinsics is None:
        raise ValueError("Dos sesiones requieren --extrinsics con calibración medida")
    if len(sessions) == 1 and extrinsics is not None:
        raise ValueError("--extrinsics solo se usa con dos sesiones")
    if tracking not in ("auto", "fixed") or not 0.002 <= voxel <= 0.02:
        raise ValueError("tracking o voxel fuera del intervalo permitido")
    if texture_size not in (1024, 2048, 4096) or not 1 <= texture_frames <= 60:
        raise ValueError("textura debe medir 1024, 2048 o 4096; texture-frames entre 1 y 60")
    if not 1 <= max_frames <= 1000 or not 0.5 <= depth_limit <= 4.5 or not 0 <= edge_mm <= 200:
        raise ValueError("max-frames, profundidad o filtro de bordes inválidos")
    if not 1000 <= max_triangles <= 1_000_000:
        raise ValueError("max-triangles fuera del intervalo permitido")

    world_from_second = np.eye(4)
    extrinsics_data = None
    if extrinsics is not None:
        world_from_second, extrinsics_data = _measured_extrinsics(extrinsics, np)
    groups = []
    intrinsics = []
    group_reports = []
    for index, session in enumerate(sessions):
        group, intrinsic, details = _load_session(
            session, "first" if index == 0 else "second", tracking, max_frames,
            depth_limit, edge_mm, roi, np, o3d,
        )
        if index == 1:
            for frame in group:
                frame.pose = world_from_second @ frame.pose
        groups.append(group)
        intrinsics.append(intrinsic)
        group_reports.append(details)

    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=voxel, sdf_trunc=voxel * 4,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
    )
    for group, intrinsic in zip(groups, intrinsics):
        for frame in group:
            volume.integrate(frame.rgbd, intrinsic, np.linalg.inv(frame.pose))
    mesh = volume.extract_triangle_mesh()
    if not mesh.has_triangles():
        raise ValueError("La integración no produjo una malla")
    original_triangles = len(mesh.triangles)
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_unreferenced_vertices()
    if len(mesh.triangles) > max_triangles:
        mesh = mesh.simplify_quadric_decimation(max_triangles)
    mesh.compute_vertex_normals()
    output.parent.mkdir(parents=True, exist_ok=True)
    ply_path = output.with_suffix(".ply")
    if not o3d.io.write_triangle_mesh(str(ply_path), mesh, write_ascii=False):
        raise OSError("No se pudo escribir la malla PLY")
    obj_path = output.with_suffix(".obj")
    texture = _bake_texture(mesh, groups, intrinsics, obj_path, texture_size, texture_frames, np, o3d)
    bounds = mesh.get_axis_aligned_bounding_box()
    report = {
        "format": "KINECT_HOARD_QUALITY_SCAN_1", "ply": str(ply_path),
        "tracking": tracking, "voxel_metres": voxel, "depth_limit_metres": depth_limit,
        "depth_edge_threshold_mm": edge_mm, "roi_depth_pixels": list(roi) if roi else None,
        "original_triangles": original_triangles, "triangles": len(mesh.triangles),
        "vertices": len(mesh.vertices), "bounds_min_metres": bounds.min_bound.tolist(),
        "bounds_max_metres": bounds.max_bound.tolist(), "sessions": group_reports,
        "extrinsics": extrinsics_data, "coordinate_space": "first camera: X right, Y down, Z forward, metres",
        "full_resolution_color_frames": sum(frame.full_rgb is not None for group in groups for frame in group),
        "capture_start_offset_seconds": (groups[1][0].timestamp - groups[0][0].timestamp) / 10_000_000
            if len(groups) == 2 else None,
        "capture_overlap_seconds": max(0.0, (min(groups[0][-1].timestamp, groups[1][-1].timestamp)
            - max(groups[0][0].timestamp, groups[1][0].timestamp)) / 10_000_000)
            if len(groups) == 2 else None,
        "poses": [{"sensor": frame.sensor, "timestamp_ticks_utc": frame.timestamp,
                   "camera_to_world": frame.pose.tolist()} for group in groups for frame in group],
        **texture,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, help="Sesión ColorDepth .khr")
    parser.add_argument("output", type=Path, help="Base de salida .obj o .ply")
    parser.add_argument("--second-session", type=Path, help="Segunda sesión RGBD")
    parser.add_argument("--extrinsics", type=Path, help="Calibración JSON medida: primera cámara <- segunda")
    parser.add_argument("--capture", type=int, help="Captura antes segundos de una cámara")
    parser.add_argument("--capture-dual", type=int, help="Captura One y 360 a la vez; requiere segunda sesión y extrínsecos")
    parser.add_argument("--model", choices=("one", "360"), default="one")
    parser.add_argument("--tracking", choices=("auto", "fixed"), default="auto")
    parser.add_argument("--voxel", type=float, default=0.005)
    parser.add_argument("--texture-size", type=int, default=2048)
    parser.add_argument("--texture-frames", type=int, default=24)
    parser.add_argument("--max-frames", type=int, default=120)
    parser.add_argument("--max-triangles", type=int, default=100_000)
    parser.add_argument("--depth-limit", type=float, default=4.0)
    parser.add_argument("--edge-mm", type=int, default=50)
    parser.add_argument("--roi", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.capture is not None and args.capture_dual is not None:
        parser.error("Elige --capture o --capture-dual")
    if args.capture is not None:
        if args.second_session is not None or not 1 <= args.capture <= 120:
            parser.error("--capture admite una cámara y entre 1 y 120 segundos")
        root = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
        exe = root / "KinectHoard.App.exe"
        if not exe.is_file():
            exe = root / "KinectHoard.App" / "bin" / "Release" / "net48" / "KinectHoard.App.exe"
        args.session.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run([str(exe), "--record-quality-model", args.model, str(args.session),
                                    str(args.capture), "ColorDepth"], timeout=args.capture + 30,
                                   capture_output=True)
        if completed.returncode:
            raise RuntimeError(f"La Kinect {args.model} no produjo RGBD (código {completed.returncode})")
    if args.capture_dual is not None:
        if not 1 <= args.capture_dual <= 120 or args.second_session is None or args.extrinsics is None:
            parser.error("--capture-dual requiere 1-120 segundos, --second-session y --extrinsics")
        import numpy as np
        _measured_extrinsics(args.extrinsics, np)
        root = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
        exe = root / "KinectHoard.App.exe"
        if not exe.is_file():
            exe = root / "KinectHoard.App" / "bin" / "Release" / "net48" / "KinectHoard.App.exe"
        args.session.parent.mkdir(parents=True, exist_ok=True)
        args.second_session.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run([str(exe), "--record-dual-quality", str(args.session),
                                    str(args.second_session), str(args.capture_dual), "ColorDepth"],
                                   timeout=args.capture_dual + 45, capture_output=True)
        if completed.returncode:
            raise RuntimeError(f"No se obtuvieron ambas sesiones RGBD (código {completed.returncode})")
    sessions = [args.session] + ([args.second_session] if args.second_session else [])
    result = scan(sessions, args.output, args.report or args.output.with_suffix(".scan.json"),
                  args.tracking, args.extrinsics, args.voxel, args.texture_size,
                  args.max_frames, args.texture_frames, args.depth_limit,
                  args.edge_mm, tuple(args.roi) if args.roi else None, args.max_triangles)
    print(f"Escáner: {result['triangles']} triángulos, textura {result['texture_width']}×"
          f"{result['texture_height']}, cobertura {result['texture_observed_coverage']:.1%} -> {result['obj']}")


if __name__ == "__main__":
    main()
