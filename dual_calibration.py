"""Estimate One <- 360 rigid calibration from measured 3D landmark pairs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _rigid_fit(first, second, np):
    first_center = first.mean(axis=0)
    second_center = second.mean(axis=0)
    covariance = (second - second_center).T @ (first - first_center)
    left, _, right = np.linalg.svd(covariance)
    rotation = right.T @ np.diag([1.0, 1.0, np.linalg.det(right.T @ left.T)]) @ left.T
    translation = first_center - rotation @ second_center
    matrix = np.eye(4)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = translation
    return matrix


def estimate(landmarks_path: Path, output_path: Path, threshold_metres: float = 0.02) -> dict:
    import numpy as np

    data = json.loads(landmarks_path.read_text(encoding="utf-8"))
    if data.get("format") != "KINECT_HOARD_DUAL_LANDMARKS_1":
        raise ValueError("Formato de correspondencias desconocido")
    first = np.asarray(data.get("first_points_metres"), dtype=np.float64)
    second = np.asarray(data.get("second_points_metres"), dtype=np.float64)
    if first.shape != second.shape or first.ndim != 2 or first.shape[1] != 3 or len(first) < 4:
        raise ValueError("Se necesitan al menos cuatro pares XYZ correspondientes")
    if not np.isfinite(first).all() or not np.isfinite(second).all():
        raise ValueError("Las coordenadas deben ser finitas")
    if not 0.005 <= threshold_metres <= 0.05:
        raise ValueError("El umbral RANSAC debe estar entre 5 y 50 mm")
    if np.linalg.matrix_rank(first - first.mean(axis=0), tol=1e-3) < 3 or \
       np.linalg.matrix_rank(second - second.mean(axis=0), tol=1e-3) < 3:
        raise ValueError("Los puntos deben extenderse en tres dimensiones; un plano o línea es ambiguo")
    spread = min(float(np.linalg.norm(np.ptp(first, axis=0))), float(np.linalg.norm(np.ptp(second, axis=0))))
    if spread < 0.12:
        raise ValueError("El objeto de calibración debe cubrir al menos 12 cm")

    rng = np.random.default_rng(360)
    best = None
    best_count = 0
    best_rms = float("inf")
    trials = min(2000, max(100, len(first) * 40))
    for _ in range(trials):
        sample = rng.choice(len(first), 4, replace=False)
        if np.linalg.matrix_rank(first[sample] - first[sample].mean(axis=0), tol=1e-3) < 3:
            continue
        candidate = _rigid_fit(first[sample], second[sample], np)
        aligned = second @ candidate[:3, :3].T + candidate[:3, 3]
        residuals = np.linalg.norm(aligned - first, axis=1)
        inliers = residuals <= threshold_metres
        count = int(inliers.sum())
        if count < 4:
            continue
        rms = float(np.sqrt(np.mean(residuals[inliers] ** 2)))
        if count > best_count or count == best_count and rms < best_rms:
            best, best_count, best_rms = inliers, count, rms
    if best is None or best_count < max(4, int(np.ceil(len(first) * 0.7))):
        raise ValueError("No hay suficientes correspondencias coherentes para calibrar")

    matrix = _rigid_fit(first[best], second[best], np)
    aligned = second @ matrix[:3, :3].T + matrix[:3, 3]
    residuals = np.linalg.norm(aligned - first, axis=1)
    rms = float(np.sqrt(np.mean(residuals[best] ** 2)))
    maximum = float(residuals[best].max())
    if rms > 0.03:
        raise ValueError(f"Error RMS {rms:.3f} m supera 3 cm")
    result = {
        "format": "KINECT_HOARD_DUAL_EXTRINSICS_1",
        "world_from_second": matrix.tolist(),
        "calibration_method": "3D corresponding landmarks + RANSAC + rigid SVD fit",
        "rms_error_metres": rms,
        "max_inlier_error_metres": maximum,
        "ransac_threshold_metres": threshold_metres,
        "inliers": best_count,
        "landmarks": len(first),
        "inlier_indices": np.flatnonzero(best).tolist(),
        "source_landmarks": str(landmarks_path),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("landmarks", type=Path, help="JSON con pares XYZ medidos por ambas cámaras")
    parser.add_argument("output", type=Path, help="JSON de extrínsecos para el escáner dual")
    parser.add_argument("--threshold", type=float, default=0.02, help="Umbral RANSAC en metros")
    args = parser.parse_args()
    result = estimate(args.landmarks, args.output, args.threshold)
    print(f"Calibración: {result['inliers']}/{result['landmarks']} puntos, "
          f"RMS {result['rms_error_metres'] * 1000:.1f} mm -> {args.output}")


if __name__ == "__main__":
    main()
