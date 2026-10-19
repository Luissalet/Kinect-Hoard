"""Local, stdio-only MCP access to Kinect Hoard's documented capabilities."""

from __future__ import annotations

import json
import math
import os
from functools import wraps
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
import camera_runtime as runtime
from workspace_catalog import catalog as mode_catalog


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


def _live_request(path: str = "status", action: bool = False) -> dict[str, Any]:
    return runtime.request("scanner", f"api/scan/{path}", action, timeout=.4 if path == "status" else 10)


@mcp.tool()
def start_live_scan(mode: str = "fixed", generation: str = "", subject: str = "person") -> dict[str, Any]:
    """Open the native live scanner. moving: handheld camera; fixed: subject moves before the camera.

    Defaults to 360 for moving and One for fixed. Both modes support person and
    object. Starts in preview; use control_live_scan('start') once positioned.
    """
    return _open_live_scan(mode, generation, subject, window=True)


def _open_live_scan(mode: str, generation: str, subject: str, window: bool) -> dict[str, Any]:
    with runtime.lifecycle():
        return _open_live_scan_locked(mode, generation, subject, window)


def _open_live_scan_locked(mode: str, generation: str, subject: str, window: bool) -> dict[str, Any]:
    if mode not in ("moving", "fixed") or subject not in ("person", "object"):
        raise ValueError("mode: moving/fixed; subject: person/object")
    generation = generation or ("360" if mode == "moving" else "one")
    if generation not in ("one", "360"):
        raise ValueError("generation: one/360")
    try:
        existing = _live_request()
    except OSError:
        existing = None
    if existing is not None:
        if (existing["mode"], existing["model"], existing["target"]) != (mode, generation, subject):
            raise ValueError("Hay otro escáner abierto; finaliza y cierra esa toma antes de cambiar de modo")
        return existing
    runtime.stop("camera")
    return runtime.launch("scanner", lambda port: [sys.executable, str(ROOT / "scanner_worker.py"),
                          mode, generation, subject, "window" if window else "headless", str(port)],
                          "api/scan/status", _exe())


@mcp.tool()
def live_scan_status() -> dict[str, Any]:
    """Read native scanner mode, camera, live tracking, export paths and actual limitations."""
    try:
        return _live_request()
    except urllib.error.URLError:
        return {"state": "closed", "detail": "Escáner cerrado. Ábrelo cuando vayas a utilizarlo."}


@mcp.tool()
def control_live_scan(action: str, x: float = 0, y: float = 0) -> dict[str, Any]:
    """Control start/pause/finish/close, select (normalized image x/y), orbit (radian deltas), or follow.

    finish exports the native mesh and an OBJ/MTL/PNG atlas from original RGB.
    Poll live_scan_status until finished; an accepted command is not a completed export.
    """
    if action not in ("start", "pause", "finish", "select", "orbit", "follow", "close"):
        raise ValueError("Acción de escáner desconocida")
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("Coordenadas no finitas")
    return _live_request(f"{action}?x={x}&y={y}", True)


@mcp.tool()
def open_studio() -> dict[str, Any]:
    """Open the Kinect studio: camera streams, recording, face, audio, gestures and geometry."""
    if live_scan_status()["state"] != "closed":
        raise ValueError("Desconecta el escáner antes de abrir el estudio para liberar la cámara")
    process = subprocess.Popen([str(_exe())], cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW)
    return {"process_id": process.pid, "opened": True}


@mcp.tool()
def list_modes() -> list[dict[str, Any]]:
    """List every studio mode, executable recipe, tools, source and Toolkit sample references."""
    return mode_catalog(_catalog()["capabilities"])


@mcp.tool()
def start_camera(stream: str = "Color", generation: str = "one") -> dict[str, Any]:
    """Start or switch a live camera stream; camera/Blender/OBS share this reader. Never starts on catalogue access."""
    allowed = {"Color", "Depth", "Infrared", "LongExposureInfrared", "BodyIndex", "Skeleton", "BackgroundRemoved", "ColorDepth"}
    if generation not in ("one", "360") or stream not in allowed:
        raise ValueError("Sensor o flujo desconocido")
    if generation == "360" and stream not in {"Color", "Depth", "Infrared", "ColorDepth"}:
        raise ValueError("El backend libfreenect de 360 ofrece RGB, profundidad e IR. El cuerpo usa One.")
    with runtime.lifecycle():
        try:
            current = runtime.request("camera", "api/health", timeout=.3)
            if current.get("service") == "kinect-hoard-camera" and (current["sensor"], current["stream"]) == (generation, stream):
                return current
        except OSError:
            pass
        scan = live_scan_status()
        if scan["state"] not in ("closed", "ready", "connecting", "finished", "error"):
            raise ValueError("Hay un escaneo en curso. Páusalo, finaliza y desconecta antes de cambiar de modo.")
        runtime.stop("scanner")
        runtime.stop("camera")
        return runtime.launch("camera", lambda port: [str(_exe()), "--webserver-model", generation, str(port), stream, "0"], "api/health", _exe(), seconds=12)


@mcp.tool()
def camera_status() -> dict[str, Any]:
    """Read actual reader state, frame count, USB state and last error without opening a sensor."""
    try:
        result = runtime.request("camera", "api/health", timeout=.3)
        return result if result.get("service") == "kinect-hoard-camera" else {"streaming": False, "state": "closed"}
    except OSError:
        return {"streaming": False, "state": "closed"}


@mcp.tool()
def get_live_frame() -> dict[str, Any]:
    """Read live body joints in camera metres, depth pixel mapping, sequence and timestamp. Blender uses this contract."""
    return runtime.request("camera", "api/frame")


@mcp.tool()
def close_camera() -> dict[str, Any]:
    """Release the live stream and its sensor for another application."""
    with runtime.lifecycle():
        return runtime.stop("camera")


@mcp.tool()
def list_artifacts() -> list[dict[str, Any]]:
    """List saved captures, recordings, geometry and scan assets, newest first; never returns pixels."""
    if not CAPTURE_DIR.is_dir():
        return []
    extensions = {".khr", ".json", ".png", ".pgm", ".ply", ".obj", ".mtl", ".wav", ".txt"}
    paths = [p for p in CAPTURE_DIR.rglob("*") if p.is_file() and p.suffix.lower() in extensions]
    return [{"filename": p.relative_to(CAPTURE_DIR).as_posix(), "bytes": p.stat().st_size,
             "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat()} for p in sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)]


@mcp.tool()
def open_demo(demo: str = "interaction") -> dict[str, Any]:
    """Open a working native interaction gallery, sound/beam monitor, dual camera view or avatar, directly in its mode."""
    if demo not in ("interaction", "audio", "dual", "avatar"):
        raise ValueError("demo: interaction/audio/dual/avatar")
    if live_scan_status()["state"] != "closed":
        raise ValueError("Finaliza y desconecta el escáner antes de abrir esta vista")
    close_camera()
    process = subprocess.Popen([str(_exe()), "--demo", demo], cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW)
    return {"opened": True, "demo": demo, "process_id": process.pid}


@mcp.tool()
def replay_session(filename: str) -> dict[str, Any]:
    """Open a recorded KHR without a sensor, with pause/step/PNG/raw/gesture/avatar controls."""
    if Path(filename).name != filename or not filename.endswith(".khr") or not (CAPTURE_DIR / filename).is_file():
        raise ValueError("Indica un archivo KHR existente en captures/")
    process = subprocess.Popen([str(_exe()), "--replay-ui", str(CAPTURE_DIR / filename)], cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW)
    return {"opened": True, "filename": filename, "process_id": process.pid}


@mcp.tool()
def connect_blender(launch: bool = True, hoard_url: str = "http://127.0.0.1:64321") -> dict[str, Any]:
    """Connect One skeleton to a live Blender armature; the Kinect panel can record animation keyframes."""
    current = camera_status()
    stream = current.get("stream") if current.get("sensor") == "one" and current.get("stream") in ("Skeleton", "ColorDepth") else "ColorDepth"
    reader = start_camera(stream, "one")
    script = ROOT / "integrations" / "blender_kinect.py"
    candidates = sorted(Path(os.environ.get("ProgramFiles", r"C:\Program Files")).glob("Blender Foundation/Blender */blender.exe"), reverse=True)
    result = {"reader": reader, "script_path": str(script), "endpoint": hoard_url.rstrip("/") + "/api/camera/frame", "launched": False}
    if launch:
        if not candidates:
            raise FileNotFoundError("No se encontró Blender instalado; descarga el script y ejecútalo desde el editor de Blender")
        runtime.DATA.mkdir(exist_ok=True)
        log = runtime.DATA / "blender.log"
        with log.open("w", encoding="utf-8") as output:
            process = subprocess.Popen([str(candidates[0]), "--python", str(script)], cwd=ROOT,
                                       stdout=output, stderr=subprocess.STDOUT,
                                       env={**os.environ, "KINECT_HOARD_URL": hoard_url}, creationflags=subprocess.CREATE_NO_WINDOW)
        result.update(launched=True, process_id=process.pid, log_path=str(log))
    return result


@mcp.tool()
def sensor_status() -> str:
    """Read current USB and Kinect backend status without starting a camera stream."""
    CAPTURE_DIR.mkdir(exist_ok=True)
    path = CAPTURE_DIR / "diagnose-mcp.txt"
    result = subprocess.run([str(_exe()), "--diagnose", str(path)], timeout=20, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"El diagnóstico terminó con código {result.returncode}")
    return path.read_text(encoding="utf-8")


def _camera_operation(function):
    @wraps(function)
    def run(*args, **kwargs):
        previous = camera_status()
        result = None
        try:
            with runtime.lifecycle():
                if live_scan_status()["state"] != "closed":
                    raise ValueError("Desconecta el escáner antes de esta captura para conservar la toma activa")
                runtime.stop("camera")
                result = function(*args, **kwargs)
        finally:
            if previous.get("streaming"):
                try:
                    start_camera(previous["stream"], previous["sensor"])
                except (OSError, RuntimeError):
                    if isinstance(result, dict):
                        result["preview_note"] = "La captura se guardó; vuelve a conectar la vista previa"
        return result
    return run


@mcp.tool()
@_camera_operation
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
    if generation == "360" and kind not in ("color", "depth", "infrared", "registered_color", "point_cloud", "mesh", "color_cloud", "color_mesh"):
        raise ValueError("La ruta nativa 360 admite RGB, profundidad, IR y geometría con o sin color")
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
@_camera_operation
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
@_camera_operation
def record_audio(seconds: int = 10) -> dict[str, Any]:
    """Attempt Kinect One audio capture; report failure when the runtime produces no samples."""
    if not 1 <= seconds <= 60:
        raise ValueError("seconds debe estar entre 1 y 60")
    CAPTURE_DIR.mkdir(exist_ok=True)
    path = CAPTURE_DIR / f"audio-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.wav"
    result = subprocess.run([str(_exe()), "--audio-record", str(path), str(seconds)], timeout=seconds + 20, capture_output=True)
    metadata_path = path.with_suffix(".json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    if metadata.get("audio_bytes", 0) == 0:
        raise RuntimeError("El runtime no entregó muestras de audio; consulta docs/audio.md y el estado del sensor")
    return {"path": str(path), "metadata_path": str(metadata_path), "bytes": path.stat().st_size,
            "complete": result.returncode == 0, "audio_seconds": metadata.get("audio_seconds"),
            "requested_seconds": seconds}


@mcp.tool()
@_camera_operation
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
@_camera_operation
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
@_camera_operation
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
@_camera_operation
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
@_camera_operation
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
    python = ROOT / ".venv-scan" / "Scripts" / "python.exe"
    if python.is_file() and (ROOT / "fusion.py").is_file():
        return [str(python), str(ROOT / "fusion.py")]
    if bundled.is_file():
        return [str(bundled)]
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
@_camera_operation
def scan_3d(seconds: int = 15, tracking: str = "auto", generation: str = "one",
            foreground_max_depth: float | None = None, roi: list[int] | None = None) -> dict[str, Any]:
    """Record synchronized RGBD from Kinect One or 360 and reconstruct a colored TSDF mesh locally."""
    if not 2 <= seconds <= 60 or tracking not in ("auto", "fixed") or generation not in ("one", "360"):
        raise ValueError("seconds debe estar entre 2 y 60, tracking auto/fixed y generation one/360")
    foreground_options = _foreground_options(foreground_max_depth, roi)
    CAPTURE_DIR.mkdir(exist_ok=True)
    stem = f"fusion-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    session = CAPTURE_DIR / f"{stem}.khr"
    mesh = CAPTURE_DIR / f"{stem}.ply"
    report_path = CAPTURE_DIR / f"{stem}.fusion.json"
    result = subprocess.run([*_scan_command(), str(session), str(mesh),
                             "--capture", str(seconds), "--model", generation, "--tracking", tracking, "--report", str(report_path),
                             *foreground_options],
                            timeout=seconds + 120, capture_output=True)
    if result.returncode != 0 or not report_path.is_file():
        raise RuntimeError(f"Fusion falló (código {result.returncode}): {result.stderr.decode(errors='replace')[-500:]}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {"generation": generation, "session_path": str(session), "mesh_path": str(mesh), "report_path": str(report_path),
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
@_camera_operation
def scan_textured(seconds: int = 15, generation: str = "one", tracking: str = "auto",
                  texture_size: int = 2048, max_triangles: int = 100_000) -> dict[str, Any]:
    """Record One or 360 RGBD and export an OBJ, MTL, PNG atlas, PLY and quality report."""
    if not 2 <= seconds <= 60 or generation not in ("one", "360") or tracking not in ("auto", "fixed"):
        raise ValueError("seconds 2-60, generation one/360 y tracking auto/fixed")
    if texture_size not in (1024, 2048, 4096):
        raise ValueError("texture_size debe ser 1024, 2048 o 4096")
    if not 10_000 <= max_triangles <= 1_000_000:
        raise ValueError("max_triangles debe estar entre 10000 y 1000000")
    CAPTURE_DIR.mkdir(exist_ok=True)
    stem = f"textured-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    session = CAPTURE_DIR / f"{stem}.khr"
    obj = CAPTURE_DIR / f"{stem}.obj"
    report_path = CAPTURE_DIR / f"{stem}.scan.json"
    result = subprocess.run([*_scan_command(), "--quality", str(session), str(obj),
                             "--capture", str(seconds), "--model", generation,
                             "--tracking", tracking, "--texture-size", str(texture_size),
                             "--max-triangles", str(max_triangles),
                             "--report", str(report_path)], timeout=seconds + 600, capture_output=True)
    if result.returncode != 0 or not report_path.is_file():
        raise RuntimeError(f"Escáner falló (código {result.returncode}): {result.stderr.decode(errors='replace')[-700:]}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {"generation": generation, "session_path": str(session), "obj_path": report["obj"],
            "texture_path": report["texture"], "ply_path": report["ply"], "report_path": str(report_path),
            "triangles": report["triangles"], "texture_observed_coverage": report["texture_observed_coverage"]}


@mcp.tool()
@_camera_operation
def scan_dual_textured(extrinsics_filename: str, seconds: int = 15,
                       texture_size: int = 2048, max_triangles: int = 100_000) -> dict[str, Any]:
    """Capture One and 360 concurrently and fuse a textured OBJ using measured extrinsics."""
    if Path(extrinsics_filename).name != extrinsics_filename or not extrinsics_filename.endswith(".json"):
        raise ValueError("Indica el nombre del JSON de calibración en captures/")
    if not 2 <= seconds <= 60 or texture_size not in (1024, 2048, 4096):
        raise ValueError("seconds 2-60 y texture_size 1024/2048/4096")
    if not 10_000 <= max_triangles <= 1_000_000:
        raise ValueError("max_triangles debe estar entre 10000 y 1000000")
    extrinsics = CAPTURE_DIR / extrinsics_filename
    if not extrinsics.is_file():
        raise FileNotFoundError(extrinsics_filename)
    stem = f"dual-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    one = CAPTURE_DIR / f"{stem}-one.khr"
    three_sixty = CAPTURE_DIR / f"{stem}-360.khr"
    obj = CAPTURE_DIR / f"{stem}.obj"
    report_path = CAPTURE_DIR / f"{stem}.scan.json"
    result = subprocess.run([*_scan_command(), "--quality", str(one), str(obj),
                             "--second-session", str(three_sixty), "--extrinsics", str(extrinsics),
                             "--capture-dual", str(seconds), "--tracking", "fixed",
                             "--texture-size", str(texture_size), "--max-triangles", str(max_triangles),
                             "--report", str(report_path)],
                            timeout=seconds + 600, capture_output=True)
    if result.returncode != 0 or not report_path.is_file():
        raise RuntimeError(f"Escaneo dual falló (código {result.returncode}): {result.stderr.decode(errors='replace')[-700:]}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {"one_session_path": str(one), "360_session_path": str(three_sixty),
            "obj_path": report["obj"], "texture_path": report["texture"],
            "ply_path": report["ply"], "report_path": str(report_path),
            "triangles": report["triangles"], "texture_observed_coverage": report["texture_observed_coverage"],
            "capture_start_offset_seconds": report["capture_start_offset_seconds"],
            "capture_overlap_seconds": report["capture_overlap_seconds"]}


@mcp.tool()
def calibrate_dual_landmarks(first_points_metres: list[list[float]],
                             second_points_metres: list[list[float]],
                             threshold_metres: float = 0.02) -> dict[str, Any]:
    """Fit a rigid One <- 360 transform from corresponding measured XYZ landmarks."""
    if len(first_points_metres) != len(second_points_metres) or not 4 <= len(first_points_metres) <= 100:
        raise ValueError("Indica entre 4 y 100 pares de puntos XYZ")
    if any(len(point) != 3 for point in [*first_points_metres, *second_points_metres]):
        raise ValueError("Cada punto debe contener X, Y, Z en metros")
    if not 0.005 <= threshold_metres <= 0.05:
        raise ValueError("threshold_metres debe estar entre 0,005 y 0,05")
    CAPTURE_DIR.mkdir(exist_ok=True)
    stem = f"dual-calibration-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    landmarks = CAPTURE_DIR / f"{stem}-landmarks.json"
    output = CAPTURE_DIR / f"{stem}.json"
    landmarks.write_text(json.dumps({"format": "KINECT_HOARD_DUAL_LANDMARKS_1",
                                     "first_points_metres": first_points_metres,
                                     "second_points_metres": second_points_metres}), encoding="utf-8")
    result = subprocess.run([*_scan_command(), "--calibrate", str(landmarks), str(output),
                             "--threshold", str(threshold_metres)], timeout=30, capture_output=True)
    if result.returncode != 0 or not output.is_file():
        raise RuntimeError(f"Calibración falló: {result.stderr.decode(errors='replace')[-700:]}")
    calibration = json.loads(output.read_text(encoding="utf-8"))
    return {"calibration_filename": output.name, "calibration_path": str(output),
            "landmarks_path": str(landmarks), "rms_error_metres": calibration["rms_error_metres"],
            "inliers": calibration["inliers"], "landmarks": calibration["landmarks"],
            "world_from_second": calibration["world_from_second"]}


@mcp.tool()
def fuse_textured_sessions(first_filename: str, second_filename: str = "",
                           extrinsics_filename: str = "", tracking: str = "auto",
                           texture_size: int = 2048, max_triangles: int = 100_000) -> dict[str, Any]:
    """Texture one or two existing RGBD sessions in captures/; two need measured extrinsics JSON."""
    for filename in (first_filename, second_filename):
        if filename and (Path(filename).name != filename or not filename.endswith(".khr")):
            raise ValueError("Las sesiones deben ser nombres .khr de captures/")
    if not first_filename or tracking not in ("auto", "fixed") or texture_size not in (1024, 2048, 4096):
        raise ValueError("Indica primera sesión, tracking auto/fixed y tamaño de textura válido")
    if bool(second_filename) != bool(extrinsics_filename):
        raise ValueError("Una segunda sesión requiere calibración extrínseca medida")
    if not 10_000 <= max_triangles <= 1_000_000:
        raise ValueError("max_triangles debe estar entre 10000 y 1000000")
    if extrinsics_filename and (Path(extrinsics_filename).name != extrinsics_filename or not extrinsics_filename.endswith(".json")):
        raise ValueError("Indica solo el nombre del JSON de extrínsecos en captures/")
    sessions = [CAPTURE_DIR / first_filename] + ([CAPTURE_DIR / second_filename] if second_filename else [])
    if any(not path.is_file() or not path.with_suffix(".intrinsics.json").is_file() for path in sessions):
        raise FileNotFoundError("Falta una sesión RGBD o sus intrínsecos")
    extrinsics = CAPTURE_DIR / extrinsics_filename if extrinsics_filename else None
    if extrinsics is not None and not extrinsics.is_file():
        raise FileNotFoundError(extrinsics_filename)
    stem = f"textured-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    obj = CAPTURE_DIR / f"{stem}.obj"
    report_path = CAPTURE_DIR / f"{stem}.scan.json"
    command = [*_scan_command(), "--quality", str(sessions[0]), str(obj),
               "--tracking", tracking, "--texture-size", str(texture_size),
               "--max-triangles", str(max_triangles), "--report", str(report_path)]
    if extrinsics is not None:
        command.extend(("--second-session", str(sessions[1]), "--extrinsics", str(extrinsics)))
    result = subprocess.run(command, timeout=600, capture_output=True)
    if result.returncode != 0 or not report_path.is_file():
        raise RuntimeError(f"Escáner falló (código {result.returncode}): {result.stderr.decode(errors='replace')[-700:]}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {"obj_path": report["obj"], "texture_path": report["texture"],
            "ply_path": report["ply"], "report_path": str(report_path),
            "triangles": report["triangles"], "texture_observed_coverage": report["texture_observed_coverage"],
            "sessions": report["sessions"]}


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
