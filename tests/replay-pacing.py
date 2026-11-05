"""Replay as live at the sensor's 30 fps, and what the latency report counts.

Run with .venv-scan/Scripts/python.exe tests/replay-pacing.py
1. A synthetic turn recorded at 30 fps is replayed at its own pace. Frames are
   decoded ahead on another thread, as a sensor delivers them: when decoding
   ran on the processing thread the replay dropped about two frames in three
   (534 of 806) although tracking itself fits the budget.
2. The same take with the subject missing from a third of its frames (empty
   archived masks), every frame at once: those frames are reported as idle
   and stay out of the per-frame timing, so they cannot raise the share of
   frames within budget.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from turn_synthetic import generate  # noqa: E402


def _exe() -> Path:
    for candidate in (ROOT / "KinectHoard.App.exe", ROOT / "KinectHoard.App" / "bin" / "Release" / "net48" / "KinectHoard.App.exe"):
        if candidate.is_file():
            return candidate
    raise SystemExit("KinectHoard.App.exe no está compilado; ejecuta build.ps1")


def replay(session: Path, output: Path, speed: str) -> dict:
    env = {**__import__("os").environ, "KINECT_HOARD_REPLAY_NO_TEXTURE": "1"}
    command = [str(_exe()), "--scanner-replay", str(session), "one", "fixed", str(output), "amp", "icp", speed]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=1800, env=env)
    if result.returncode != 0:
        raise SystemExit(f"La reproducción nativa no terminó: {result.returncode} {result.stderr[-600:]}")
    return json.loads((output / "live.scan.json").read_text(encoding="utf-8"))


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "synthetic-30fps"
        # Half a turn in 6 s at 30 fps: 180 frames, 1 degree per sensor frame. The
        # first frame allocates both volumes (~0.5 s), so about 15 frames are
        # always dropped at the start.
        generate(source, turn_seconds=12.0, fps=30.0, turns=0.5, swing_degrees=8.0)
        journal = replay(source / "session.khr", Path(temporary) / "replay-paced", "1")
        feed, latency = journal["replay"], journal["latency"]
        assert feed["frames"] == feed["delivered"] + feed["dropped"], feed
        assert feed["dropped"] <= 0.25 * feed["frames"], feed
        assert feed["late_ms_median"] < 12, feed
        assert latency["frames"] == journal["frames_integrated"] + journal["frames_rejected"], (latency, journal["frames_integrated"])

        manifest = json.loads((source / "live.scan.json").read_text(encoding="utf-8"))
        third = len(manifest["poses"]) // 3
        for entry in manifest["poses"][third:2 * third]:
            entry["foreground_runs"] = []
        (source / "live.scan.json").write_text(json.dumps(manifest), encoding="utf-8")
        gap = replay(source / "session.khr", Path(temporary) / "replay-gap", "0")
        timed = gap["latency"]
        assert timed["idle_frames"] >= third, timed
        assert timed["frames"] == gap["frames_integrated"] + gap["frames_rejected"], (timed, gap["frames_integrated"])
        assert timed["frames"] + timed["idle_frames"] == gap["replay"]["delivered"], (timed, gap["replay"])
        print(f"Ritmo de 30 fps: {feed['delivered']} de {feed['frames']} fotogramas procesados ({feed['dropped']} descartados), "
              f"retraso mediano {feed['late_ms_median']} ms, {latency['process_ms_median']} ms por fotograma; "
              f"{timed['idle_frames']} fotogramas sin sujeto fuera de la medida de tiempo")


if __name__ == "__main__":
    main()
