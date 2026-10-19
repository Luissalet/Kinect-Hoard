"""Fuse synchronized Kinect Hoard ColorDepth sessions into a colored TSDF mesh."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import struct
import subprocess
import sys
from pathlib import Path
from typing import BinaryIO, Iterator


COLOR_DEPTH_STREAM = 7


def exact(source: BinaryIO, size: int) -> bytes:
    data = source.read(size)
    if len(data) != size:
        raise ValueError("Sesión truncada")
    return data


def int32(source: BinaryIO) -> int:
    return struct.unpack("<i", exact(source, 4))[0]


def dotnet_string(source: BinaryIO) -> str:
    size = 0
    for shift in range(0, 35, 7):
        byte = exact(source, 1)[0]
        size |= (byte & 0x7F) << shift
        if byte < 128:
            if size > 1024:
                raise ValueError("Cabecera de sesión demasiado larga")
            return exact(source, size).decode("utf-8")
    raise ValueError("Longitud de texto inválida")


def frames(path: Path, with_quality: bool = False) -> Iterator[tuple]:
    with gzip.open(path, "rb") as source:
        version = dotnet_string(source)
        if version not in ("KINECT_HOARD_SESSION_1", "KINECT_HOARD_SESSION_2"):
            raise ValueError("Formato de sesión desconocido")
        quality = version == "KINECT_HOARD_SESSION_2"
        if int32(source) != COLOR_DEPTH_STREAM:
            raise ValueError("Fusion requiere una sesión ColorDepth")
        exact(source, 8)  # UTC start ticks
        while marker := source.read(1):
            if marker != b"\x01":
                raise ValueError("Marcador de fotograma inválido")
            timestamp = struct.unpack("<q", exact(source, 8))[0]
            width, height = int32(source), int32(source)
            if width < 1 or height < 1 or width * height > 1_000_000:
                raise ValueError("Dimensiones de fotograma inválidas")
            pixel_length = int32(source)
            if pixel_length != width * height * 4:
                raise ValueError("Imagen BGRA inválida")
            bgra = exact(source, pixel_length)
            value_count = int32(source)
            if value_count != width * height:
                raise ValueError("Profundidad ausente o incompatible")
            depth = exact(source, value_count * 2)
            if int32(source) != 0:
                raise ValueError("La sesión ColorDepth contiene cuerpos inesperados")
            full_width = full_height = 0
            full_color = mapping = b""
            if quality:
                full_width, full_height = int32(source), int32(source)
                full_length = int32(source)
                if full_length < 0 or full_length > 32_000_000 or (
                    full_length == 0 and (full_width != 0 or full_height != 0) or
                    full_length > 0 and (full_width < 1 or full_height < 1 or full_width * full_height * 4 != full_length)
                ):
                    raise ValueError("RGB original inválido")
                full_color = exact(source, full_length)
                map_count = int32(source)
                if map_count not in (0, width * height) or bool(map_count) != bool(full_length):
                    raise ValueError("Mapa RGB original inválido")
                mapping = exact(source, map_count * 8)
            if with_quality:
                yield timestamp, width, height, bgra, depth, full_width, full_height, full_color, mapping
            else:
                yield timestamp, width, height, bgra, depth


def reconstruction_intrinsics(session: Path) -> tuple[dict, bool]:
    """Normalize SDK-mirrored images to a common optical coordinate system."""
    metadata = json.loads(session.with_suffix(".intrinsics.json").read_text(encoding="utf-8"))
    if metadata.get("format") != "KINECT_HOARD_RGBD_1":
        raise ValueError("Calibración RGBD incompatible")
    parameters = dict(metadata["intrinsics"])
    orientation = metadata.get("image_orientation")
    if orientation is None:
        orientation = "mirrored_x" if parameters.get("method") in (
            "Kinect SDK depth camera intrinsics",
            "Pinhole fit to SDK MapDepthFrameToCameraSpace (distortion omitted)",
        ) else "camera"
    if orientation not in ("camera", "mirrored_x"):
        raise ValueError("Orientación RGBD desconocida")
    mirrored = orientation == "mirrored_x"
    if mirrored:
        parameters["cx"] = int(parameters["width"]) - 1 - float(parameters["cx"])
    return parameters, mirrored


def fuse(session: Path, output: Path, report_path: Path, voxel: float, tracking: str, max_frames: int,
         foreground_max_depth: float | None = None,
         roi: tuple[int, int, int, int] | None = None) -> dict:
    try:
        import numpy as np
        import open3d as o3d
    except ImportError as error:
        raise RuntimeError("Instala el módulo de escaneo con setup-scan.ps1") from error
    if o3d.__version__ != "0.19.0":
        raise RuntimeError("Fusion requiere Open3D 0.19.0; ejecuta setup-scan.ps1")

    parameters, mirrored = reconstruction_intrinsics(session)
    width, height = int(parameters["width"]), int(parameters["height"])
    fx, fy = float(parameters["fx"]), float(parameters["fy"])
    cx, cy = float(parameters["cx"]), float(parameters["cy"])
    if fx <= 0 or fy <= 0 or width < 1 or height < 1:
        raise ValueError("Calibración de profundidad no válida")
    if foreground_max_depth is not None and not 0.5 <= foreground_max_depth <= 4.5:
        raise ValueError("La profundidad máxima de primer plano debe estar entre 0,5 y 4,5 m")
    if roi is not None:
        x, y, crop_width, crop_height = roi
        if x < 0 or y < 0 or crop_width < 1 or crop_height < 1 or x + crop_width > width or y + crop_height > height:
            raise ValueError("La región de interés debe quedar dentro de la imagen de profundidad")
    depth_limit = foreground_max_depth or 4.5
    intrinsic = o3d.camera.PinholeCameraIntrinsic(width, height, fx, fy, cx, cy)
    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=voxel,
        sdf_trunc=voxel * 4,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
    )
    odometry_option = o3d.pipelines.odometry.OdometryOption()
    odometry_option.depth_diff_max = 0.08
    odometry_option.depth_max = depth_limit
    pose = np.eye(4)
    previous = None
    seen = integrated = lost = 0
    poses = []
    for timestamp, frame_width, frame_height, bgra, raw_depth in frames(session):
        if max_frames and seen >= max_frames:
            break
        seen += 1
        if (frame_width, frame_height) != (width, height):
            raise ValueError("Las dimensiones de la sesión difieren de la calibración")
        depth = np.frombuffer(raw_depth, dtype="<u2").reshape(height, width).copy()
        if mirrored:
            depth = depth[:, ::-1].copy()
        if foreground_max_depth is not None:
            depth[depth > int(foreground_max_depth * 1000)] = 0
        if roi is not None:
            x, y, crop_width, crop_height = roi
            depth[:y, :] = 0
            depth[y + crop_height:, :] = 0
            depth[y:y + crop_height, :x] = 0
            depth[y:y + crop_height, x + crop_width:] = 0
        if np.count_nonzero(depth) < 1000:
            lost += 1
            continue
        color = np.frombuffer(bgra, dtype=np.uint8).reshape(height, width, 4)[:, :, :3][:, :, ::-1].copy()
        if mirrored:
            color = color[:, ::-1].copy()
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(color), o3d.geometry.Image(depth),
            depth_scale=1000.0, depth_trunc=depth_limit, convert_rgb_to_intensity=False,
        )
        if previous is not None and tracking == "auto":
            success, motion, _ = o3d.pipelines.odometry.compute_rgbd_odometry(
                previous, rgbd, intrinsic, np.eye(4),
                o3d.pipelines.odometry.RGBDOdometryJacobianFromHybridTerm(), odometry_option,
            )
            translation = float(np.linalg.norm(motion[:3, 3])) if success else math.inf
            angle = math.acos(float(np.clip((np.trace(motion[:3, :3]) - 1) / 2, -1, 1))) if success else math.inf
            if not success or translation > 0.25 or angle > math.radians(25):
                lost += 1
                continue
            pose = pose @ np.linalg.inv(motion)
        volume.integrate(rgbd, intrinsic, np.linalg.inv(pose))
        integrated += 1
        previous = rgbd
        poses.append({
            "timestamp_ticks_utc": timestamp,
            "camera_to_world": pose.tolist(),
        })
    if integrated == 0:
        raise ValueError("Ningún fotograma RGBD válido para integrar")
    mesh = volume.extract_triangle_mesh()
    if len(mesh.vertices) == 0 or len(mesh.triangles) == 0:
        raise ValueError("La integración no produjo una malla")
    mesh.compute_vertex_normals()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_triangle_mesh(str(output), mesh, write_ascii=False):
        raise OSError("No se pudo escribir la malla PLY")
    bounds = mesh.get_axis_aligned_bounding_box()
    report = {
        "format": "KINECT_HOARD_FUSION_1",
        "session": str(session), "mesh": str(output),
        "tracking": tracking, "frames_seen": seen, "frames_integrated": integrated,
        "tracking_losses": lost, "vertices": len(mesh.vertices), "triangles": len(mesh.triangles),
        "voxel_metres": voxel, "coordinate_space": "Open3D first camera: X right, Y down, Z forward, metres",
        "foreground_max_depth_metres": foreground_max_depth,
        "roi_depth_pixels": list(roi) if roi is not None else None,
        "bounds_min_metres": bounds.min_bound.tolist(), "bounds_max_metres": bounds.max_bound.tolist(),
        "intrinsics_method": parameters.get("method"), "horizontal_flip_applied": mirrored, "poses": poses,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--texture-live":
        from quality_scan import texture_live
        print(texture_live(Path(sys.argv[2]))["obj"])
        return
    if "--calibrate" in sys.argv[1:]:
        sys.argv.remove("--calibrate")
        from dual_calibration import main as calibration_main
        calibration_main()
        return
    if "--quality" in sys.argv[1:]:
        sys.argv.remove("--quality")
        from quality_scan import main as quality_main
        quality_main()
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, nargs="?", help="Sesión .khr de ColorDepth")
    parser.add_argument("mesh", type=Path, nargs="?", help="Malla PLY de salida")
    parser.add_argument("--view", type=Path, help="Abre una malla PLY u OBJ con textura en el visor 3D")
    parser.add_argument("--raw-colors", action="store_true", help="Muestra colores originales sin realce de vista previa")
    parser.add_argument("--report", type=Path, help="Informe JSON (por defecto junto a la malla)")
    parser.add_argument("--tracking", choices=("auto", "fixed"), default="auto")
    parser.add_argument("--foreground-max-depth", type=float, metavar="METRES",
                        help="Descarta el fondo más alejado antes de odometría y TSDF")
    parser.add_argument("--roi", type=int, nargs=4, metavar=("X", "Y", "W", "H"),
                        help="Recorta una región en píxeles de profundidad; el resto queda sin medida")
    parser.add_argument("--capture", type=int, help="Graba primero segundos de ColorDepth con la Kinect elegida")
    parser.add_argument("--model", choices=("one", "360"), default="one", help="Modelo de Kinect para --capture")
    parser.add_argument("--voxel", type=float, default=0.01, help="Lado del vóxel en metros")
    parser.add_argument("--max-frames", type=int, default=120)
    args = parser.parse_args()
    if args.view is not None:
        if args.session is not None or args.mesh is not None or not args.view.is_file():
            parser.error("--view requiere únicamente una malla PLY existente")
        import numpy as np
        import open3d as o3d
        mesh = o3d.io.read_triangle_mesh(str(args.view), enable_post_processing=True)
        if not mesh.has_triangles():
            raise ValueError("El archivo PLY no contiene una malla triangular")
        if not mesh.has_vertex_normals():
            mesh.compute_vertex_normals()
        if mesh.has_vertex_colors() and not args.raw_colors:
            colors = np.asarray(mesh.vertex_colors)
            brightness = colors @ np.array([0.2126, 0.7152, 0.0722])
            valid = brightness[brightness > 0.01]
            if len(valid):
                gain = min(16.0, max(1.0, 0.42 / np.percentile(valid, 50)))
                mesh.vertex_colors = o3d.utility.Vector3dVector(np.clip(colors * gain, 0, 1) ** 0.8)
        viewer = o3d.visualization.Visualizer()
        if not viewer.create_window(window_name="Kinect Hoard · " + args.view.name,
                                    width=1100, height=760):
            raise RuntimeError("No se pudo abrir el visor 3D")
        try:
            viewer.add_geometry(mesh)
            options = viewer.get_render_option()
            options.background_color = np.array([0.06, 0.07, 0.09])
            # Untextured meshes (including the HD face model) need lighting to
            # make their surface relief visible; RGB scans retain their colors.
            options.light_on = not (mesh.has_vertex_colors() or mesh.has_textures())
            options.mesh_show_back_face = True
            viewer.run()
        finally:
            viewer.destroy_window()
        return
    if args.session is None or args.mesh is None:
        parser.error("indica la sesión RGBD y la malla de salida")
    if not 0.004 <= args.voxel <= 0.05 or not 1 <= args.max_frames <= 1000:
        parser.error("voxel o max-frames fuera del intervalo permitido")
    if args.capture is not None:
        if not 1 <= args.capture <= 120:
            parser.error("capture debe estar entre 1 y 120 segundos")
        root = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
        exe = root / "KinectHoard.App.exe"
        if not exe.is_file():
            exe = root / "KinectHoard.App" / "bin" / "Release" / "net48" / "KinectHoard.App.exe"
        args.session.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run([str(exe), "--record-model", args.model, str(args.session), str(args.capture), "ColorDepth"],
                                timeout=args.capture + 30, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"La Kinect {args.model} no produjo una sesión RGBD (código {result.returncode})")
    report_path = args.report or args.mesh.with_suffix(".fusion.json")
    result = fuse(args.session, args.mesh, report_path, args.voxel, args.tracking, args.max_frames,
                  args.foreground_max_depth, tuple(args.roi) if args.roi is not None else None)
    print(f"Fusion: {result['frames_integrated']}/{result['frames_seen']} fotogramas, "
          f"{result['vertices']} vértices, {result['triangles']} caras -> {args.mesh}")


if __name__ == "__main__":
    main()
