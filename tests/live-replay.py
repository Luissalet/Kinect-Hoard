"""Live tracker through the replay source, on a synthetic person turning with swinging arms.

Run with .venv-scan/Scripts/python.exe tests/live-replay.py
Feeds a generated session through the native live engine (--scanner-replay,
same FusionScanner.Process as the sensor) with the coloured-ICP tracker and
checks, with replay_score: rotation error against ground truth, loop closure
on keyframes, volume rebuild, per-frame latency report, live mesh residual
and the exported OBJ.
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
    # Same lookup as mcp_server._exe; the scan environment has no MCP package.
    for candidate in (ROOT / "KinectHoard.App.exe", ROOT / "KinectHoard.App" / "bin" / "Release" / "net48" / "KinectHoard.App.exe"):
        if candidate.is_file():
            return candidate
    raise SystemExit("KinectHoard.App.exe no está compilado; ejecuta build.ps1")


def replay(session: Path, output: Path) -> None:
    for processor in ("amp", "cpu"):
        command = [str(_exe()), "--scanner-replay", str(session), "one", "fixed", str(output), processor, "icp", "0"]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=1800)
        if result.returncode == 0:
            return
        print(f"{processor}: {result.returncode} {result.stderr[-600:]}")
    raise SystemExit("La reproducción nativa no terminó")


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "synthetic-turn"
        # 1.15 turns in 14 s at 10 fps: 3.5 degrees per frame, arms swinging 12 degrees.
        generate(source, turn_seconds=12.0, fps=10.0, turns=1.15, swing_degrees=12.0)
        output = Path(temporary) / "replay-synthetic"
        replay(source / "session.khr", output)
        journal = json.loads((output / "live.scan.json").read_text(encoding="utf-8"))
        assert journal["tracker"] == "icp" and journal["replay_source"] == str(source.resolve())
        score = json.loads((output / "replay-score.json").read_text(encoding="utf-8"))
        trajectory = score["synthetic"]["trajectory"]
        assert trajectory["frames"] >= 0.9 * score["synthetic"]["frames"], trajectory
        assert trajectory["rotation_deg_rms"] < 5.0 and trajectory["rotation_deg_final"] < 4.0, trajectory
        tracking = score["tracking"]
        assert tracking["loop_closures"] >= 1 and tracking["graph_solves"] >= 1, tracking
        assert tracking["subject_absent_frames"] == 0 and tracking["lost"] <= 2, tracking
        latency = score["latency"]
        assert latency["frames"] >= journal["frames_integrated"] and latency["process_ms_median"] > 0, latency
        # The volume rebuild after a loop closure is spread over frames into a
        # spare volume: it used to stall one frame for 150-450 ms.
        assert tracking["volume_rebuilds"] >= 1 and not tracking["rebuild_in_progress"], tracking
        assert latency["rebuild_ms_max"] < 80, latency
        # Poses as fused live, before later loop closures moved them.
        live = score["synthetic"]["trajectory_live"]
        assert live and live["frames"] == trajectory["frames"] and live["rotation_deg_rms"] < 6.0, live
        assert score["mesh"]["depth_residual_mm_median"] < 6.0, score["mesh"]
        assert score["synthetic"]["surface"]["completeness_within_1cm"] > 0.6, score["synthetic"]["surface"]
        assert len(journal["trajectory"]) == score["frames_tracked"] >= len(journal["poses"])
        obj = (output / "scan.obj").read_text(encoding="ascii", errors="replace")
        assert "mtllib" in obj and "\nvt " in obj
        print(f"Directo reproducido: {trajectory['frames']} vistas, rotación RMS {trajectory['rotation_deg_rms']:.2f}°, "
              f"final {trajectory['rotation_deg_final']:.2f}°, {tracking['loop_closures']} cierres de vuelta, "
              f"{latency['process_ms_median']:.1f} ms por fotograma (p95 {latency['process_ms_p95']:.1f})")


if __name__ == "__main__":
    main()
