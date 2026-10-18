"""Validate dual-camera 3D calibration with noise, one mismatch and a degenerate rig."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dual_calibration import estimate  # noqa: E402


def main() -> None:
    import numpy as np

    folder = ROOT / ".cache" / "dual-calibration-smoke"
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(12)
    second = rng.uniform(-0.3, 0.3, size=(12, 3)) + [0, 0, 1.5]
    angle = np.deg2rad(170)
    rotation = np.array([[np.cos(angle), 0, np.sin(angle)],
                         [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]])
    translation = np.array([0.8, -0.04, 2.8])
    first = second @ rotation.T + translation + rng.normal(0, 0.002, size=(12, 3))
    first[11] += [0.3, 0.2, -0.1]
    landmarks = folder / "landmarks.json"
    landmarks.write_text(json.dumps({"format": "KINECT_HOARD_DUAL_LANDMARKS_1",
                                     "first_points_metres": first.tolist(),
                                     "second_points_metres": second.tolist()}), encoding="utf-8")
    result = estimate(landmarks, folder / "calibration.json")
    recovered = np.asarray(result["world_from_second"])
    assert result["inliers"] == 11
    assert result["rms_error_metres"] < 0.006
    assert np.linalg.norm(recovered[:3, :3] - rotation) < 0.02
    assert np.linalg.norm(recovered[:3, 3] - translation) < 0.02

    flat = json.loads(landmarks.read_text(encoding="utf-8"))
    flat["first_points_metres"] = [[x, y, 0] for x, y, _ in first]
    flat["second_points_metres"] = [[x, y, 0] for x, y, _ in second]
    landmarks.write_text(json.dumps(flat), encoding="utf-8")
    try:
        estimate(landmarks, folder / "invalid.json")
    except ValueError as error:
        assert "tres dimensiones" in str(error)
    else:
        raise AssertionError("Se aceptó una calibración plana degenerada")
    print(f"Calibración dual: 11/12 puntos, RMS {result['rms_error_metres'] * 1000:.1f} mm")


if __name__ == "__main__":
    main()
