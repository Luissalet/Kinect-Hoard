"""Local, stdio-only MCP access to Kinect Hoard's documented capabilities."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import MCPServer


ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "docs" / "capabilities.json"
CAPTURE_DIR = ROOT / "captures"
mcp = MCPServer("Kinect Hoard")


def _catalog() -> dict[str, Any]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def _exe() -> Path:
    candidates = (
        ROOT / "KinectHoard.App.exe",
        ROOT / "KinectHoard.App" / "bin" / "Release" / "net48" / "KinectHoard.App.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("KinectHoard.App.exe no está en el paquete; compila con build.ps1")


@mcp.tool()
def list_capabilities(generation: str = "one") -> list[dict[str, Any]]:
    """List documented Kinect capabilities and their real validation status for One or 360."""
    if generation not in ("one", "360"):
        raise ValueError("generation debe ser 'one' o '360'")
    return [
        {"id": item["id"], "title": item["title"], "status": item[generation], "output": item["output"]}
        for item in _catalog()["capabilities"]
    ]


@mcp.tool()
def get_capability(capability_id: str) -> dict[str, Any]:
    """Return status, data contract, source paths and adaptation notes for one capability."""
    item = next((x for x in _catalog()["capabilities"] if x["id"] == capability_id), None)
    if item is None:
        raise ValueError(f"Capacidad desconocida: {capability_id}")
    result = dict(item)
    result["documentation"] = (ROOT / item["docs"]).read_text(encoding="utf-8")
    return result


@mcp.tool()
def read_hoard_source(relative_path: str) -> str:
    """Read an allowlisted Hoard implementation or documentation file, for adapting it to another app."""
    catalog = _catalog()
    allowed = {"README.md", "PRIVACY.md", "THIRD_PARTY_NOTICES.md",
               "mcp_server.py", "faustus-plugin.json", "docs/capabilities.json"}
    allowed.update(f"docs/{path.name}" for path in (ROOT / "docs").glob("*.md"))
    for item in catalog["capabilities"]:
        allowed.update(item["code"])
        allowed.add(item["docs"])
    normalized = relative_path.replace("\\", "/")
    if normalized not in allowed:
        raise ValueError("Ruta fuera del catálogo de código y documentación")
    path = ROOT / normalized
    if not path.is_file():
        raise FileNotFoundError(normalized)
    content = path.read_text(encoding="utf-8")
    if len(content) > 80_000:
        return content[:80_000] + "\n[truncado: consulta el archivo local para más contexto]"
    return content


@mcp.tool()
def sensor_status() -> str:
    """Read current USB and Kinect backend status without starting a camera stream."""
    CAPTURE_DIR.mkdir(exist_ok=True)
    path = CAPTURE_DIR / "diagnose-mcp.txt"
    result = subprocess.run([str(_exe()), "--diagnose", str(path)], timeout=20, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"El diagnóstico terminó con código {result.returncode}")
    return path.read_text(encoding="utf-8")


@mcp.tool()
def capture_artifact(kind: str, generation: str = "one") -> dict[str, Any]:
    """Capture one local artifact. Returns its path only; image or body contents are not sent to the model."""
    options = {
        "color": ("--capture", "Color", ".png"),
        "depth": ("--capture-raw", "Depth", ".pgm"),
        "infrared": ("--capture-raw", "Infrared", ".pgm"),
        "long_infrared": ("--capture-raw", "LongExposureInfrared", ".pgm"),
        "body_index": ("--capture-raw", "BodyIndex", ".pgm"),
        "skeleton_image": ("--capture", "Skeleton", ".png"),
        "background_removed": ("--capture", "BackgroundRemoved", ".png"),
        "registered_color": ("--capture", "ColorDepth", ".png"),
        "bodies": ("--bodies", "", ".json"),
        "point_cloud": ("--point-cloud", "", ".ply"),
        "mesh": ("--mesh", "", ".ply"),
        "color_cloud": ("--color-cloud", "", ".ply"),
        "color_mesh": ("--color-mesh", "", ".ply"),
    }
    if kind not in options:
        raise ValueError("kind debe ser uno de: " + ", ".join(options))
    if generation not in ("one", "360"):
        raise ValueError("generation debe ser 'one' o '360'")
    if generation == "360" and kind not in ("color", "depth", "infrared", "point_cloud", "mesh"):
        raise ValueError("La ruta nativa 360 solo admite color, profundidad, infrarrojos y geometría de profundidad")
    CAPTURE_DIR.mkdir(exist_ok=True)
    command, stream, suffix = options[kind]
    path = CAPTURE_DIR / f"{kind}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}{suffix}"
    if generation == "360":
        command += "-model"
        argv = [str(_exe()), command, generation, str(path)]
    else:
        argv = [str(_exe()), command, str(path)]
    if stream:
        argv.append(stream)
    result = subprocess.run(argv, timeout=35, capture_output=True)
    if result.returncode != 0 or not path.is_file():
        raise RuntimeError(f"La captura falló (código {result.returncode}); comprueba USB y que la cámara no esté ocupada")
    return {"kind": kind, "generation": generation, "path": str(path), "bytes": path.stat().st_size}


@mcp.tool()
def record_session(stream: str = "Depth", seconds: int = 10, generation: str = "one") -> dict[str, Any]:
    """Record up to 60 seconds at 5 fps in a local .khr file for offline debugging."""
    allowed = {"Color", "Depth", "Infrared", "LongExposureInfrared", "BodyIndex", "Skeleton", "BackgroundRemoved", "ColorDepth"}
    if stream not in allowed or not 1 <= seconds <= 60:
        raise ValueError("stream o seconds no válidos")
    if generation not in ("one", "360"):
        raise ValueError("generation debe ser 'one' o '360'")
    if generation == "360" and stream not in ("Color", "Depth", "Infrared"):
        raise ValueError("La ruta nativa 360 solo graba Color, Depth o Infrared")
    CAPTURE_DIR.mkdir(exist_ok=True)
    path = CAPTURE_DIR / f"session-{stream.lower()}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.khr"
    argv = [str(_exe()), "--record", str(path), str(seconds), stream] if generation == "one" else \
        [str(_exe()), "--record-model", generation, str(path), str(seconds), stream]
    result = subprocess.run(argv, timeout=seconds + 20, capture_output=True)
    if result.returncode != 0 or not path.is_file():
        raise RuntimeError(f"La grabación falló (código {result.returncode}); comprueba cámara y USB")
    metadata_path = path.with_suffix(".intrinsics.json")
    return {"path": str(path), "bytes": path.stat().st_size, "stream": stream, "generation": generation, "requested_seconds": seconds,
            "intrinsics_path": str(metadata_path) if metadata_path.is_file() else None}


@mcp.tool()
def record_audio(seconds: int = 10) -> dict[str, Any]:
    """Attempt Kinect One audio capture; report failure when the runtime produces no samples."""
    if not 1 <= seconds <= 60:
        raise ValueError("seconds debe estar entre 1 y 60")
    CAPTURE_DIR.mkdir(exist_ok=True)
    path = CAPTURE_DIR / f"audio-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.wav"
    result = subprocess.run([str(_exe()), "--audio-record", str(path), str(seconds)], timeout=seconds + 20, capture_output=True)
    metadata_path = path.with_suffix(".json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    if result.returncode != 0 or metadata.get("audio_bytes", 0) == 0:
        raise RuntimeError("El runtime no entregó muestras de audio; consulta docs/audio.md y el estado del sensor")
    return {"path": str(path), "metadata_path": str(metadata_path), "bytes": path.stat().st_size}


@mcp.tool()
def recognize_speech(seconds: int = 10) -> dict[str, Any]:
    """Record Kinect One audio locally and return recognized command events plus artifact paths."""
    if not 1 <= seconds <= 60:
        raise ValueError("seconds debe estar entre 1 y 60")
    CAPTURE_DIR.mkdir(exist_ok=True)
    path = CAPTURE_DIR / f"speech-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.wav"
    result = subprocess.run([str(_exe()), "--speech-live", str(path), str(seconds)], timeout=seconds + 35, capture_output=True)
    report_path = path.with_suffix(".speech.json")
    if result.returncode != 0 or not report_path.is_file():
        raise RuntimeError(f"La captura o el reconocimiento de voz falló (código {result.returncode})")
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    return {"audio_path": str(path), "report_path": str(report_path), "culture": report["culture"], "recognized": report["recognized"]}


@mcp.tool()
def analyze_face(generation: str = "one") -> dict[str, Any]:
    """Capture RGB from One or 360 and return frontal face rectangles and local artifact paths."""
    if generation not in ("one", "360"):
        raise ValueError("generation debe ser 'one' o '360'")
    CAPTURE_DIR.mkdir(exist_ok=True)
    prefix = f"face-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    report_path = CAPTURE_DIR / f"{prefix}.json"
    image_path = CAPTURE_DIR / f"{prefix}.png"
    if generation == "one":
        result = subprocess.run([str(_exe()), "--face-capture", str(report_path), str(image_path)], timeout=30, capture_output=True)
    else:
        source_path = CAPTURE_DIR / f"{prefix}-source.png"
        capture = subprocess.run([str(_exe()), "--capture-model", "360", str(source_path), "Color"], timeout=35, capture_output=True)
        if capture.returncode != 0 or not source_path.is_file():
            raise RuntimeError(f"La captura RGB 360 falló (código {capture.returncode})")
        result = subprocess.run([str(_exe()), "--face-image", str(source_path), str(report_path), str(image_path)], timeout=30, capture_output=True)
    if result.returncode != 0 or not report_path.is_file() or not image_path.is_file():
        raise RuntimeError(f"El análisis facial falló (código {result.returncode}); revisa el sensor y el modelo OpenCV")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {"generation": generation, "report_path": str(report_path), "image_path": str(image_path), "width": report["width"], "height": report["height"], "faces": report["faces"]}


@mcp.tool()
def capture_face3d(seconds: int = 15) -> dict[str, Any]:
    """Capture a local Kinect One HD face mesh and report geometry metadata without returning facial data."""
    if not 1 <= seconds <= 60:
        raise ValueError("seconds debe estar entre 1 y 60")
    CAPTURE_DIR.mkdir(exist_ok=True)
    stem = f"face3d-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    report_path = CAPTURE_DIR / f"{stem}.json"
    mesh_path = CAPTURE_DIR / f"{stem}.ply"
    result = subprocess.run([str(_exe()), "--face3d", str(report_path), str(mesh_path), str(seconds)],
                            timeout=seconds + 20, capture_output=True)
    if result.returncode != 0 or not report_path.is_file() or not mesh_path.is_file():
        raise RuntimeError(f"La captura facial HD falló (código {result.returncode}); consulta el sensor y la visibilidad del rostro")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    face = report["face"]
    return {"report_path": str(report_path), "mesh_path": str(mesh_path),
            "frames_with_face": report["frames_with_face"], "alignment_quality": face["AlignmentQuality"],
            "vertices": len(face["VerticesMetres"]) // 3, "triangles": len(face["TriangleIndices"]) // 3}


@mcp.tool()
def scan_head(seconds: int = 90) -> dict[str, Any]:
    """Collect multiple face views to build a personalized local Kinect One HD face model."""
    if not 10 <= seconds <= 120:
        raise ValueError("seconds debe estar entre 10 y 120")
    CAPTURE_DIR.mkdir(exist_ok=True)
    stem = f"headscan-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    report_path = CAPTURE_DIR / f"{stem}.json"
    mesh_path = CAPTURE_DIR / f"{stem}.ply"
    result = subprocess.run([str(_exe()), "--headscan", str(report_path), str(mesh_path), str(seconds)],
                            timeout=seconds + 25, capture_output=True)
    if not report_path.is_file():
        raise RuntimeError(f"No se pudo iniciar el escaneo de cabeza (código {result.returncode})")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    face = report.get("face") or {}
    if result.returncode != 0 or not report.get("personalized_model") or not mesh_path.is_file():
        return {"complete": False, "report_path": str(report_path),
                "collection_status": face.get("ModelCollectionStatus"),
                "capture_status": face.get("ModelCaptureStatus"),
                "frames_with_face": report["frames_with_face"]}
    return {"complete": True, "report_path": str(report_path), "mesh_path": str(mesh_path),
            "frames_with_face": report["frames_with_face"],
            "vertices": len(face["VerticesMetres"]) // 3, "triangles": len(face["TriangleIndices"]) // 3}


@mcp.tool()
def capture_gestures(seconds: int = 10) -> dict[str, Any]:
    """Capture Kinect One skeleton frames and return local gesture events and a JSON report path."""
    if not 1 <= seconds <= 60:
        raise ValueError("seconds debe estar entre 1 y 60")
    CAPTURE_DIR.mkdir(exist_ok=True)
    path = CAPTURE_DIR / f"gestures-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
    result = subprocess.run([str(_exe()), "--gestures-live", str(path), str(seconds)], timeout=seconds + 20, capture_output=True)
    if result.returncode != 0 or not path.is_file():
        raise RuntimeError(f"La captura de gestos falló (código {result.returncode})")
    report = json.loads(path.read_text(encoding="utf-8"))
    return {"report_path": str(path), "frames": report["frames"], "tracked_frames": report["tracked_frames"], "events": report["events"]}


@mcp.tool()
def analyze_gesture_session(filename: str) -> dict[str, Any]:
    """Analyze a Skeleton .khr file in captures/ and return its gesture events."""
    if Path(filename).name != filename or not filename.endswith(".khr"):
        raise ValueError("Indica solo el nombre de un archivo .khr de captures/")
    source = CAPTURE_DIR / filename
    if not source.is_file():
        raise FileNotFoundError(filename)
    output = CAPTURE_DIR / f"gestures-session-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
    result = subprocess.run([str(_exe()), "--gestures-session", str(source), str(output)], timeout=30, capture_output=True)
    if result.returncode != 0 or not output.is_file():
        raise RuntimeError(f"No se pudo analizar la sesión de gestos (código {result.returncode})")
    report = json.loads(output.read_text(encoding="utf-8"))
    return {"report_path": str(output), "frames": report["frames"], "tracked_frames": report["tracked_frames"], "events": report["events"]}


def _scan_command() -> list[str]:
    bundled = ROOT / "KinectHoard.Fusion.exe"
    if bundled.is_file():
        return [str(bundled)]
    python = ROOT / ".venv-scan" / "Scripts" / "python.exe"
    if python.is_file() and (ROOT / "fusion.py").is_file():
        return [str(python), str(ROOT / "fusion.py")]
    raise RuntimeError("Falta Fusion: usa el ZIP completo o ejecuta setup-scan.ps1")


def _foreground_options(max_depth: float | None, roi: list[int] | None) -> list[str]:
    options: list[str] = []
    if max_depth is not None:
        if not 0.5 <= max_depth <= 4.5:
            raise ValueError("foreground_max_depth debe estar entre 0,5 y 4,5 m")
        options.extend(("--foreground-max-depth", str(max_depth)))
    if roi is not None:
        if len(roi) != 4 or any(not isinstance(value, int) or value < 0 for value in roi) or roi[2] == 0 or roi[3] == 0:
            raise ValueError("roi debe ser [x, y, ancho, alto] en píxeles de profundidad")
        options.extend(("--roi", *(str(value) for value in roi)))
    return options


@mcp.tool()
def scan_3d(seconds: int = 15, tracking: str = "auto",
            foreground_max_depth: float | None = None, roi: list[int] | None = None) -> dict[str, Any]:
    """Record Kinect One synchronized RGBD and reconstruct a colored TSDF mesh locally."""
    if not 2 <= seconds <= 60 or tracking not in ("auto", "fixed"):
        raise ValueError("seconds debe estar entre 2 y 60 y tracking debe ser auto o fixed")
    foreground_options = _foreground_options(foreground_max_depth, roi)
    CAPTURE_DIR.mkdir(exist_ok=True)
    stem = f"fusion-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    session = CAPTURE_DIR / f"{stem}.khr"
    mesh = CAPTURE_DIR / f"{stem}.ply"
    report_path = CAPTURE_DIR / f"{stem}.fusion.json"
    result = subprocess.run([*_scan_command(), str(session), str(mesh),
                             "--capture", str(seconds), "--tracking", tracking, "--report", str(report_path),
                             *foreground_options],
                            timeout=seconds + 120, capture_output=True)
    if result.returncode != 0 or not report_path.is_file():
        raise RuntimeError(f"Fusion falló (código {result.returncode}): {result.stderr.decode(errors='replace')[-500:]}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {"session_path": str(session), "mesh_path": str(mesh), "report_path": str(report_path),
            "frames_integrated": report["frames_integrated"], "tracking_losses": report["tracking_losses"],
            "vertices": report["vertices"], "triangles": report["triangles"],
            "foreground_max_depth_metres": report["foreground_max_depth_metres"],
            "roi_depth_pixels": report["roi_depth_pixels"]}


@mcp.tool()
def fuse_session(filename: str, tracking: str = "auto",
                 foreground_max_depth: float | None = None, roi: list[int] | None = None) -> dict[str, Any]:
    """Reconstruct a colored TSDF mesh from a ColorDepth .khr file in captures/."""
    if Path(filename).name != filename or not filename.endswith(".khr") or tracking not in ("auto", "fixed"):
        raise ValueError("Indica el nombre de una sesión .khr en captures/ y tracking auto o fixed")
    foreground_options = _foreground_options(foreground_max_depth, roi)
    session = CAPTURE_DIR / filename
    if not session.is_file() or not session.with_suffix(".intrinsics.json").is_file():
        raise FileNotFoundError("Falta la sesión RGBD o su calibración")
    stem = f"fusion-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    mesh = CAPTURE_DIR / f"{stem}.ply"
    report_path = CAPTURE_DIR / f"{stem}.fusion.json"
    result = subprocess.run([*_scan_command(), str(session), str(mesh),
                             "--tracking", tracking, "--report", str(report_path), *foreground_options],
                            timeout=120, capture_output=True)
    if result.returncode != 0 or not report_path.is_file():
        raise RuntimeError(f"Fusion falló (código {result.returncode}): {result.stderr.decode(errors='replace')[-500:]}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {"mesh_path": str(mesh), "report_path": str(report_path),
            "frames_integrated": report["frames_integrated"], "tracking_losses": report["tracking_losses"],
            "vertices": report["vertices"], "triangles": report["triangles"],
            "foreground_max_depth_metres": report["foreground_max_depth_metres"],
            "roi_depth_pixels": report["roi_depth_pixels"]}


@mcp.tool()
def session_info(filename: str) -> dict[str, Any]:
    """Summarize a locally recorded .khr session without returning any camera pixels."""
    if Path(filename).name != filename or not filename.endswith(".khr"):
        raise ValueError("Indica solo el nombre de un archivo .khr de captures/")
    source = CAPTURE_DIR / filename
    if not source.is_file():
        raise FileNotFoundError(filename)
    output = CAPTURE_DIR / f"session-info-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
    try:
        result = subprocess.run([str(_exe()), "--session-info", str(source), str(output)], timeout=30, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"La sesión no se pudo leer (código {result.returncode})")
        return json.loads(output.read_text(encoding="utf-8"))
    finally:
        output.unlink(missing_ok=True)


@mcp.resource("kinect-hoard://capabilities")
def capabilities_resource() -> str:
    """Machine-readable capability catalog and validation status."""
    return CATALOG.read_text(encoding="utf-8")


@mcp.resource("kinect-hoard://toolkit-map")
def toolkit_map_resource() -> str:
    """Mapping from the original Kinect Developer Toolkit examples to Hoard."""
    return (ROOT / "docs" / "toolkit-map.md").read_text(encoding="utf-8")


if __name__ == "__main__":
    mcp.run()
