"""Markerless motion capture from webcams or recorded videos, without a Kinect.

One camera: monocular 3D pose (metric pose of the body around the hips, placed
in the scene by solving the root translation against the 2D points). Two to
four cameras: ChArUco or body-point calibration, triangulation, temporal
filter and gap filling. Exports skeleton JSON/CSV, BVH, an animated skinned
GLB and a check video. Runs in .venv-mocap (setup-mocap.ps1); Kinect Hoard's
MCP and web server start it as a background process.

Libraries: OpenCV (Apache-2.0), MediaPipe Pose Landmarker (Apache-2.0),
NumPy/SciPy (BSD), Pillow (HPND).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / ".cache" / "mocap"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
             "pose_landmarker_{0}/float16/latest/pose_landmarker_{0}.task")
VIDEO_EXTENSIONS = (".avi", ".mp4", ".mov", ".mkv", ".webm", ".m4v", ".wmv")
FORMAT = "KINECT_HOARD_MOCAP_1"

LANDMARKS = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right", "left_shoulder", "right_shoulder", "left_elbow",
    "right_elbow", "left_wrist", "right_wrist", "left_pinky", "right_pinky", "left_index", "right_index",
    "left_thumb", "right_thumb", "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle",
    "left_heel", "right_heel", "left_foot_index", "right_foot_index",
]
IDX = {name: i for i, name in enumerate(LANDMARKS)}
# Landmarks every detector must deliver for the body solve; the synthetic markers use exactly these.
CORE = [IDX[n] for n in (
    "nose", "left_ear", "right_ear", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_index", "right_index", "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel", "left_foot_index", "right_foot_index")]
CONNECTIONS = [(a, b) for a, b in (
    ("left_shoulder", "right_shoulder"), ("left_hip", "right_hip"), ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"), ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
    ("left_wrist", "left_index"), ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
    ("right_wrist", "right_index"), ("left_hip", "left_knee"), ("left_knee", "left_ankle"),
    ("left_ankle", "left_heel"), ("left_heel", "left_foot_index"), ("left_ankle", "left_foot_index"),
    ("right_hip", "right_knee"), ("right_knee", "right_ankle"), ("right_ankle", "right_heel"),
    ("right_heel", "right_foot_index"), ("right_ankle", "right_foot_index"), ("nose", "left_ear"),
    ("nose", "right_ear"))]
CONNECTIONS = [(IDX[a], IDX[b]) for a, b in CONNECTIONS]
# Share of stature covered by thigh + shank + hip-to-shoulder + shoulder-to-nose (Winter's segment table).
STATURE_FRACTION = 0.871

BOARD_DEFAULT = {"squares_x": 5, "squares_y": 7, "square_mm": 35.0, "marker_mm": 26.0, "dictionary": "DICT_4X4_50"}


# ---------------------------------------------------------------- progress

class Progress:
    """progress.json beside a job: state, stage, fraction and a short Spanish detail."""

    def __init__(self, folder: Path, name: str = "progress.json"):
        self.path = Path(folder) / name
        self.data = {"state": "running", "stage": "starting", "progress": 0.0}

    def _write(self):
        self.data["updated"] = time.time()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def __call__(self, stage: str, progress: float, detail: str = "", **extra):
        self.data.update(state="running", stage=stage, progress=round(float(progress), 4), detail=detail, **extra)
        self._write()

    def finish(self, **extra):
        self.data.update(state="finished", progress=1.0, **extra)
        self._write()

    def fail(self, detail: str):
        self.data.update(state="error", detail=detail)
        self._write()


def _json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    raise TypeError(type(value))


def write_json(path: Path, data) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1, default=_json_default), encoding="utf-8")


# ---------------------------------------------------------------- videos and cameras

def list_videos(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    videos = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
    return sorted(videos, key=lambda p: p.name)


def video_info(path: Path) -> dict:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"No se puede abrir el vídeo {path.name}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    info = {"width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": float(fps) if 1 <= fps <= 240 else 30.0, "frames": int(capture.get(cv2.CAP_PROP_FRAME_COUNT))}
    capture.release()
    return info


def frame_times(path: Path, count: int, fps: float) -> np.ndarray:
    """Per-frame seconds: the timestamps written while recording, else frame / fps."""
    stamps = path.with_suffix(".timestamps.json")
    if stamps.is_file():
        values = np.asarray(json.loads(stamps.read_text(encoding="utf-8"))["timestamps"], dtype=float)
        if len(values) >= count:
            return values[:count]
        if len(values):
            return np.concatenate([values, values[-1] + np.arange(1, count - len(values) + 1) / fps])
    return np.arange(count, dtype=float) / fps


def read_frames(path: Path):
    capture = cv2.VideoCapture(str(path))
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                return
            yield frame
    finally:
        capture.release()


def _dshow_names() -> list[str]:
    ffmpeg = find_ffmpeg()
    if not ffmpeg or os.name != "nt":
        return []
    try:
        output = subprocess.run([ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stderr
    except (OSError, subprocess.TimeoutExpired):
        return []
    names = []
    for line in output.splitlines():
        if line.rstrip().endswith("(video)") and '"' in line:
            names.append(line.split('"')[1])
    return names


def _open_camera(index: int, width: int = 1280, height: int = 720, fps: int = 30):
    backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
    capture = cv2.VideoCapture(index, backend)
    if not capture.isOpened():
        return None
    capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    capture.set(cv2.CAP_PROP_FPS, fps)
    return capture


# On Windows, webcams are read through ffmpeg's DirectShow input when ffmpeg is installed: on this
# PC OpenCV's DirectShow and Media Foundation backends could hang opening a LifeCam that ffmpeg
# read without trouble. Frames get the system clock as timestamp, shared by every camera.

def _use_ffmpeg() -> bool:
    return os.name == "nt" and bool(find_ffmpeg()) and os.environ.get("KINECT_MOCAP_OPENCV_CAPTURE") != "1"


def _dshow_device(index: int):
    names = _dshow_names()
    if index >= len(names):
        raise RuntimeError(f"No hay cámara {index}; busca de nuevo las cámaras")
    return names[index], names[:index].count(names[index])


def _dshow_modes(name: str, number: int) -> list[tuple[str, int, int, float]]:
    """(kind, width, height, max fps) per mode; kind is 'mjpeg' or a raw pixel format."""
    import re
    output = subprocess.run([find_ffmpeg(), "-hide_banner", "-f", "dshow", "-list_options", "true",
                             "-video_device_number", str(number), "-i", f"video={name}"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stderr
    modes = []
    for line in output.splitlines():
        found = re.search(r"(vcodec|pixel_format)=(\S+)\s+min s=\d+x\d+ fps=[\d.]+ max s=(\d+)x(\d+) fps=([\d.]+)", line)
        if found:
            mode = (found.group(2) if found.group(1) == "vcodec" else "raw:" + found.group(2), int(found.group(3)),
                    int(found.group(4)), float(found.group(5)))
            if mode not in modes:
                modes.append(mode)
    return modes


def _dshow_input(index: int, width: int, height: int, fps: int) -> tuple[list[str], dict]:
    name, number = _dshow_device(index)
    modes = _dshow_modes(name, number)
    def score(mode):
        kind, w, h, f = mode
        return (abs(w * h - width * height), -min(f, fps), kind != "mjpeg")
    if not modes:
        raise RuntimeError(f"La cámara {index} ({name}) no publica modos de vídeo")
    kind, w, h, f = min(modes, key=score)
    rate = min(fps, f)
    args = ["-f", "dshow", "-rtbufsize", "512M", "-use_wallclock_as_timestamps", "1", "-video_device_number",
            str(number), "-video_size", f"{w}x{h}", "-framerate", f"{rate:g}"]
    args += ["-vcodec", "mjpeg"] if kind == "mjpeg" else ["-pixel_format", kind[4:]]
    args += ["-i", f"video={name}"]
    return args, {"name": name, "width": w, "height": h, "fps": rate, "input": kind}


def find_ffprobe() -> str | None:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None
    candidate = Path(ffmpeg).with_name("ffprobe.exe" if ffmpeg.lower().endswith(".exe") else "ffprobe")
    return str(candidate) if candidate.is_file() else shutil.which("ffprobe")


def _packet_times(path: Path) -> np.ndarray:
    output = subprocess.run([find_ffprobe(), "-v", "error", "-select_streams", "v:0", "-show_entries",
                             "packet=pts_time", "-of", "csv=p=0", str(path)], capture_output=True, text=True,
                            timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    values = [float(v) for v in output.split() if v.strip() not in ("", "N/A")]
    return np.sort(np.array(values))


def _snapshot_ffmpeg(index: int, output: Path) -> dict:
    args, mode = _dshow_input(index, 1280, 720, 30)
    run = subprocess.run([find_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", *args, "-vf",
                          "select=gte(n\\,10)", "-frames:v", "1", "-q:v", "3", str(output)],
                         capture_output=True, text=True, timeout=30,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if run.returncode != 0 or not output.is_file():
        raise RuntimeError(f"La cámara {index} no entregó imagen: {run.stderr[-300:]}")
    return {"index": index, "width": mode["width"], "height": mode["height"], "path": str(output)}


def _record_ffmpeg(folder: Path, cameras: list[int], seconds: float, fps: int, width: int, height: int,
                   progress: Progress) -> dict:
    plans = []
    for k, index in enumerate(cameras):
        progress("opening", 0.0, f"Preparando la cámara {index}")
        args, mode = _dshow_input(index, width, height, fps)
        codec = ["-c:v", "copy"] if mode["input"] == "mjpeg" else ["-c:v", "mjpeg", "-q:v", "3"]
        plans.append((index, mode, [find_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", *args, "-t",
                                    f"{seconds:g}", *codec, "-copyts", str(folder / f"cam{k}.mkv")]))
    processes = [subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) for _, _, cmd in plans]
    started = time.perf_counter()
    while any(p.poll() is None for p in processes):
        elapsed = time.perf_counter() - started
        progress("recording", min(elapsed / seconds, 1.0), f"Grabando {min(elapsed, seconds):.0f} de {seconds:.0f} s")
        if elapsed > seconds + 45:
            for p in processes:
                p.kill()
            raise RuntimeError("Una cámara no terminó de grabar; puede estar ocupada por otro programa")
        time.sleep(0.25)
    errors = [p.stderr.read().decode(errors="replace")[-300:] for p in processes if p.returncode != 0]
    if errors:
        raise RuntimeError("La grabación falló: " + " | ".join(errors))
    stamps = [_packet_times(folder / f"cam{k}.mkv") for k in range(len(plans))]
    if any(len(s) < 5 for s in stamps):
        raise RuntimeError("Una cámara no entregó fotogramas durante la grabación")
    origin = min(s[0] for s in stamps)
    result = []
    for k, ((index, mode, _), s) in enumerate(zip(plans, stamps)):
        measured = (len(s) - 1) / (s[-1] - s[0]) if s[-1] > s[0] else 0.0
        write_json(folder / f"cam{k}.timestamps.json", {"camera_index": index, "camera": mode["name"],
                                                        "timestamps": s - origin, "fps_measured": measured,
                                                        "clock": "system clock (ffmpeg wallclock)"})
        result.append({"camera": k, "camera_index": index, "name": mode["name"], "frames": int(len(s)),
                       "width": mode["width"], "height": mode["height"], "fps_measured": round(measured, 2),
                       "start_offset_s": round(float(s[0] - origin), 3), "video": f"cam{k}.mkv"})
    return {"cameras": result, "seconds": seconds, "capture": "ffmpeg dshow"}


def list_cameras(max_index: int = 6) -> list[dict]:
    names = _dshow_names()
    if _use_ffmpeg():
        cameras = []
        for index, name in enumerate(names):
            try:
                modes = _dshow_modes(name, names[:index].count(name))
            except (OSError, subprocess.TimeoutExpired):
                modes = []
            best = max(modes, key=lambda m: (m[1] * m[2] if m[3] >= 15 else 0, m[0] == "mjpeg"), default=None)
            cameras.append({"index": index, "name": name, "width": best[1] if best else None,
                            "height": best[2] if best else None})
        return cameras
    cameras, misses = [], 0
    for index in range(max_index):
        capture = _open_camera(index)
        frame = None
        if capture is not None:
            for _ in range(5):
                ok, frame = capture.read()
                if ok:
                    break
            capture.release()
        if frame is None:
            misses += 1
            if misses >= 2 and index >= len(names):
                break
            continue
        misses = 0
        cameras.append({"index": index, "name": names[index] if index < len(names) else f"Cámara {index}",
                        "width": int(frame.shape[1]), "height": int(frame.shape[0])})
    return cameras


def snapshot(index: int, output: Path) -> dict:
    if _use_ffmpeg():
        return _snapshot_ffmpeg(index, output)
    capture = _open_camera(index)
    if capture is None:
        raise RuntimeError(f"La cámara {index} no se puede abrir; puede estar ocupada")
    frame = None
    try:
        for _ in range(12):  # let exposure settle
            ok, current = capture.read()
            if ok:
                frame = current
    finally:
        capture.release()
    if frame is None:
        raise RuntimeError(f"La cámara {index} no entregó imagen")
    cv2.imwrite(str(output), frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return {"index": index, "width": int(frame.shape[1]), "height": int(frame.shape[0]), "path": str(output)}


def record(folder: Path, cameras: list[int], seconds: float, fps: int, width: int, height: int,
           progress: Progress) -> dict:
    """Record every camera at once with a shared clock; each frame keeps its timestamp for syncing."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("cam*"):
        old.unlink()
    if _use_ffmpeg():
        return _record_ffmpeg(folder, cameras, seconds, fps, width, height, progress)
    captures = []
    try:
        for index in cameras:
            progress("opening", 0.0, f"Abriendo la cámara {index}")
            capture = _open_camera(index, width, height, fps)
            if capture is None:
                raise RuntimeError(f"La cámara {index} no se puede abrir; puede estar ocupada")
            frame = None
            for _ in range(15):
                ok, current = capture.read()
                if ok:
                    frame = current
            if frame is None:
                raise RuntimeError(f"La cámara {index} no entregó imagen")
            captures.append((index, capture, frame.shape[1], frame.shape[0]))
        writers, stamps, errors = [], [[] for _ in captures], []
        for k, (index, capture, w, h) in enumerate(captures):
            writer = cv2.VideoWriter(str(folder / f"cam{k}.avi"), cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
            if not writer.isOpened():
                raise RuntimeError("No se pudo crear el vídeo MJPG")
            writers.append(writer)
        start = time.perf_counter() + 0.3
        stop = start + seconds

        def loop(k: int):
            _, capture, _, _ = captures[k]
            try:
                while time.perf_counter() < start:
                    capture.grab()
                while True:
                    ok, frame = capture.read()
                    now = time.perf_counter()
                    if now >= stop:
                        break
                    if ok:
                        writers[k].write(frame)
                        stamps[k].append(now - start)
            except Exception as exc:  # reported in the job
                errors.append(f"cámara {captures[k][0]}: {exc}")

        threads = [threading.Thread(target=loop, args=(k,), daemon=True) for k in range(len(captures))]
        for thread in threads:
            thread.start()
        while any(t.is_alive() for t in threads):
            elapsed = max(0.0, time.perf_counter() - start)
            progress("recording", min(elapsed / seconds, 1.0), f"Grabando {min(elapsed, seconds):.0f} de {seconds:.0f} s",
                     frames=[len(s) for s in stamps])
            time.sleep(0.25)
        for writer in writers:
            writer.release()
        if errors:
            raise RuntimeError("; ".join(errors))
        result = []
        for k, (index, _, w, h) in enumerate(captures):
            measured = (len(stamps[k]) - 1) / (stamps[k][-1] - stamps[k][0]) if len(stamps[k]) > 1 else 0
            write_json(folder / f"cam{k}.timestamps.json", {"camera_index": index, "timestamps": stamps[k],
                                                            "fps_measured": measured})
            result.append({"camera": k, "camera_index": index, "frames": len(stamps[k]), "width": w, "height": h,
                           "fps_measured": round(measured, 2), "video": f"cam{k}.avi"})
        if any(r["frames"] < 5 for r in result):
            raise RuntimeError("Una cámara no entregó fotogramas durante la grabación")
        return {"cameras": result, "seconds": seconds}
    finally:
        for _, capture, _, _ in captures:
            capture.release()


# ---------------------------------------------------------------- ChArUco board

def _board(spec: dict):
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, spec["dictionary"]))
    return cv2.aruco.CharucoBoard((int(spec["squares_x"]), int(spec["squares_y"])), spec["square_mm"] / 1000.0,
                                  spec["marker_mm"] / 1000.0, dictionary)


def board_spec(**overrides) -> dict:
    spec = dict(BOARD_DEFAULT)
    spec.update({k: v for k, v in overrides.items() if v is not None})
    if not (3 <= spec["squares_x"] <= 12 and 3 <= spec["squares_y"] <= 12):
        raise ValueError("El tablero debe tener entre 3 y 12 cuadros por lado")
    if not 0.4 <= spec["marker_mm"] / spec["square_mm"] <= 0.9:
        raise ValueError("El marcador debe medir entre el 40 % y el 90 % del cuadro")
    return spec


def board_pdf(output: Path, spec: dict) -> dict:
    """A4 PDF at true scale: one board square measures square_mm on paper when printed at 100 %."""
    from PIL import Image, ImageDraw, ImageFont
    board = _board(spec)
    pixels = 400  # per square
    dpi = pixels / spec["square_mm"] * 25.4
    page = (round(210 / 25.4 * dpi), round(297 / 25.4 * dpi))
    size = (spec["squares_x"] * pixels, spec["squares_y"] * pixels)
    margin = round(12 / 25.4 * dpi)
    if size[0] > page[0] - 2 * margin or size[1] > page[1] - 4 * margin:
        raise ValueError("El tablero no cabe en un A4 con ese tamaño de cuadro; reduce square_mm")
    image = board.generateImage(size, marginSize=0, borderBits=1)
    canvas = Image.new("L", page, 255)
    left, top = (page[0] - size[0]) // 2, margin + round(8 / 25.4 * dpi)
    canvas.paste(Image.fromarray(image), (left, top))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default(size=max(18, round(3.2 / 25.4 * dpi)))
    except TypeError:
        font = ImageFont.load_default()
    text = (f"Tablero ChArUco {spec['squares_x']}×{spec['squares_y']} · cuadro {spec['square_mm']:g} mm · "
            f"marcador {spec['marker_mm']:g} mm · {spec['dictionary']}")
    draw.text((left, margin // 2), text, fill=0, font=font)
    note = ("Imprime al 100 % (sin «ajustar a la página») y mide un cuadro con una regla. "
            "Si no mide lo indicado, escribe la medida real al calibrar.")
    draw.text((left, top + size[1] + round(5 / 25.4 * dpi)), note, fill=0, font=font)
    # 50 mm reference ruler
    ruler_y = top + size[1] + round(14 / 25.4 * dpi)
    ruler = round(50 / 25.4 * dpi)
    draw.line([(left, ruler_y), (left + ruler, ruler_y)], fill=0, width=4)
    for k in range(6):
        x = left + round(k * 10 / 25.4 * dpi)
        draw.line([(x, ruler_y - 14), (x, ruler_y + 14)], fill=0, width=3)
    draw.text((left + ruler + 20, ruler_y - 20), "50 mm", fill=0, font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "PDF", resolution=dpi)
    write_json(output.with_suffix(".json"), {"format": "KINECT_HOARD_CHARUCO_1", **spec})
    return {"pdf": str(output), "board": spec, "dpi": round(dpi, 2)}


def _detect_charuco(detector, frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    corners, ids, _, _ = detector.detectBoard(gray)
    if ids is None or len(ids) < 6:
        return None
    return corners.reshape(-1, 2).astype(np.float64), ids.reshape(-1).astype(int)


def _rt_matrix(rvec, tvec) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = cv2.Rodrigues(np.asarray(rvec, dtype=float).reshape(3))[0]
    T[:3, 3] = np.asarray(tvec, dtype=float).reshape(3)
    return T


def calibrate_charuco(videos: list[Path], spec: dict, progress: Progress, max_frames: int = 160) -> dict:
    from scipy.optimize import least_squares
    from scipy.spatial.transform import Rotation
    board = _board(spec)
    detector = cv2.aruco.CharucoDetector(board)
    board_points = board.getChessboardCorners().astype(np.float64)
    cams = []
    for c, video in enumerate(videos):
        info = video_info(video)
        times = frame_times(video, max(info["frames"], 1) + 20000, info["fps"])
        stride = max(1, info["frames"] // max_frames) if info["frames"] > 0 else 1
        detections = {}
        for f, frame in enumerate(read_frames(video)):
            if f % stride:
                continue
            found = _detect_charuco(detector, frame)
            if found is not None:
                t = times[f] if f < len(times) else f / info["fps"]
                detections[f] = (float(t), *found)
            if f % (stride * 10) == 0:
                progress("board", (c + min(f / max(info["frames"], 1), 1)) / (len(videos) + 1),
                         f"Buscando el tablero en la cámara {c + 1}")
        if len(detections) < 5:
            raise RuntimeError(f"La cámara {c + 1} solo vio el tablero en {len(detections)} fotogramas; "
                               "muévelo despacio por toda la imagen y repite")
        size = (info["width"], info["height"])
        def spread(ids):  # corners on more than one board row and column
            p = board_points[ids]
            return len(ids) >= 8 and np.ptp(p[:, 0]) > 0 and np.ptp(p[:, 1]) > 0
        keys = sorted((k for k in detections if spread(detections[k][2])), key=lambda k: -len(detections[k][2]))
        if len(keys) < 4:
            raise RuntimeError(f"La cámara {c + 1} vio el tablero entero muy pocas veces; acércalo o mejora la luz")
        chosen = sorted(keys[:60])
        objs = [board_points[detections[k][2]].astype(np.float32) for k in chosen]
        imgs = [detections[k][1].astype(np.float32) for k in chosen]
        guess = default_intrinsics(size, 65.0)
        rms, K, dist, _, _ = cv2.calibrateCamera(objs, imgs, size, guess, np.zeros(5),
                                                 flags=cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_K3
                                                 | cv2.CALIB_ZERO_TANGENT_DIST)
        poses = {}
        for k, (t, corners, ids) in detections.items():
            if len(ids) < 8:
                continue
            ok, rvec, tvec = cv2.solvePnP(board_points[ids], corners, K, dist, flags=cv2.SOLVEPNP_ITERATIVE)
            if not ok:
                continue
            projected = cv2.projectPoints(board_points[ids], rvec, tvec, K, dist)[0].reshape(-1, 2)
            if np.median(np.linalg.norm(projected - corners, axis=1)) < 3.0:
                poses[k] = (t, _rt_matrix(rvec, tvec), corners, ids)
        cams.append({"video": video.name, "size": size, "K": K, "dist": dist.reshape(-1), "rms": float(rms),
                     "detections": len(detections), "poses": poses, "fps": info["fps"]})
    result_cams = [{"name": f"cam{c}", "video": cam["video"], "size": list(cam["size"]), "K": cam["K"],
                    "dist": cam["dist"], "R": np.eye(3), "t": np.zeros(3), "rms_intrinsics_px": cam["rms"],
                    "board_frames": cam["detections"]} for c, cam in enumerate(cams)]
    report = {"method": "charuco", "board": spec, "cameras": result_cams}
    if len(cams) == 1:
        return report
    progress("extrinsics", len(videos) / (len(videos) + 1), "Calculando la posición de cada cámara")

    def matches(a: dict, b: dict, tolerance: float):
        times_b = np.array([v[0] for v in b.values()])
        keys_b = list(b)
        pairs = []
        for ka, va in a.items():
            if not len(times_b):
                break
            j = int(np.argmin(np.abs(times_b - va[0])))
            if abs(times_b[j] - va[0]) <= tolerance:
                pairs.append((ka, keys_b[j]))
        return pairs

    tolerance = 0.6 / max(cams[0]["fps"], 1)
    initial = [np.eye(4)]
    for c in range(1, len(cams)):
        pairs = matches(cams[0]["poses"], cams[c]["poses"], tolerance)
        if len(pairs) < 3:
            raise RuntimeError(f"La cámara 1 y la cámara {c + 1} vieron el tablero a la vez en {len(pairs)} fotogramas; "
                               "colócalo donde lo vean ambas")
        relatives = [cams[c]["poses"][kc][1] @ np.linalg.inv(cams[0]["poses"][k0][1]) for k0, kc in pairs]
        rotation = Rotation.from_matrix(np.array([r[:3, :3] for r in relatives])).mean().as_matrix()
        T = np.eye(4)
        T[:3, :3] = rotation
        T[:3, 3] = np.median(np.array([r[:3, 3] for r in relatives]), axis=0)
        initial.append(T)
    # Joint refinement: intrinsics and distortion of every camera, extrinsics, and one board pose per instant.
    from scipy.sparse import lil_matrix
    C = len(cams)
    used, multi, single = set(), [], []
    for c in range(C):
        for k, pose in cams[c]["poses"].items():
            if (c, k) in used:
                continue
            used.add((c, k))
            views = {c: (pose[2], pose[3])}
            for d in range(C):
                if d == c:
                    continue
                pair = matches({k: pose}, cams[d]["poses"], tolerance)
                if pair and (d, pair[0][1]) not in used:
                    used.add((d, pair[0][1]))
                    views[d] = cams[d]["poses"][pair[0][1]][2:]
            entry = (np.linalg.inv(initial[c]) @ pose[1], views)
            (multi if len(views) >= 2 else single).append(entry)
    multi = multi[:: max(1, len(multi) // 90)]
    single = single[:: max(1, len(single) // 40)]
    instants = multi + single
    N = len(instants)
    INTR = 6  # fx, fy, cx, cy, k1, k2 (webcams: no tangential term)

    def unpack(x):
        intr = x[:INTR * C].reshape(C, INTR)
        Ks = [np.array([[i[0], 0, i[2]], [0, i[1], i[3]], [0, 0, 1.0]]) for i in intr]
        dists = [np.array([i[4], i[5], 0.0, 0.0, 0.0]) for i in intr]
        k = INTR * C
        extr = [np.eye(4)] + [_rt_matrix(x[k + 6 * i:k + 6 * i + 3], x[k + 6 * i + 3:k + 6 * i + 6]) for i in range(C - 1)]
        k += 6 * (C - 1)
        boards = [_rt_matrix(x[k + 6 * i:k + 6 * i + 3], x[k + 6 * i + 3:k + 6 * i + 6]) for i in range(N)]
        return Ks, dists, extr, boards

    blocks = [(i, c, ids) for i, (_, views) in enumerate(instants) for c, (_, ids) in views.items()]

    def residuals(x):
        Ks, dists, extr, boards = unpack(x)
        out = []
        for i, c, ids in blocks:
            T = extr[c] @ boards[i]
            projected = cv2.projectPoints(board_points[ids], cv2.Rodrigues(T[:3, :3])[0], T[:3, 3], Ks[c], dists[c])[0]
            out.append((projected.reshape(-1, 2) - instants[i][1][c][0]).ravel())
        return np.concatenate(out)

    x0 = []
    for cam in cams:
        K, d = cam["K"], cam["dist"]
        x0 += [K[0, 0], K[1, 1], K[0, 2], K[1, 2], d[0], d[1]]
    for T in initial[1:]:
        x0 += [*cv2.Rodrigues(T[:3, :3])[0].ravel(), *T[:3, 3]]
    for T0, _ in instants:
        x0 += [*cv2.Rodrigues(T0[:3, :3])[0].ravel(), *T0[:3, 3]]
    x0 = np.array(x0, dtype=float)
    rows = sum(2 * len(ids) for _, _, ids in blocks)
    sparsity = lil_matrix((rows, len(x0)), dtype=int)
    row = 0
    for i, c, ids in blocks:
        r = slice(row, row + 2 * len(ids))
        sparsity[r, INTR * c:INTR * (c + 1)] = 1
        if c > 0:
            sparsity[r, INTR * C + 6 * (c - 1):INTR * C + 6 * c] = 1
        b = INTR * C + 6 * (C - 1) + 6 * i
        sparsity[r, b:b + 6] = 1
        row += 2 * len(ids)
    before = float(np.sqrt(np.mean(residuals(x0) ** 2)))
    solution = least_squares(residuals, x0, jac_sparsity=sparsity, loss="soft_l1", f_scale=1.0, x_scale="jac",
                             max_nfev=100)
    Ks, dists, extrinsics, _ = unpack(solution.x)
    rms_after = float(np.sqrt(np.mean(solution.fun ** 2)))
    for c, T in enumerate(extrinsics):
        result_cams[c].update(K=Ks[c], dist=dists[c], R=T[:3, :3], t=T[:3, 3])
    instants = multi
    report.update(joint_frames=len(instants), reprojection_rms_px_before=before, reprojection_rms_px=rms_after)
    return report


def load_calibration(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for cam in data["cameras"]:
        for key in ("K", "dist", "R", "t"):
            cam[key] = np.asarray(cam[key], dtype=float)
    return data


# ---------------------------------------------------------------- 2D pose

def model_path(model: str) -> Path:
    if model not in ("lite", "full", "heavy"):
        raise ValueError("model: lite, full o heavy")
    path = MODEL_DIR / f"pose_landmarker_{model}.task"
    if not path.is_file():
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL.format(model), tmp)
        os.replace(tmp, path)
    return path


def detect_mediapipe(video: Path, model: str, report) -> dict:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    info = video_info(video)
    total = max(info["frames"], 1)
    times = frame_times(video, total + 20000, info["fps"])
    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path(model))), running_mode=vision.RunningMode.VIDEO,
        num_poses=1, min_pose_detection_confidence=0.5, min_pose_presence_confidence=0.5, min_tracking_confidence=0.5)
    points, conf, world, stamps = [], [], [], []
    started = time.perf_counter()
    last_ms = -1
    with vision.PoseLandmarker.create_from_options(options) as landmarker:
        for f, frame in enumerate(read_frames(video)):
            h, w = frame.shape[:2]
            t = float(times[f]) if f < len(times) else f / info["fps"]
            ms = max(int(round(t * 1000)), last_ms + 1)
            last_ms = ms
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            result = landmarker.detect_for_video(image, ms)
            p = np.full((33, 2), np.nan)
            c = np.zeros(33)
            wl = np.full((33, 3), np.nan)
            if result.pose_landmarks:
                for j, landmark in enumerate(result.pose_landmarks[0]):
                    p[j] = (landmark.x * w, landmark.y * h)
                    c[j] = min(getattr(landmark, "visibility", 1.0) or 0.0, getattr(landmark, "presence", 1.0) or 1.0)
                for j, landmark in enumerate(result.pose_world_landmarks[0]):
                    wl[j] = (landmark.x, landmark.y, landmark.z)
            points.append(p)
            conf.append(c)
            world.append(wl)
            stamps.append(t)
            if f % 15 == 0:
                report(min(f / total, 1.0))
    elapsed = time.perf_counter() - started
    return {"points": np.array(points), "conf": np.array(conf), "world": np.array(world), "times": np.array(stamps),
            "size": [info["width"], info["height"]], "fps": info["fps"],
            "ms_per_frame": 1000 * elapsed / max(len(points), 1), "detector": f"mediapipe-{model}"}


def synthetic_colors() -> dict[int, tuple[int, int, int]]:
    """Unique saturated BGR colour per core landmark, for the synthetic test videos."""
    colors = {}
    for k, j in enumerate(CORE):
        hsv = np.uint8([[[int(180 * k / len(CORE)), 255, 255]]])
        colors[j] = tuple(int(v) for v in cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0])
    return colors


def detect_markers(video: Path, report) -> dict:
    """Synthetic-marker detector: each core landmark is a disc of one exact colour (lossless test videos)."""
    info = video_info(video)
    total = max(info["frames"], 1)
    times = frame_times(video, total + 20000, info["fps"])
    colors = synthetic_colors()
    points, conf = [], []
    for f, frame in enumerate(read_frames(video)):
        key = (frame[:, :, 0].astype(np.int32) << 16) | (frame[:, :, 1].astype(np.int32) << 8) | frame[:, :, 2]
        p = np.full((33, 2), np.nan)
        c = np.zeros(33)
        for j, (b, g, r) in colors.items():
            mask = (key == ((b << 16) | (g << 8) | r)).astype(np.uint8)
            if mask.sum() < 4:
                continue
            count, _, stats, centroids = cv2.connectedComponentsWithStats(mask)
            best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            p[j] = centroids[best]
            c[j] = 1.0
        points.append(p)
        conf.append(c)
        if f % 15 == 0:
            report(min(f / total, 1.0))
    n = len(points)
    return {"points": np.array(points), "conf": np.array(conf), "world": np.full((n, 33, 3), np.nan),
            "times": np.asarray(times[:n], dtype=float), "size": [info["width"], info["height"]], "fps": info["fps"],
            "ms_per_frame": None, "detector": "synthetic-markers"}


# ---------------------------------------------------------------- geometry

def default_intrinsics(size, fov_degrees: float) -> np.ndarray:
    w, h = size
    f = (w / 2) / math.tan(math.radians(fov_degrees) / 2)
    return np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], dtype=float)


def normalize_points(points: np.ndarray, K: np.ndarray, dist: np.ndarray) -> np.ndarray:
    shape = points.shape
    flat = points.reshape(-1, 2)
    out = np.full_like(flat, np.nan)
    good = np.isfinite(flat).all(axis=1)
    if good.any():
        out[good] = cv2.undistortPoints(flat[good].reshape(-1, 1, 2).astype(np.float64), K, dist).reshape(-1, 2)
    return out.reshape(shape)


def project(X: np.ndarray, K, dist, R, t) -> np.ndarray:
    shape = X.shape[:-1]
    flat = X.reshape(-1, 3)
    out = np.full((len(flat), 2), np.nan)
    good = np.isfinite(flat).all(axis=1)
    if good.any():
        rvec = cv2.Rodrigues(np.asarray(R, dtype=float))[0]
        out[good] = cv2.projectPoints(flat[good], rvec, np.asarray(t, dtype=float), K, dist)[0].reshape(-1, 2)
    return out.reshape(*shape, 2)


def triangulate(norm: np.ndarray, conf: np.ndarray, Rs, ts, min_conf: float = 0.5, focal=None,
                reject_px: float = 20.0):
    """Weighted DLT for every frame and landmark. norm: (C,F,J,2) normalised image points."""
    C, F, J, _ = norm.shape
    P = np.stack([np.hstack([np.asarray(R), np.asarray(t).reshape(3, 1)]) for R, t in zip(Rs, ts)])  # C,3,4
    weight = np.where((conf >= min_conf) & np.isfinite(norm).all(axis=-1), conf, 0.0)  # C,F,J
    focal = np.ones(C) if focal is None else np.asarray(focal, dtype=float)

    def solve(weight):
        x = np.nan_to_num(norm[..., 0])
        y = np.nan_to_num(norm[..., 1])
        rows1 = x[..., None] * P[:, None, None, 2, :] - P[:, None, None, 0, :]
        rows2 = y[..., None] * P[:, None, None, 2, :] - P[:, None, None, 1, :]
        A = np.concatenate([rows1 * weight[..., None], rows2 * weight[..., None]], axis=0)  # 2C,F,J,4
        A = np.moveaxis(A, 0, 2)  # F,J,2C,4
        _, _, vt = np.linalg.svd(A)
        Xh = vt[..., -1, :]
        with np.errstate(invalid="ignore", divide="ignore"):
            X = Xh[..., :3] / Xh[..., 3:4]
        X[(weight > 0).sum(axis=0) < 2] = np.nan
        return X

    X = solve(weight)
    errors = reprojection_errors(X, norm, Rs, ts, focal)
    if C >= 3:
        worst = np.nanargmax(np.where(weight > 0, np.nan_to_num(errors, nan=-1), -1), axis=0)  # F,J
        worst_err = np.take_along_axis(np.nan_to_num(errors, nan=-1), worst[None], axis=0)[0]
        drop = (worst_err > reject_px) & ((weight > 0).sum(axis=0) >= 3)
        if drop.any():
            weight = weight.copy()
            f_idx, j_idx = np.nonzero(drop)
            weight[worst[f_idx, j_idx], f_idx, j_idx] = 0.0
            X = solve(weight)
            errors = reprojection_errors(X, norm, Rs, ts, focal)
    errors[weight == 0] = np.nan
    return X, errors


def reprojection_errors(X, norm, Rs, ts, focal) -> np.ndarray:
    out = []
    for c, (R, t) in enumerate(zip(Rs, ts)):
        Xc = X @ np.asarray(R).T + np.asarray(t)
        with np.errstate(invalid="ignore", divide="ignore"):
            uv = Xc[..., :2] / Xc[..., 2:3]
        out.append(np.linalg.norm(uv - norm[c], axis=-1) * focal[c])
    return np.array(out)


def mono_root(norm: np.ndarray, conf: np.ndarray, world: np.ndarray, min_conf: float = 0.5) -> np.ndarray:
    """Camera-space joints from metric hip-centred landmarks: solve the root translation per frame (linear)."""
    F = norm.shape[0]
    out = np.full((F, 33, 3), np.nan)
    for f in range(F):
        good = (conf[f] >= min_conf) & np.isfinite(norm[f]).all(axis=1) & np.isfinite(world[f]).all(axis=1)
        if good.sum() < 6:
            continue
        x, y = norm[f, good, 0], norm[f, good, 1]
        X, Y, Z = world[f, good].T
        w = conf[f, good]
        A = np.zeros((2 * len(x), 3))
        b = np.zeros(2 * len(x))
        A[0::2, 0], A[0::2, 2], b[0::2] = 1, -x, x * Z - X
        A[1::2, 1], A[1::2, 2], b[1::2] = 1, -y, y * Z - Y
        sw = np.repeat(np.sqrt(w), 2)
        T = np.linalg.lstsq(A * sw[:, None], b * sw, rcond=None)[0]
        if T[2] > 0.3:
            out[f] = world[f] + T
    return out


def fill_gaps(X: np.ndarray, max_gap: int):
    """Linear fill of interior gaps up to max_gap frames. Returns filled array and number of filled samples."""
    X = X.copy()
    filled = 0
    F = X.shape[0]
    frames = np.arange(F)
    for j in range(X.shape[1]):
        valid = np.isfinite(X[:, j]).all(axis=1)
        if valid.sum() < 2:
            continue
        missing = ~valid
        idx = np.nonzero(missing)[0]
        if not len(idx):
            continue
        groups = np.split(idx, np.nonzero(np.diff(idx) > 1)[0] + 1)
        for group in groups:
            if group[0] == 0 or group[-1] == F - 1 or len(group) > max_gap:
                continue
            for d in range(3):
                X[group, j, d] = np.interp(group, frames[valid], X[valid, j, d])
            filled += len(group)
    return X, filled


def smooth(X: np.ndarray, fps: float, method: str, cutoff_hz: float) -> np.ndarray:
    if method == "none":
        return X.copy()
    from scipy.signal import butter, filtfilt, savgol_filter
    X = X.copy()
    if method == "butterworth":
        cutoff = min(cutoff_hz, 0.45 * fps)
        b, a = butter(4, cutoff / (fps / 2))
        minimum = 3 * max(len(a), len(b)) + 1
    elif method == "savgol":
        window = max(5, int(round(fps * 0.25)) | 1)
        minimum = window + 1
    else:
        raise ValueError("filter: butterworth, savgol o none")
    for j in range(X.shape[1]):
        valid = np.isfinite(X[:, j]).all(axis=1)
        idx = np.nonzero(valid)[0]
        if not len(idx):
            continue
        for segment in np.split(idx, np.nonzero(np.diff(idx) > 1)[0] + 1):
            if len(segment) < minimum:
                continue
            data = X[segment, j]
            if method == "butterworth":
                X[segment, j] = filtfilt(b, a, data, axis=0)
            else:
                X[segment, j] = savgol_filter(data, window, 3, axis=0)
    return X


def _mid(X, a, b):
    return (X[:, IDX[a]] + X[:, IDX[b]]) / 2


def _unit(v):
    with np.errstate(invalid="ignore", divide="ignore"):
        return v / np.linalg.norm(v, axis=-1, keepdims=True)


def align_world(X: np.ndarray):
    """Rotate so the body's up is +Y and its mean facing is +Z (left = +X); floor at Y=0; start at XZ=0."""
    hips, neck = _mid(X, "left_hip", "right_hip"), _mid(X, "left_shoulder", "right_shoulder")
    up = np.nanmedian(_unit(neck - hips), axis=0)
    left = np.nanmedian(_unit(np.concatenate([X[:, IDX["left_hip"]] - X[:, IDX["right_hip"]],
                                              X[:, IDX["left_shoulder"]] - X[:, IDX["right_shoulder"]]])), axis=0)
    if not (np.isfinite(up).all() and np.isfinite(left).all()):
        raise RuntimeError("No hay fotogramas con caderas y hombros para orientar el esqueleto")
    y = up / np.linalg.norm(up)
    x = left - (left @ y) * y
    x /= np.linalg.norm(x)
    z = np.cross(x, y)
    R = np.stack([x, y, z])
    Xw = X @ R.T
    feet = Xw[:, [IDX[n] for n in ("left_ankle", "right_ankle", "left_heel", "right_heel",
                                    "left_foot_index", "right_foot_index")], 1]
    floor = np.nanpercentile(feet, 2) if np.isfinite(feet).any() else np.nanmin(Xw[..., 1])
    hips_w = _mid(Xw, "left_hip", "right_hip")
    first = np.nonzero(np.isfinite(hips_w).all(axis=1))[0][0]
    offset = np.array([hips_w[first, 0], floor, hips_w[first, 2]])
    return Xw - offset, {"rotation": R, "offset": offset}


def segment_sum(X: np.ndarray) -> float:
    """Median thigh + shank + hip-to-shoulder + shoulder-to-nose length (same units as X)."""
    def length(a, b):
        return np.linalg.norm(X[:, IDX[a]] - X[:, IDX[b]], axis=-1)
    thigh = np.nanmedian(np.concatenate([length("left_hip", "left_knee"), length("right_hip", "right_knee")]))
    shank = np.nanmedian(np.concatenate([length("left_knee", "left_ankle"), length("right_knee", "right_ankle")]))
    hips, neck = _mid(X, "left_hip", "right_hip"), _mid(X, "left_shoulder", "right_shoulder")
    torso = np.nanmedian(np.linalg.norm(neck - hips, axis=-1))
    head = np.nanmedian(np.linalg.norm(X[:, IDX["nose"]] - neck, axis=-1))
    return float(thigh + shank + torso + head)


# ---------------------------------------------------------------- calibration from body points

def autocalibrate(points: list[np.ndarray], conf: list[np.ndarray], sizes, fov_degrees: float, height_m: float,
                  intrinsics: list | None, progress=None) -> dict:
    """Calibrate 2-4 cameras from the person's own landmarks: essential matrices, then bundle adjustment."""
    from scipy.optimize import least_squares
    from scipy.sparse import lil_matrix
    C = len(points)
    Ks = [np.asarray(intrinsics[c]["K"]) if intrinsics and intrinsics[c] else default_intrinsics(sizes[c], fov_degrees)
          for c in range(C)]
    dists = [np.asarray(intrinsics[c]["dist"]) if intrinsics and intrinsics[c] else np.zeros(5) for c in range(C)]
    known = bool(intrinsics) and all(intrinsics)
    norm = np.stack([normalize_points(points[c], Ks[c], dists[c]) for c in range(C)])
    cf = np.stack(conf)
    good = (cf >= 0.6) & np.isfinite(norm).all(axis=-1)
    Rs, ts = [np.eye(3)], [np.zeros(3)]
    for c in range(1, C):
        mask = good[0] & good[c]
        if mask.sum() < 40:
            raise RuntimeError(f"La cámara 1 y la cámara {c + 1} ven a la persona a la vez en muy pocos puntos "
                               f"({int(mask.sum())}); grábala moviéndose donde la vean todas")
        p0, pc = norm[0][mask], norm[c][mask]
        f_mean = (Ks[0][0, 0] + Ks[c][0, 0]) / 2
        E, inliers = cv2.findEssentialMat(p0, pc, np.eye(3), method=cv2.RANSAC, prob=0.999, threshold=3.0 / f_mean)
        if E is None:
            raise RuntimeError("No se pudo estimar la geometría entre cámaras con los puntos del cuerpo")
        E = E[:3]
        _, R, t, _ = cv2.recoverPose(E, p0, pc, np.eye(3), mask=inliers)
        Rs.append(R)
        ts.append(t.reshape(3))
    # Put every pair on the scale of pair (0, 1) through the depths of camera 0's points.
    if C > 2:
        depth01 = triangulate(norm[[0, 1]], cf[[0, 1]], Rs[:2], ts[:2], min_conf=0.6)[0][..., 2]
        for c in range(2, C):
            depth0c = triangulate(norm[[0, c]], cf[[0, c]], [Rs[0], Rs[c]], [ts[0], ts[c]], min_conf=0.6)[0][..., 2]
            ratio = depth01 / depth0c
            ratio = ratio[np.isfinite(ratio) & (ratio > 0)]
            if len(ratio):
                ts[c] = ts[c] * np.median(ratio)
    if progress:
        progress("autocalibration", 0.5, "Ajuste conjunto de cámaras y puntos del cuerpo")
    # Bundle adjustment on a subsample of frames.
    F = norm.shape[1]
    frames = np.arange(F)[:: max(1, F // 150)]
    X0, _ = triangulate(norm[:, frames], cf[:, frames], Rs, ts, min_conf=0.6)
    obs = []  # (cam, point index, normalised xy, weight)
    point_ids = {}
    for fi, f in enumerate(frames):
        for j in range(33):
            if not np.isfinite(X0[fi, j]).all():
                continue
            views = [c for c in range(C) if good[c, f, j]]
            if len(views) < 2:
                continue
            pid = point_ids.setdefault((fi, j), len(point_ids))
            for c in views:
                obs.append((c, pid, norm[c, f, j], cf[c, f, j]))
    P = len(point_ids)
    points0 = np.zeros((P, 3))
    for (fi, j), pid in point_ids.items():
        points0[pid] = X0[fi, j]
    cam_idx = np.array([o[0] for o in obs])
    pt_idx = np.array([o[1] for o in obs])
    xy = np.array([o[2] for o in obs])
    w = np.sqrt(np.array([o[3] for o in obs]))
    n_cam = C - 1
    free_focal = False  # two-view body points do not constrain focal length; it comes from the FOV or a board
    base_f = np.array([K[0, 0] for K in Ks])
    t1_norm = float(np.linalg.norm(ts[1]))

    def unpack(x):
        Rm = [np.eye(3)] + [cv2.Rodrigues(x[6 * i:6 * i + 3])[0] for i in range(n_cam)]
        tm = [np.zeros(3)] + [x[6 * i + 3:6 * i + 6] for i in range(n_cam)]
        k = 6 * n_cam
        scale = np.exp(x[k:k + C]) if free_focal else np.ones(C)
        k += C if free_focal else 0
        return Rm, tm, scale, x[k:].reshape(-1, 3)

    def residuals(x):
        Rm, tm, scale, pts = unpack(x)
        R_all = np.stack(Rm)[cam_idx]
        t_all = np.stack(tm)[cam_idx]
        Xc = np.einsum("nij,nj->ni", R_all, pts[pt_idx]) + t_all
        uv = Xc[:, :2] / Xc[:, 2:3]
        # Focal changes rescale normalised coordinates of the observation by base_f / f.
        observed = xy / scale[cam_idx, None]
        res = ((uv - observed) * base_f[cam_idx, None] * w[:, None]).ravel()
        gauge = np.array([(np.linalg.norm(tm[1]) - t1_norm) * 1000.0])
        return np.concatenate([res, gauge])

    x0 = []
    for c in range(1, C):
        x0 += [*cv2.Rodrigues(Rs[c])[0].ravel(), *ts[c]]
    if free_focal:
        x0 += [0.0] * C
    x0 = np.array(x0 + list(points0.ravel()), dtype=float)
    n_params = len(x0)
    sparsity = lil_matrix((2 * len(obs) + 1, n_params), dtype=int)
    rows = np.arange(len(obs))
    for r, (c, pid) in enumerate(zip(cam_idx, pt_idx)):
        for row in (2 * r, 2 * r + 1):
            if c > 0:
                sparsity[row, 6 * (c - 1):6 * c] = 1
            if free_focal:
                sparsity[row, 6 * n_cam + c] = 1
            start = 6 * n_cam + (C if free_focal else 0) + 3 * pid
            sparsity[row, start:start + 3] = 1
    sparsity[2 * len(obs), 3:6] = 1
    before = residuals(x0)[:-1]
    solution = least_squares(residuals, x0, jac_sparsity=sparsity, loss="soft_l1", f_scale=3.0, x_scale="jac",
                             max_nfev=60, method="trf")
    Rm, tm, scale, _ = unpack(solution.x)
    residual_px = np.abs(solution.fun[:-1]).reshape(-1, 2)
    for c in range(C):
        Ks[c] = Ks[c].copy()
        Ks[c][0, 0] *= scale[c]
        Ks[c][1, 1] *= scale[c]
    # Metric scale from the stature.
    norm_new = np.stack([normalize_points(points[c], Ks[c], dists[c]) for c in range(C)])
    Xall, _ = triangulate(norm_new, cf, Rm, tm, min_conf=0.6)
    metric = height_m * STATURE_FRACTION / segment_sum(Xall)
    tm = [t * metric for t in tm]
    cameras = [{"name": f"cam{c}", "size": list(sizes[c]), "K": Ks[c], "dist": dists[c], "R": Rm[c], "t": tm[c]}
               for c in range(C)]
    return {"method": "body", "cameras": cameras, "subject_height_m": height_m, "fov_degrees_initial": fov_degrees,
            "intrinsics_known": known, "observations": len(obs),
            "reprojection_px_before": float(np.median(np.linalg.norm(before.reshape(-1, 2), axis=1))),
            "reprojection_px": float(np.median(np.linalg.norm(residual_px, axis=1))),
            "scale_note": "Escala aproximada a partir de la estatura indicada (±5 %)."}


# ---------------------------------------------------------------- skeleton, BVH and GLB

BVH_JOINTS = [
    # name, parent, rotation kind
    ("Hips", None), ("Spine", "Hips"), ("Neck", "Spine"), ("Head", "Neck"),
    ("LeftShoulder", "Spine"), ("LeftArm", "LeftShoulder"), ("LeftForeArm", "LeftArm"), ("LeftHand", "LeftForeArm"),
    ("RightShoulder", "Spine"), ("RightArm", "RightShoulder"), ("RightForeArm", "RightArm"),
    ("RightHand", "RightForeArm"),
    ("LeftUpLeg", "Hips"), ("LeftLeg", "LeftUpLeg"), ("LeftFoot", "LeftLeg"), ("LeftToeBase", "LeftFoot"),
    ("RightUpLeg", "Hips"), ("RightLeg", "RightUpLeg"), ("RightFoot", "RightLeg"), ("RightToeBase", "RightFoot"),
]
PARENT = dict(BVH_JOINTS)
JOINT_NAMES = [name for name, _ in BVH_JOINTS]


def _fill_hold(X: np.ndarray) -> np.ndarray:
    """Hold the nearest valid value where long gaps remain, so every exported frame is complete."""
    X = X.copy()
    for j in range(X.shape[1]):
        valid = np.isfinite(X[:, j]).all(axis=1)
        if not valid.any():
            continue
        idx = np.nonzero(valid)[0]
        nearest = idx[np.clip(np.searchsorted(idx, np.arange(len(X))), 0, len(idx) - 1)]
        prev = idx[np.clip(np.searchsorted(idx, np.arange(len(X)), side="right") - 1, 0, len(idx) - 1)]
        choose = np.where(np.abs(prev - np.arange(len(X))) <= np.abs(nearest - np.arange(len(X))), prev, nearest)
        X[~valid, j] = X[choose[~valid], j]
    return X


def body_points(X: np.ndarray) -> dict[str, np.ndarray]:
    """Joint positions of the BVH skeleton from the 33 landmarks (F,3 each)."""
    p = {name: X[:, IDX[name]] for name in LANDMARKS}
    hips = (p["left_hip"] + p["right_hip"]) / 2
    neck = (p["left_shoulder"] + p["right_shoulder"]) / 2
    spine = (hips + neck) / 2
    head = (p["left_ear"] + p["right_ear"]) / 2
    head = np.where(np.isfinite(head), head, p["nose"])
    out = {"Hips": hips, "Spine": spine, "Neck": neck, "Head": head}
    for side, s in (("Left", "left"), ("Right", "right")):
        out[f"{side}Shoulder"] = neck + 0.2 * (p[f"{s}_shoulder"] - neck)
        out[f"{side}Arm"] = p[f"{s}_shoulder"]
        out[f"{side}ForeArm"] = p[f"{s}_elbow"]
        out[f"{side}Hand"] = p[f"{s}_wrist"]
        index = p[f"{s}_index"]
        out[f"{side}HandEnd"] = np.where(np.isfinite(index), index, p[f"{s}_wrist"] + 0.3 * (p[f"{s}_wrist"] - p[f"{s}_elbow"]))
        out[f"{side}UpLeg"] = p[f"{s}_hip"]
        out[f"{side}Leg"] = p[f"{s}_knee"]
        out[f"{side}Foot"] = p[f"{s}_ankle"]
        toe = p[f"{s}_foot_index"]
        out[f"{side}ToeBase"] = np.where(np.isfinite(toe), toe, p[f"{s}_ankle"] + np.array([0, -0.05, 0.12]))
    out["LeftEar"], out["RightEar"] = p["left_ear"], p["right_ear"]
    return out


def _frame(up, left):
    y = _unit(up)
    x = _unit(left - np.sum(left * y, axis=-1, keepdims=True) * y)
    z = np.cross(x, y)
    return np.stack([x, y, z], axis=-1)  # columns


def _swing(a, b):
    """Batched minimal rotation taking unit vectors a onto b."""
    a, b = _unit(a), _unit(b)
    v = np.cross(a, b)
    c = np.sum(a * b, axis=-1)
    vx = np.zeros(a.shape[:-1] + (3, 3))
    vx[..., 0, 1], vx[..., 0, 2], vx[..., 1, 0] = -v[..., 2], v[..., 1], v[..., 2]
    vx[..., 1, 2], vx[..., 2, 0], vx[..., 2, 1] = -v[..., 0], -v[..., 1], v[..., 0]
    with np.errstate(invalid="ignore", divide="ignore"):
        k = 1.0 / (1.0 + c)
    R = np.eye(3) + vx + vx @ vx * k[..., None, None]
    opposite = c < -0.9999
    if np.any(opposite):
        axis = np.cross(a[opposite], [1.0, 0, 0])
        axis = np.where(np.linalg.norm(axis, axis=-1, keepdims=True) < 1e-6, np.cross(a[opposite], [0, 1.0, 0]), axis)
        axis = _unit(axis)
        R[opposite] = 2 * axis[..., :, None] * axis[..., None, :] - np.eye(3)
    bad = ~np.isfinite(R).all(axis=(-1, -2))
    R[bad] = np.eye(3)
    return R


def solve_skeleton(Xw: np.ndarray) -> dict:
    """Rest offsets (metres, Y up, X = subject's left, Z = forward) and per-frame global/local rotations."""
    pts = body_points(_fill_hold(Xw))

    def med(a, b):
        return float(np.nanmedian(np.linalg.norm(pts[a] - pts[b], axis=-1)))

    half_sh = (med("LeftArm", "Neck") + med("RightArm", "Neck")) / 2
    half_hip = (med("LeftUpLeg", "Hips") + med("RightUpLeg", "Hips")) / 2
    lengths = {
        "spine": med("Spine", "Hips"), "neck": med("Neck", "Spine"), "head": med("Head", "Neck"),
        "upper_arm": (med("LeftForeArm", "LeftArm") + med("RightForeArm", "RightArm")) / 2,
        "forearm": (med("LeftHand", "LeftForeArm") + med("RightHand", "RightForeArm")) / 2,
        "hand": (med("LeftHandEnd", "LeftHand") + med("RightHandEnd", "RightHand")) / 2,
        "thigh": (med("LeftLeg", "LeftUpLeg") + med("RightLeg", "RightUpLeg")) / 2,
        "shin": (med("LeftFoot", "LeftLeg") + med("RightFoot", "RightLeg")) / 2,
        "foot": (med("LeftToeBase", "LeftFoot") + med("RightToeBase", "RightFoot")) / 2,
        "half_shoulders": half_sh, "half_hips": half_hip,
    }
    L = lengths
    offsets = {"Hips": [0, 0, 0], "Spine": [0, L["spine"], 0], "Neck": [0, L["neck"], 0], "Head": [0, L["head"], 0]}
    ends = {"Head": [0, max(0.08, 0.8 * L["head"]), 0]}
    for side, sign in (("Left", 1), ("Right", -1)):
        offsets[f"{side}Shoulder"] = [sign * 0.2 * half_sh, L["neck"], 0]
        offsets[f"{side}Arm"] = [sign * 0.8 * half_sh, 0, 0]
        offsets[f"{side}ForeArm"] = [sign * L["upper_arm"], 0, 0]
        offsets[f"{side}Hand"] = [sign * L["forearm"], 0, 0]
        ends[f"{side}Hand"] = [sign * L["hand"], 0, 0]
        offsets[f"{side}UpLeg"] = [sign * half_hip, 0, 0]
        offsets[f"{side}Leg"] = [0, -L["thigh"], 0]
        offsets[f"{side}Foot"] = [0, -L["shin"], 0]
        offsets[f"{side}ToeBase"] = [0, 0, L["foot"]]
        ends[f"{side}ToeBase"] = [0, 0, max(0.03, 0.25 * L["foot"])]
    G = {}
    G["Hips"] = _frame(pts["Neck"] - pts["Hips"], pts["LeftUpLeg"] - pts["RightUpLeg"])
    G["Spine"] = _frame(pts["Neck"] - pts["Spine"], pts["LeftArm"] - pts["RightArm"])
    ex, ey, ez = np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])

    def follow(name, parent, rest_dir, target):
        G[name] = _swing(G[parent] @ rest_dir, target) @ G[parent]

    follow("Neck", "Spine", ey, pts["Head"] - pts["Neck"])
    ears = pts["LeftEar"] - pts["RightEar"]
    head = _frame(G["Neck"] @ ey, ears)
    G["Head"] = np.where(np.isfinite(head).all(axis=(-1, -2))[:, None, None], head, G["Neck"])
    for side, sign in (("Left", 1), ("Right", -1)):
        dx = sign * ex
        follow(f"{side}Shoulder", "Spine", dx, pts[f"{side}Arm"] - pts[f"{side}Shoulder"])
        follow(f"{side}Arm", f"{side}Shoulder", dx, pts[f"{side}ForeArm"] - pts[f"{side}Arm"])
        follow(f"{side}ForeArm", f"{side}Arm", dx, pts[f"{side}Hand"] - pts[f"{side}ForeArm"])
        follow(f"{side}Hand", f"{side}ForeArm", dx, pts[f"{side}HandEnd"] - pts[f"{side}Hand"])
        follow(f"{side}UpLeg", "Hips", -ey, pts[f"{side}Leg"] - pts[f"{side}UpLeg"])
        follow(f"{side}Leg", f"{side}UpLeg", -ey, pts[f"{side}Foot"] - pts[f"{side}Leg"])
        follow(f"{side}Foot", f"{side}Leg", ez, pts[f"{side}ToeBase"] - pts[f"{side}Foot"])
        G[f"{side}ToeBase"] = G[f"{side}Foot"]
    for name in G:
        bad = ~np.isfinite(G[name]).all(axis=(-1, -2))
        G[name][bad] = np.eye(3)
    local = {name: (G[name] if parent is None else np.swapaxes(G[parent], -1, -2) @ G[name])
             for name, parent in BVH_JOINTS}
    return {"offsets": offsets, "ends": ends, "global": G, "local": local, "root": pts["Hips"], "lengths": lengths,
            "points": pts}


def write_bvh(path: Path, skeleton: dict, fps: float, unit_scale: float = 100.0) -> None:
    from scipy.spatial.transform import Rotation
    children = {name: [n for n, p in BVH_JOINTS if p == name] for name in JOINT_NAMES}
    lines = ["HIERARCHY"]

    def emit(name, depth):
        pad = "  " * depth
        off = np.array(skeleton["offsets"][name]) * unit_scale
        lines.append(f"{pad}{'ROOT' if depth == 0 else 'JOINT'} {name}")
        lines.append(pad + "{")
        lines.append(f"{pad}  OFFSET {off[0]:.4f} {off[1]:.4f} {off[2]:.4f}")
        if depth == 0:
            lines.append(f"{pad}  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation")
        else:
            lines.append(f"{pad}  CHANNELS 3 Zrotation Xrotation Yrotation")
        for child in children[name]:
            emit(child, depth + 1)
        if not children[name]:
            end = np.array(skeleton["ends"].get(name, [0, 0.05, 0])) * unit_scale
            lines.extend([f"{pad}  End Site", pad + "  {", f"{pad}    OFFSET {end[0]:.4f} {end[1]:.4f} {end[2]:.4f}",
                          pad + "  }"])
        lines.append(pad + "}")

    emit("Hips", 0)
    root = skeleton["root"] * unit_scale
    F = len(root)
    eulers = {name: Rotation.from_matrix(skeleton["local"][name]).as_euler("ZXY", degrees=True) for name in JOINT_NAMES}
    lines += ["MOTION", f"Frames: {F}", f"Frame Time: {1.0 / fps:.6f}"]
    for f in range(F):
        values = [*root[f]]
        for name in JOINT_NAMES:
            values += list(eulers[name][f])
        lines.append(" ".join(f"{v:.4f}" for v in values))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_bvh(path: Path) -> dict:
    """Minimal BVH reader with forward kinematics; returns joint names and world positions (F,J,3)."""
    from scipy.spatial.transform import Rotation
    tokens = path.read_text(encoding="utf-8").split()
    i = 0
    joints, stack = [], []
    while tokens[i] != "MOTION":
        token = tokens[i]
        if token in ("ROOT", "JOINT"):
            joints.append({"name": tokens[i + 1], "parent": stack[-1] if stack else None, "channels": []})
            i += 2
        elif token == "End":
            joints.append({"name": joints[stack[-1]]["name"] + "_end", "parent": stack[-1], "channels": [], "end": True})
            i += 2
        elif token == "{":
            stack.append(len(joints) - 1)
            i += 1
        elif token == "}":
            stack.pop()
            i += 1
        elif token == "OFFSET":
            joints[stack[-1]]["offset"] = np.array([float(v) for v in tokens[i + 1:i + 4]])
            i += 4
        elif token == "CHANNELS":
            n = int(tokens[i + 1])
            joints[stack[-1]]["channels"] = tokens[i + 2:i + 2 + n]
            i += 2 + n
        else:
            i += 1
    frames = int(tokens[i + 2])
    frame_time = float(tokens[i + 5])
    values = np.array([float(v) for v in tokens[i + 6:]]).reshape(frames, -1)
    positions = np.zeros((frames, len(joints), 3))
    rotations = np.zeros((frames, len(joints), 3, 3))
    column = 0
    for j, joint in enumerate(joints):
        local_rot = np.tile(np.eye(3), (frames, 1, 1))
        translation = np.zeros((frames, 3))
        for ch in joint["channels"]:
            data = values[:, column]
            column += 1
            if ch.endswith("position"):
                translation[:, "XYZ".index(ch[0])] = data
            else:
                local_rot = local_rot @ Rotation.from_euler(ch[0].lower(), data[:, None], degrees=True).as_matrix()
        parent = joint["parent"]
        offset = joint.get("offset", np.zeros(3))
        if parent is None:
            positions[:, j] = offset + translation
            rotations[:, j] = local_rot
        else:
            positions[:, j] = positions[:, parent] + np.einsum("fij,j->fi", rotations[:, parent], offset)
            rotations[:, j] = rotations[:, parent] @ local_rot
    return {"names": [j["name"] for j in joints], "positions": positions, "frame_time": frame_time,
            "frames": frames, "channels": int(values.shape[1])}


def _bone_mesh(start, end, width):
    """Octahedral bone from start to end (flat shaded): positions and normals, 24 vertices."""
    d = end - start
    length = np.linalg.norm(d)
    axis = d / length if length > 1e-9 else np.array([0, 1.0, 0])
    helper = np.array([0, 0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0, 0])
    u = np.cross(axis, helper)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    mid = start + axis * length * 0.2
    ring = [mid + width * u, mid + width * v, mid - width * u, mid - width * v]
    tris = []
    for k in range(4):
        a, b = ring[k], ring[(k + 1) % 4]
        tris.append((start, b, a))
        tris.append((end, a, b))
    positions, normals = [], []
    for tri in tris:
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        n = n / (np.linalg.norm(n) or 1)
        for vertex in tri:
            positions.append(vertex)
            normals.append(n)
    return np.array(positions, dtype=np.float32), np.array(normals, dtype=np.float32)


def write_glb(path: Path, skeleton: dict, times: np.ndarray) -> dict:
    """Skinned GLB: joint hierarchy with rest offsets, octahedral bone mesh and one animation clip."""
    from scipy.spatial.transform import Rotation
    names = list(JOINT_NAMES)
    end_names = [f"{n}_end" for n in skeleton["ends"]]
    all_nodes = names + end_names
    node_index = {n: i for i, n in enumerate(all_nodes)}
    children = {n: [] for n in all_nodes}
    for n, p in BVH_JOINTS:
        if p:
            children[p].append(node_index[n])
    for n in skeleton["ends"]:
        children[n].append(node_index[f"{n}_end"])
    offset = {**{n: np.array(skeleton["offsets"][n], float) for n in names},
              **{f"{n}_end": np.array(e, float) for n, e in skeleton["ends"].items()}}
    parent = {**{n: p for n, p in BVH_JOINTS}, **{f"{n}_end": n for n in skeleton["ends"]}}
    rest = {}
    for n in all_nodes:  # parents precede children in this order
        rest[n] = offset[n] + (rest[parent[n]] if parent[n] else 0)
    blobs = []

    def add(data: np.ndarray, target=None):
        raw = np.ascontiguousarray(data).tobytes()
        offset_bytes = sum(len(b) for b in blobs)
        pad = (-len(raw)) % 4
        blobs.append(raw + b"\0" * pad)
        view = {"buffer": 0, "byteOffset": offset_bytes, "byteLength": len(raw)}
        if target:
            view["target"] = target
        views.append(view)
        return len(views) - 1

    views, accessors = [], []

    def accessor(data: np.ndarray, kind: str, component: int, target=None, minmax=False):
        view = add(data, target)
        acc = {"bufferView": view, "componentType": component, "count": int(len(data)), "type": kind}
        if minmax:
            flat = data.reshape(len(data), -1)
            acc["min"] = [float(v) for v in flat.min(axis=0)]
            acc["max"] = [float(v) for v in flat.max(axis=0)]
        accessors.append(acc)
        return len(accessors) - 1

    positions, normals, joints = [], [], []
    for n in names:
        for child in children[n]:
            child_name = all_nodes[child]
            length = np.linalg.norm(offset[child_name])
            if length < 1e-4:
                continue
            p, nm = _bone_mesh(rest[n], rest[child_name], float(np.clip(0.12 * length, 0.008, 0.035)))
            positions.append(p)
            normals.append(nm)
            joints.append(np.full(len(p), node_index[n]))
    pos = np.concatenate(positions).astype(np.float32)
    nor = np.concatenate(normals).astype(np.float32)
    jnt = np.zeros((len(pos), 4), dtype=np.uint16)
    jnt[:, 0] = np.concatenate(joints)
    wgt = np.zeros((len(pos), 4), dtype=np.float32)
    wgt[:, 0] = 1.0
    ibm = np.zeros((len(all_nodes), 4, 4), dtype=np.float32)
    for n, i in node_index.items():
        m = np.eye(4, dtype=np.float32)
        m[:3, 3] = -rest[n]
        ibm[i] = m.T  # column-major
    a_pos = accessor(pos, "VEC3", 5126, 34962, True)
    a_nor = accessor(nor, "VEC3", 5126, 34962)
    a_jnt = accessor(jnt, "VEC4", 5123, 34962)
    a_wgt = accessor(wgt, "VEC4", 5126, 34962)
    a_ibm = accessor(ibm.reshape(len(all_nodes), 16), "MAT4", 5126)
    t = (np.asarray(times, dtype=np.float32) - float(times[0])).astype(np.float32)
    a_time = accessor(t, "SCALAR", 5126, minmax=True)
    samplers, channels = [], []
    for n in names:
        quats = Rotation.from_matrix(skeleton["local"][n]).as_quat().astype(np.float32)  # x, y, z, w
        for k in range(1, len(quats)):
            if np.dot(quats[k], quats[k - 1]) < 0:
                quats[k] = -quats[k]
        samplers.append({"input": a_time, "output": accessor(quats, "VEC4", 5126), "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": node_index[n], "path": "rotation"}})
    root = skeleton["root"].astype(np.float32)
    samplers.append({"input": a_time, "output": accessor(root, "VEC3", 5126), "interpolation": "LINEAR"})
    channels.append({"sampler": len(samplers) - 1, "target": {"node": node_index["Hips"], "path": "translation"}})
    nodes = []
    for n in all_nodes:
        node = {"name": n, "translation": [float(v) for v in offset[n]]}
        if children[n]:
            node["children"] = children[n]
        nodes.append(node)
    nodes[node_index["Hips"]]["translation"] = [float(v) for v in root[0]]
    mesh_node = len(nodes)
    nodes.append({"name": "Esqueleto", "mesh": 0, "skin": 0})
    gltf = {
        "asset": {"version": "2.0", "generator": "Kinect Hoard mocap"},
        "scene": 0, "scenes": [{"name": "Captura", "nodes": [node_index["Hips"], mesh_node]}],
        "nodes": nodes,
        "skins": [{"name": "Esqueleto", "joints": list(range(len(all_nodes))), "skeleton": node_index["Hips"],
                   "inverseBindMatrices": a_ibm}],
        "meshes": [{"name": "Huesos", "primitives": [{"attributes": {"POSITION": a_pos, "NORMAL": a_nor,
                                                                     "JOINTS_0": a_jnt, "WEIGHTS_0": a_wgt},
                                                      "material": 0}]}],
        "materials": [{"name": "Hueso", "pbrMetallicRoughness": {"baseColorFactor": [0.48, 0.85, 0.77, 1.0],
                                                                "metallicFactor": 0.0, "roughnessFactor": 0.6}}],
        "animations": [{"name": "Captura", "samplers": samplers, "channels": channels}],
        "accessors": accessors, "bufferViews": views,
        "buffers": [{"byteLength": sum(len(b) for b in blobs)}],
    }
    payload = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((-len(payload)) % 4)
    binary = b"".join(blobs)
    total = 12 + 8 + len(payload) + 8 + len(binary)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, total))
        fh.write(struct.pack("<I4s", len(payload), b"JSON"))
        fh.write(payload)
        fh.write(struct.pack("<I4s", len(binary), b"BIN\0"))
        fh.write(binary)
    return {"nodes": len(nodes), "joints": len(all_nodes), "vertices": int(len(pos)), "keys": int(len(t))}


def read_glb(path: Path) -> dict:
    """Parse a GLB written above and evaluate the clip's joint world positions at every key (for tests)."""
    from scipy.spatial.transform import Rotation
    data = Path(path).read_bytes()
    magic, version, total = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or total != len(data):
        raise ValueError("GLB no válido")
    json_len = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + json_len])
    bin_start = 20 + json_len + 8
    binary = data[bin_start:]
    types = {"SCALAR": 1, "VEC3": 3, "VEC4": 4, "MAT4": 16}
    dtypes = {5126: np.float32, 5123: np.uint16}

    def acc(i):
        a = gltf["accessors"][i]
        v = gltf["bufferViews"][a["bufferView"]]
        array = np.frombuffer(binary, dtype=dtypes[a["componentType"]], count=a["count"] * types[a["type"]],
                              offset=v["byteOffset"])
        return array.reshape(a["count"], types[a["type"]]) if types[a["type"]] > 1 else array

    nodes = gltf["nodes"]
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    animation = gltf["animations"][0]
    keys = len(acc(animation["samplers"][0]["input"]))
    rot = {i: np.tile([0, 0, 0, 1.0], (keys, 1)) for i in range(len(nodes))}
    trans = {i: np.tile(n.get("translation", [0, 0, 0]), (keys, 1)) for i, n in enumerate(nodes)}
    for ch in animation["channels"]:
        out = acc(animation["samplers"][ch["sampler"]]["output"])
        (rot if ch["target"]["path"] == "rotation" else trans)[ch["target"]["node"]] = out
    world_p, world_r = {}, {}

    def solve(i):
        if i in world_p:
            return
        R = Rotation.from_quat(rot[i]).as_matrix()
        if i in parent:
            solve(parent[i])
            world_p[i] = world_p[parent[i]] + np.einsum("fij,fj->fi", world_r[parent[i]], trans[i])
            world_r[i] = world_r[parent[i]] @ R
        else:
            world_p[i], world_r[i] = trans[i].astype(float), R

    joints = gltf["skins"][0]["joints"]
    for j in joints:
        solve(j)
    return {"gltf": gltf, "names": [nodes[j]["name"] for j in joints],
            "positions": np.stack([world_p[j] for j in joints], axis=1), "keys": keys}


# ---------------------------------------------------------------- check video

BONE_COLORS = {"left": (80, 170, 255), "right": (255, 170, 80), "mid": (230, 230, 230)}


def _side(a: int, b: int) -> str:
    names = LANDMARKS[a] + LANDMARKS[b]
    if names.count("left") == 2:
        return "left"
    if names.count("right") == 2:
        return "right"
    return "mid"


def find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
    return str(candidate) if candidate.is_file() else None


class VideoOut:
    """H.264 MP4 through ffmpeg when present (plays in browsers), else OpenCV."""

    def __init__(self, path: Path, fps: float, size):
        self.path, self.size = path, size
        ffmpeg = find_ffmpeg()
        self.process = self.writer = None
        if ffmpeg:
            self.process = subprocess.Popen(
                [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{size[0]}x{size[1]}",
                 "-r", f"{fps:.3f}", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)],
                stdin=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.codec = "h264-ffmpeg"
        else:
            for fourcc in ("avc1", "mp4v"):
                self.writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*fourcc), fps, size)
                if self.writer.isOpened():
                    self.codec = fourcc
                    break

    def write(self, frame):
        if self.process:
            self.process.stdin.write(frame.tobytes())
        else:
            self.writer.write(frame)

    def close(self):
        if self.process:
            self.process.stdin.close()
            self.process.wait()
        elif self.writer:
            self.writer.release()


def _draw_points(image, pts, conf, scale, color_override=None, radius=4):
    for a, b in CONNECTIONS:
        if conf[a] >= 0.5 and conf[b] >= 0.5 and np.isfinite(pts[[a, b]]).all():
            color = color_override or BONE_COLORS[_side(a, b)]
            cv2.line(image, tuple(int(v) for v in pts[a] * scale), tuple(int(v) for v in pts[b] * scale), color, 2,
                     cv2.LINE_AA)
    for j in range(33):
        if conf[j] >= 0.5 and np.isfinite(pts[j]).all():
            cv2.circle(image, tuple(int(v) for v in pts[j] * scale), radius, color_override or (60, 230, 250), -1,
                       cv2.LINE_AA)


def _render_3d(tile, Xw_frame, bounds, angle, label):
    h, w = tile.shape[:2]
    tile[:] = (34, 30, 28)
    center, extent = bounds
    ca, sa = math.cos(angle), math.sin(angle)
    elevation = math.radians(15)
    ce, se = math.cos(elevation), math.sin(elevation)
    scale = 0.85 * min(w, h) / max(extent, 1e-3)

    def proj(p):
        x, y, z = p - center
        xr, zr = ca * x + sa * z, -sa * x + ca * z
        yr = ce * y - se * zr
        return int(w / 2 + xr * scale), int(h / 2 - yr * scale)

    floor_y = 0.0
    half = extent / 2
    for k in np.linspace(-1, 1, 9):
        cv2.line(tile, proj(np.array([center[0] + k * half, floor_y, center[2] - half])),
                 proj(np.array([center[0] + k * half, floor_y, center[2] + half])), (64, 60, 56), 1, cv2.LINE_AA)
        cv2.line(tile, proj(np.array([center[0] - half, floor_y, center[2] + k * half])),
                 proj(np.array([center[0] + half, floor_y, center[2] + k * half])), (64, 60, 56), 1, cv2.LINE_AA)
    for a, b in CONNECTIONS:
        if np.isfinite(Xw_frame[[a, b]]).all():
            cv2.line(tile, proj(Xw_frame[a]), proj(Xw_frame[b]), BONE_COLORS[_side(a, b)], 3, cv2.LINE_AA)
    for j in CORE:
        if np.isfinite(Xw_frame[j]).all():
            cv2.circle(tile, proj(Xw_frame[j]), 4, (60, 230, 250), -1, cv2.LINE_AA)
    cv2.putText(tile, label, (14, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 220, 220), 2, cv2.LINE_AA)


def check_video(path: Path, videos: list[Path], index_maps: list[np.ndarray], detections: list[dict],
                reprojected: list[np.ndarray] | None, Xw: np.ndarray, times: np.ndarray, fps: float,
                progress=None) -> dict:
    tile_w = 640
    sizes = [d["size"] for d in detections]
    tile_h = int(round(tile_w * max(s[1] / s[0] for s in sizes)))
    tile_h += tile_h % 2
    n_tiles = len(videos) + 1
    cols = 1 if n_tiles == 1 else 2
    rows = math.ceil(n_tiles / cols)
    out = VideoOut(path, fps, (cols * tile_w, rows * tile_h))
    readers = [read_frames(v) for v in videos]
    cursors = [-1] * len(videos)
    frames_cache = [None] * len(videos)
    finite = Xw[np.isfinite(Xw).all(axis=-1)]
    lo, hi = np.percentile(finite, 1, axis=0), np.percentile(finite, 99, axis=0)
    bounds = ((lo + hi) / 2, float(np.max(hi - lo)) + 0.4)
    F = len(times)
    for f in range(F):
        canvas = np.zeros((rows * tile_h, cols * tile_w, 3), dtype=np.uint8)
        for c in range(len(videos)):
            target = int(index_maps[c][f])
            if target >= 0:
                while cursors[c] < target:
                    frames_cache[c] = next(readers[c], frames_cache[c])
                    cursors[c] += 1
            tile = np.full((tile_h, tile_w, 3), 24, dtype=np.uint8)
            if target >= 0 and frames_cache[c] is not None:
                frame = frames_cache[c]
                s = tile_w / frame.shape[1]
                resized = cv2.resize(frame, (tile_w, int(round(frame.shape[0] * s))))
                tile[:resized.shape[0]] = resized[:tile_h]
                det = detections[c]
                _draw_points(tile, det["points"][target], det["conf"][target], s)
                if reprojected is not None:
                    rp = reprojected[c][f]
                    for j in CORE:
                        if np.isfinite(rp[j]).all():
                            cv2.circle(tile, tuple(int(v) for v in rp[j] * s), 7, (255, 255, 0), 1, cv2.LINE_AA)
            cv2.putText(tile, f"Camara {c + 1}", (14, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (240, 240, 240), 2,
                        cv2.LINE_AA)
            r, q = divmod(c, cols)
            canvas[r * tile_h:(r + 1) * tile_h, q * tile_w:(q + 1) * tile_w] = tile
        tile = np.zeros((tile_h, tile_w, 3), dtype=np.uint8)
        _render_3d(tile, Xw[f], bounds, math.radians(30) + 0.35 * (times[f] - times[0]),
                   f"Vista 3D  {times[f] - times[0]:5.2f} s")
        r, q = divmod(len(videos), cols)
        canvas[r * tile_h:(r + 1) * tile_h, q * tile_w:(q + 1) * tile_w] = tile
        if n_tiles < rows * cols:
            r, q = divmod(n_tiles, cols)
            for k, line in enumerate(("Puntos amarillos: deteccion 2D", "Circulos cian: 3D reproyectado",
                                      "Naranja: lado izquierdo  Azul: derecho")):
                cv2.putText(canvas, line, (q * tile_w + 20, r * tile_h + 40 + 32 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                            (200, 200, 200), 1, cv2.LINE_AA)
        out.write(canvas)
        if progress and f % 20 == 0:
            progress(f / F)
    out.close()
    return {"codec": out.codec, "size": list(out.size)}


# ---------------------------------------------------------------- pipeline

def _sync(times_list: list[np.ndarray], fps_list: list[float]) -> tuple[np.ndarray, list[np.ndarray]]:
    """Common timeline (camera 1's frames) and, per camera, the frame index nearest each instant (-1 = none)."""
    reference = times_list[0]
    maps = [np.arange(len(reference))]
    for times, fps in zip(times_list[1:], fps_list[1:]):
        if not len(times):
            maps.append(np.full(len(reference), -1))
            continue
        pos = np.clip(np.searchsorted(times, reference), 0, len(times) - 1)
        prev = np.clip(pos - 1, 0, len(times) - 1)
        best = np.where(np.abs(times[prev] - reference) < np.abs(times[pos] - reference), prev, pos)
        ok = np.abs(times[best] - reference) <= 0.6 / fps
        maps.append(np.where(ok, best, -1))
    return reference, maps


def _gather(det: dict, index_map: np.ndarray, key: str, fill):
    data = det[key]
    shape = (len(index_map),) + data.shape[1:]
    out = np.full(shape, fill, dtype=float)
    ok = index_map >= 0
    out[ok] = data[index_map[ok]]
    return out


def detections_for(take: Path, videos: list[Path], detector: str, model: str, progress: Progress) -> list[dict]:
    cache = take / "pose2d"
    cache.mkdir(exist_ok=True)
    out = []
    for c, video in enumerate(videos):
        name = cache / f"{video.stem}-{detector if detector != 'mediapipe' else 'mediapipe-' + model}.npz"
        if name.is_file() and name.stat().st_mtime >= video.stat().st_mtime:
            data = np.load(name, allow_pickle=False)
            det = {k: data[k] for k in ("points", "conf", "world", "times")}
            det.update(json.loads(str(data["meta"])))
        else:
            def report(fraction, c=c):
                progress("poses", (c + fraction) / len(videos), f"Puntos del cuerpo · cámara {c + 1} de {len(videos)}")
            det = detect_mediapipe(video, model, report) if detector == "mediapipe" else detect_markers(video, report)
            meta = {k: det[k] for k in ("size", "fps", "ms_per_frame", "detector")}
            np.savez_compressed(name, points=det["points"], conf=det["conf"], world=det["world"], times=det["times"],
                                meta=json.dumps(meta))
        out.append(det)
    return out


def process(take: Path, options: dict, progress: Progress) -> dict:
    started = time.perf_counter()
    videos = list_videos(take / "videos")
    if not 1 <= len(videos) <= 4:
        raise RuntimeError(f"La toma necesita entre 1 y 4 vídeos en videos/ (tiene {len(videos)})")
    detector = options.get("detector", "mediapipe")
    model = options.get("model", "full")
    dets = detections_for(take, videos, detector, model, progress)
    fps = dets[0]["fps"]
    times, maps = _sync([d["times"] for d in dets], [d["fps"] for d in dets])
    C = len(videos)
    points = [_gather(d, m, "points", np.nan) for d, m in zip(dets, maps)]
    conf = [_gather(d, m, "conf", 0.0) for d, m in zip(dets, maps)]
    calibration_path = take / "calibration.json"
    report = {"format": FORMAT, "take": take.name, "cameras": C, "detector": dets[0]["detector"], "fps": fps,
              "frames": len(times), "videos": [v.name for v in videos],
              "detection_rate": [float(np.mean(c[:, CORE].mean(axis=1) >= 0.5)) for c in conf],
              "ms_per_frame": [d.get("ms_per_frame") for d in dets]}
    if max(report["detection_rate"]) < 0.05:
        raise RuntimeError("No se ha detectado a ninguna persona en los vídeos; comprueba que se vea el cuerpo entero")
    reprojected = None
    progress("triangulation", 0.0, "Reconstruyendo en 3D")
    if C == 1:
        calibration = load_calibration(calibration_path) if calibration_path.is_file() else None
        if calibration and len(calibration["cameras"]) >= 1:
            K, dist = calibration["cameras"][0]["K"], calibration["cameras"][0]["dist"]
            report["intrinsics"] = "calibration.json"
        else:
            K, dist = default_intrinsics(dets[0]["size"], options.get("fov_degrees", 60.0)), np.zeros(5)
            report["intrinsics"] = f"campo de visión supuesto de {options.get('fov_degrees', 60.0):g}°"
        if detector != "mediapipe":
            raise RuntimeError("Una sola cámara necesita el detector MediaPipe (3D del cuerpo)")
        world = _gather(dets[0], maps[0], "world", np.nan)
        norm = normalize_points(points[0], K, dist)
        X = mono_root(norm, conf[0], world)
        report["method"] = "monocular"
        reprojected = [project(X, K, dist, np.eye(3), np.zeros(3))]
    else:
        if not calibration_path.is_file():
            if not options.get("auto_calibrate", True):
                raise RuntimeError("Faltan la calibración: calibra con el tablero ChArUco o activa la autocalibración")
            progress("autocalibration", 0.0, "Calibrando con los puntos del cuerpo")
            calibration = autocalibrate(points, conf, [d["size"] for d in dets], options.get("fov_degrees", 60.0),
                                        options.get("subject_height_m", 1.70), None, progress)
            calibration["videos"] = [v.name for v in videos]
            write_json(calibration_path, calibration)
        calibration = load_calibration(calibration_path)
        cams = calibration["cameras"]
        if len(cams) != C:
            raise RuntimeError(f"La calibración tiene {len(cams)} cámaras y la toma {C} vídeos; vuelve a calibrar")
        for c, cam in enumerate(cams):
            if list(cam["size"]) != list(dets[c]["size"]):
                raise RuntimeError(f"La cámara {c + 1} grabó a {dets[c]['size']} y se calibró a {cam['size']}; "
                                   "calibra con la misma resolución")
        norm = np.stack([normalize_points(points[c], cams[c]["K"], cams[c]["dist"]) for c in range(C)])
        X, errors = triangulate(norm, np.stack(conf), [c["R"] for c in cams], [c["t"] for c in cams],
                                focal=[c["K"][0, 0] for c in cams])
        report["method"] = f"triangulation ({calibration['method']})"
        report["reprojection_px_median"] = float(np.nanmedian(errors)) if np.isfinite(errors).any() else None
        report["reprojection_px_p90"] = float(np.nanpercentile(errors, 90)) if np.isfinite(errors).any() else None
        reprojected = [project(X, c["K"], c["dist"], c["R"], c["t"]) for c in cams]
    raw_valid = float(np.mean(np.isfinite(X[:, CORE]).all(axis=-1)))
    progress("filter", 0.0, "Rellenando huecos y filtrando")
    max_gap = int(round(options.get("max_gap_seconds", 0.5) * fps))
    X, filled = fill_gaps(X, max_gap)
    X = smooth(X, fps, options.get("filter", "butterworth"), options.get("cutoff_hz", 6.0))
    if C == 1:
        reprojected = [project(X, K, dist, np.eye(3), np.zeros(3))]
    else:
        reprojected = [project(X, c["K"], c["dist"], c["R"], c["t"]) for c in cams]
    Xw, transform = align_world(X)
    report.update(core_points_valid_raw=raw_valid, gap_samples_filled=filled, max_gap_frames=max_gap,
                  filter=options.get("filter", "butterworth"), cutoff_hz=options.get("cutoff_hz", 6.0),
                  core_points_valid=float(np.mean(np.isfinite(Xw[:, CORE]).all(axis=-1))),
                  world_alignment=transform)
    progress("export", 0.0, "Exportando JSON, CSV, BVH y GLB")
    rel_times = times - times[0]
    skeleton_json = {
        "format": FORMAT, "units": "metros", "axes": "Y arriba, Z hacia donde mira el sujeto, X a su izquierda",
        "fps": fps, "frames": len(times), "joints": LANDMARKS, "times": np.round(rel_times, 4),
        "positions": [[None if not np.isfinite(p).all() else [round(float(v), 4) for v in p] for p in frame]
                      for frame in Xw],
    }
    write_json(take / "skeleton.json", skeleton_json)
    header = ["time"] + [f"{n}_{a}" for n in LANDMARKS for a in "xyz"]
    with open(take / "skeleton.csv", "w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(header) + "\n")
        for t, frame in zip(rel_times, Xw):
            fh.write(",".join([f"{t:.4f}"] + ["" if not np.isfinite(v) else f"{v:.4f}" for v in frame.ravel()]) + "\n")
    skeleton = solve_skeleton(Xw)
    write_bvh(take / "motion.bvh", skeleton, fps)
    glb = write_glb(take / "motion.glb", skeleton, rel_times)
    # FK check of the exported BVH against the filtered points it came from.
    bvh = read_bvh(take / "motion.bvh")
    names = bvh["names"]
    errors_fk = []
    for joint, key in (("LeftForeArm", "left_elbow"), ("RightForeArm", "right_elbow"), ("LeftHand", "left_wrist"),
                       ("RightHand", "right_wrist"), ("LeftLeg", "left_knee"), ("RightLeg", "right_knee"),
                       ("LeftFoot", "left_ankle"), ("RightFoot", "right_ankle")):
        diff = np.linalg.norm(bvh["positions"][:, names.index(joint)] / 100.0 - Xw[:, IDX[key]], axis=-1)
        errors_fk.append(diff[np.isfinite(diff)])
    errors_fk = np.concatenate(errors_fk)
    report["bvh"] = {"frames": bvh["frames"], "channels": bvh["channels"], "units": "centímetros",
                     "fk_error_mm_median": float(np.median(errors_fk) * 1000) if len(errors_fk) else None,
                     "fk_error_mm_p95": float(np.percentile(errors_fk, 95) * 1000) if len(errors_fk) else None}
    report["glb"] = glb
    report["bone_lengths_m"] = skeleton["lengths"]
    if options.get("check_video", True):
        progress("video", 0.0, "Dibujando el vídeo de comprobación")
        report["check_video"] = check_video(take / "check.mp4", videos, maps, dets, reprojected, Xw, rel_times, fps,
                                            lambda fraction: progress("video", fraction,
                                                                      "Dibujando el vídeo de comprobación"))
    report["seconds"] = round(time.perf_counter() - started, 2)
    write_json(take / "report.json", report)
    return report


def _cli():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("cameras")
    snap = sub.add_parser("snapshot")
    snap.add_argument("index", type=int)
    snap.add_argument("output")
    board = sub.add_parser("board")
    board.add_argument("output")
    for key in ("squares_x", "squares_y"):
        board.add_argument("--" + key.replace("_", "-"), type=int, default=None, dest=key)
    for key in ("square_mm", "marker_mm"):
        board.add_argument("--" + key.replace("_", "-"), type=float, default=None, dest=key)
    rec = sub.add_parser("record")
    rec.add_argument("take")
    rec.add_argument("--cameras", default="0")
    rec.add_argument("--seconds", type=float, default=10)
    rec.add_argument("--fps", type=int, default=30)
    rec.add_argument("--width", type=int, default=1280)
    rec.add_argument("--height", type=int, default=720)
    rec.add_argument("--purpose", choices=("motion", "calibration"), default="motion")
    cal = sub.add_parser("calibrate")
    cal.add_argument("take")
    cal.add_argument("--method", choices=("charuco", "body"), default="charuco")
    cal.add_argument("--board", default="")
    cal.add_argument("--square-mm", type=float, default=None)
    cal.add_argument("--marker-mm", type=float, default=None)
    cal.add_argument("--height", type=float, default=1.70)
    cal.add_argument("--fov", type=float, default=60.0)
    cal.add_argument("--model", default="full")
    cal.add_argument("--detector", default="mediapipe")
    proc = sub.add_parser("process")
    proc.add_argument("take")
    proc.add_argument("--detector", choices=("mediapipe", "synthetic-markers"), default="mediapipe")
    proc.add_argument("--model", choices=("lite", "full", "heavy"), default="full")
    proc.add_argument("--filter", choices=("butterworth", "savgol", "none"), default="butterworth")
    proc.add_argument("--cutoff", type=float, default=6.0)
    proc.add_argument("--height", type=float, default=1.70)
    proc.add_argument("--fov", type=float, default=60.0)
    proc.add_argument("--max-gap", type=float, default=0.5)
    proc.add_argument("--no-auto-calibrate", action="store_true")
    proc.add_argument("--no-video", action="store_true")
    args = parser.parse_args()

    if args.command == "cameras":
        print(json.dumps(list_cameras(), ensure_ascii=False))
        return
    if args.command == "snapshot":
        print(json.dumps(snapshot(args.index, Path(args.output)), ensure_ascii=False))
        return
    if args.command == "board":
        spec = board_spec(squares_x=args.squares_x, squares_y=args.squares_y, square_mm=args.square_mm,
                          marker_mm=args.marker_mm)
        print(json.dumps(board_pdf(Path(args.output), spec), ensure_ascii=False))
        return
    take = Path(args.take)
    take.mkdir(parents=True, exist_ok=True)
    name = {"record": "record-progress.json", "calibrate": "calibration-progress.json"}.get(args.command,
                                                                                         "progress.json")
    progress = Progress(take, name)
    progress("starting", 0.0, "Preparando")
    try:
        if args.command == "record":
            folder = take / ("calib" if args.purpose == "calibration" else "videos")
            result = record(folder, [int(v) for v in args.cameras.split(",") if v != ""], args.seconds, args.fps,
                            args.width, args.height, progress)
            if args.purpose == "motion":
                for old in ("pose2d",):
                    shutil.rmtree(take / old, ignore_errors=True)
            progress.finish(detail="Grabación guardada", result=result)
        elif args.command == "calibrate":
            if args.method == "charuco":
                videos = list_videos(take / "calib") or list_videos(take / "videos")
                if not videos:
                    raise RuntimeError("No hay vídeos del tablero en calib/ ni en videos/")
                spec_file = Path(args.board) if args.board else None
                spec = json.loads(spec_file.read_text(encoding="utf-8")) if spec_file and spec_file.is_file() else {}
                spec = board_spec(**{k: spec.get(k) for k in BOARD_DEFAULT},
                                  **{k: v for k, v in (("square_mm", args.square_mm), ("marker_mm", args.marker_mm))
                                     if v is not None})
                result = calibrate_charuco(videos, spec, progress)
            else:
                videos = list_videos(take / "videos")
                if len(videos) < 2:
                    raise RuntimeError("La autocalibración con el cuerpo necesita al menos dos vídeos")
                dets = detections_for(take, videos, args.detector, args.model, progress)
                _, maps = _sync([d["times"] for d in dets], [d["fps"] for d in dets])
                pts = [_gather(d, m, "points", np.nan) for d, m in zip(dets, maps)]
                cf = [_gather(d, m, "conf", 0.0) for d, m in zip(dets, maps)]
                result = autocalibrate(pts, cf, [d["size"] for d in dets], args.fov, args.height, None, progress)
            result["videos"] = [v.name for v in videos]
            write_json(take / "calibration.json", result)
            summary = {k: result.get(k) for k in ("method", "reprojection_rms_px", "reprojection_px", "joint_frames",
                                                  "observations")}
            summary["cameras"] = len(result["cameras"])
            progress.finish(detail="Calibración guardada", result=summary)
        elif args.command == "process":
            report = process(take, {"detector": args.detector, "model": args.model, "filter": args.filter,
                                    "cutoff_hz": args.cutoff, "subject_height_m": args.height, "fov_degrees": args.fov,
                                    "max_gap_seconds": args.max_gap, "auto_calibrate": not args.no_auto_calibrate,
                                    "check_video": not args.no_video}, progress)
            progress.finish(detail="Captura procesada", result={k: report.get(k) for k in (
                "method", "frames", "fps", "cameras", "detection_rate", "reprojection_px_median", "core_points_valid",
                "seconds")})
    except Exception as exc:
        traceback.print_exc()
        progress.fail(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    _cli()
