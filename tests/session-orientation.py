"""Asymmetric RGBD and full-resolution texture survive SDK mirror normalization."""
import gzip
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fusion import reconstruction_intrinsics
from quality_scan import _load_session


def main():
    import numpy as np
    import open3d as o3d

    folder = ROOT / '.cache' / 'session-orientation'
    folder.mkdir(parents=True, exist_ok=True)
    width, height = 64, 48
    yy, xx = np.mgrid[:height, :width]
    depth = (1300 + xx * 2 + yy).astype('<u2')
    rgb = np.stack((30 + xx * 3, 20 + yy * 4, 50 + xx + yy), axis=2).astype(np.uint8)
    fy, fx = np.mgrid[:height * 2, :width * 2]
    full_rgb = np.stack((20 + fx, 30 + fy, 70 + fx // 2), axis=2).astype(np.uint8)
    mapping = np.stack((xx * 2., yy * 2.), axis=2).astype('<f4')
    loaded = []
    for mirrored in (False, True):
        path = folder / ('sdk.khr' if mirrored else 'camera.khr')
        image, values, full, coordinates = rgb, depth, full_rgb, mapping.copy()
        if mirrored:
            image, values, full = rgb[:, ::-1], depth[:, ::-1], full_rgb[:, ::-1]
            coordinates = mapping[:, ::-1].copy()
            coordinates[:, :, 0] = width * 2 - 1 - coordinates[:, :, 0]
        bgra = np.concatenate((image[:, :, ::-1], np.full((height, width, 1), 255, np.uint8)), axis=2).tobytes()
        full_bgra = np.concatenate((full[:, :, ::-1], np.full((height * 2, width * 2, 1), 255, np.uint8)), axis=2).tobytes()
        with gzip.open(path, 'wb') as output:
            name = b'KINECT_HOARD_SESSION_2'
            output.write(bytes([len(name)]) + name + struct.pack('<iq', 7, 0))
            output.write(struct.pack('<bqiii', 1, 638000000000000000, width, height, len(bgra)))
            output.write(bgra + struct.pack('<i', width * height) + values.tobytes() + struct.pack('<i', 0))
            output.write(struct.pack('<iii', width * 2, height * 2, len(full_bgra)) + full_bgra)
            output.write(struct.pack('<i', width * height) + coordinates.tobytes())
        metadata = {'format': 'KINECT_HOARD_RGBD_1', 'intrinsics': {
            'width': width, 'height': height, 'fx': 55, 'fy': 56,
            'cx': width - 1 - 29.4 if mirrored else 29.4, 'cy': 22.7,
            'method': 'Kinect SDK depth camera intrinsics' if mirrored else 'synthetic camera',
        }}
        path.with_suffix('.intrinsics.json').write_text(json.dumps(metadata), encoding='utf-8')
        group, intrinsic, report = _load_session(path, 'first', 'fixed', 1, 3., 0, None, np, o3d)
        frame = group[0]
        assert np.array_equal(frame.rgb, rgb)
        assert np.array_equal(frame.depth, depth)
        assert abs(intrinsic.get_principal_point()[0] - 29.4) < 1e-10
        map_xy = frame.depth_to_color.astype(int)
        observed = frame.full_rgb[map_xy[:, :, 1], map_xy[:, :, 0]]
        assert np.array_equal(observed, full_rgb[yy * 2, xx * 2])
        assert report['horizontal_flip_applied'] is mirrored
        loaded.append(frame)
        if mirrored:
            metadata['image_orientation'] = 'camera'
            path.with_suffix('.intrinsics.json').write_text(json.dumps(metadata), encoding='utf-8')
            _, flipped = reconstruction_intrinsics(path)
            assert not flipped  # An already rectified SDK session can override the legacy default.
    assert np.array_equal(loaded[0].rgb, loaded[1].rgb)
    print('RGBD geometry, off-centre principal point and original RGB mapping retain physical orientation')


if __name__ == '__main__':
    main()
