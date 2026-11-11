"""Synthetic motion-capture take with ground truth: a walking puppet seen by two calibrated cameras.

Each core landmark is drawn as a disc of one exact colour (mocap.synthetic_colors) into a
lossless video, so the synthetic-marker detector recovers the 2D points that a pose model
would give. A second pair of videos shows a ChArUco board moving in front of both cameras.

    .venv-mocap/Scripts/python.exe tests/mocap_synthetic.py OUTPUT_FOLDER
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mocap  # noqa: E402

WIDTH, HEIGHT, FOCAL, FPS = 960, 540, 800.0, 30.0
HEIGHT_M = 1.75
CAMERA_POSITIONS = [np.array([2.5, 1.2, 5.0]), np.array([-2.6, 1.4, 4.6])]
TARGET = np.array([0.0, 0.9, 0.0])
BOARD = {"squares_x": 5, "squares_y": 7, "square_mm": 120.0, "marker_mm": 90.0, "dictionary": "DICT_4X4_50"}


def camera(position: np.ndarray):
    z = TARGET - position
    z /= np.linalg.norm(z)
    x = np.cross(z, [0.0, 1.0, 0.0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.stack([x, y, z])
    return R, -R @ position


def intrinsics():
    return np.array([[FOCAL, 0, WIDTH / 2], [0, FOCAL, HEIGHT / 2], [0, 0, 1.0]])


def puppet(t: float) -> np.ndarray:
    """33 landmarks in world metres (Y up); only the core ones are finite."""
    H = HEIGHT_M
    phase = 2 * math.pi * 0.9 * t
    yaw = 0.35 * math.sin(0.8 * t)
    root = np.array([0.3 * math.sin(0.5 * t), 0.530 * H + 0.02 * math.sin(2 * phase), 0.6 * t - 0.9])
    body = {}
    thigh, shank = 0.245 * H, 0.246 * H
    neck = np.array([0.0, 0.288 * H, 0.0])
    for side, sign in (("left", 1), ("right", -1)):
        hip = np.array([sign * 0.09, 0.0, 0.0])
        theta = 0.4 * math.sin(phase) * sign
        knee_flex = 0.25 + 0.35 * max(0.0, math.sin(phase * sign + 0.6))
        d1 = np.array([0.0, -math.cos(theta), math.sin(theta)])
        d2 = np.array([0.0, -math.cos(theta - knee_flex), math.sin(theta - knee_flex)])
        knee = hip + thigh * d1
        ankle = knee + shank * d2
        body[f"{side}_hip"], body[f"{side}_knee"], body[f"{side}_ankle"] = hip, knee, ankle
        body[f"{side}_heel"] = ankle + np.array([0.0, -0.05, -0.05])
        body[f"{side}_foot_index"] = ankle + np.array([sign * 0.01, -0.06, 0.14])
        shoulder = neck + np.array([sign * 0.19, 0.0, 0.0])
        swing = -0.5 * math.sin(phase) * sign
        bend = 0.45 + 0.25 * math.sin(phase * sign)
        abduct = 0.25
        upper = np.array([sign * math.sin(abduct), -math.cos(abduct) * math.cos(swing), math.cos(abduct) * math.sin(swing)])
        fore = np.array([sign * 0.12, -math.cos(swing + bend), math.sin(swing + bend)])
        fore /= np.linalg.norm(fore)
        elbow = shoulder + 0.30 * upper
        wrist = elbow + 0.25 * fore
        body[f"{side}_shoulder"], body[f"{side}_elbow"], body[f"{side}_wrist"] = shoulder, elbow, wrist
        body[f"{side}_index"] = wrist + 0.08 * fore
        body[f"{side}_ear"] = neck + np.array([sign * 0.075, 0.17, 0.0])
    body["nose"] = neck + np.array([0.0, 0.16, 0.09])
    c, s = math.cos(yaw), math.sin(yaw)
    Ry = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    out = np.full((33, 3), np.nan)
    for name, p in body.items():
        out[mocap.IDX[name]] = Ry @ p + root
    return out


def render_people(folder: Path, frames: int) -> np.ndarray:
    folder.mkdir(parents=True, exist_ok=True)
    colors = mocap.synthetic_colors()
    K = intrinsics()
    truth = np.array([puppet(f / FPS) for f in range(frames)])
    for c, position in enumerate(CAMERA_POSITIONS):
        R, t = camera(position)
        writer = cv2.VideoWriter(str(folder / f"cam{c}.mkv"), cv2.VideoWriter_fourcc(*"FFV1"), FPS, (WIDTH, HEIGHT))
        assert writer.isOpened(), "FFV1 writer unavailable"
        for f in range(frames):
            image = np.full((HEIGHT, WIDTH, 3), 40, dtype=np.uint8)
            Xc = truth[f] @ R.T + t
            uv = mocap.project(truth[f], K, np.zeros(5), R, t)
            for a, b in mocap.CONNECTIONS:
                if np.isfinite(uv[[a, b]]).all():
                    cv2.line(image, tuple(int(round(v)) for v in uv[a]), tuple(int(round(v)) for v in uv[b]),
                             (110, 110, 110), 2, cv2.LINE_8)
            order = sorted(mocap.CORE, key=lambda j: -Xc[j, 2])  # far first
            for j in order:
                radius = max(3, int(round(5 * 4.5 / Xc[j, 2])))
                cv2.circle(image, tuple(int(round(v)) for v in uv[j]), radius, colors[j], -1, cv2.LINE_8)
            writer.write(image)
        writer.release()
    return truth


def render_board(folder: Path, frames: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    board = mocap._board(BOARD)
    square = BOARD["square_mm"] / 1000
    ppx = 120
    margin = 60
    image = board.generateImage((BOARD["squares_x"] * ppx + 2 * margin, BOARD["squares_y"] * ppx + 2 * margin),
                                marginSize=margin, borderBits=1)
    image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    ppm = ppx / square
    # board metres -> board image pixels
    S = np.array([[ppm, 0, margin - 0.5], [0, ppm, margin - 0.5], [0, 0, 1]])
    size = np.array([BOARD["squares_x"] * square, BOARD["squares_y"] * square])
    K = intrinsics()
    for c, position in enumerate(CAMERA_POSITIONS):
        R, t = camera(position)
        writer = cv2.VideoWriter(str(folder / f"cam{c}.mkv"), cv2.VideoWriter_fourcc(*"FFV1"), FPS, (WIDTH, HEIGHT))
        for f in range(frames):
            s = f / frames
            tilt_x, tilt_y = 0.6 * math.sin(2 * math.pi * s), 0.6 * math.cos(2 * math.pi * s * 1.3)
            base = np.array([[1.0, 0, 0], [0, -1.0, 0], [0, 0, -1.0]]).T  # board x right, y down, z away
            rx = cv2.Rodrigues(np.array([tilt_x, 0, 0]))[0]
            ry = cv2.Rodrigues(np.array([0, tilt_y, 0]))[0]
            Rb = ry @ rx @ base
            center = np.array([0.8 * math.sin(2 * math.pi * s), 1.15 + 0.35 * math.cos(4 * math.pi * s), 2.7 + 1.0 * math.sin(6 * math.pi * s)])
            origin = center - Rb @ np.array([size[0] / 2, size[1] / 2, 0])
            Rcb = R @ Rb
            tcb = R @ origin + t
            H = K @ np.column_stack([Rcb[:, 0], Rcb[:, 1], tcb]) @ np.linalg.inv(S)
            frame = cv2.warpPerspective(image, H, (WIDTH, HEIGHT), flags=cv2.INTER_LINEAR,
                                        borderMode=cv2.BORDER_CONSTANT, borderValue=(70, 70, 70))
            writer.write(frame)
        writer.release()
    (folder.parent / "board.json").write_text(json.dumps({"format": "KINECT_HOARD_CHARUCO_1", **BOARD}), encoding="utf-8")


def ground_truth_cameras():
    out = []
    for position in CAMERA_POSITIONS:
        R, t = camera(position)
        out.append({"K": intrinsics(), "R": R, "t": t})
    return out


def build(folder: Path, frames: int = 90, board_frames: int = 60) -> np.ndarray:
    truth = render_people(folder / "videos", frames)
    render_board(folder / "calib", board_frames)
    np.save(folder / "truth.npy", truth)
    return truth


if __name__ == "__main__":
    build(Path(sys.argv[1]))
    print("synthetic take written to", sys.argv[1])
