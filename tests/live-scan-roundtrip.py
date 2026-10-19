"""Native live archive keeps raw depth and selection; real mesh + atlas export.

This stationary synthetic fixture checks data integrity, never scan quality.
"""
import gzip
import json
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
from hoard_link.lease import Lease

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fusion import frames


def main():
    folder = ROOT / '.cache' / 'live-roundtrip'
    folder.mkdir(parents=True, exist_ok=True)
    width, height = 160, 120
    y, x = np.mgrid[:height, :width]
    selected = ((x - 80) / 38) ** 2 + ((y - 60) / 44) ** 2 < 1
    depth = np.full((height, width), 2700, dtype='<u2')
    depth[selected] = (1200 + ((x[selected]-80)**2+(y[selected]-60)**2)/30).astype('<u2')
    bgra = np.empty((height, width, 4), dtype=np.uint8)
    bgra[:, :, :3] = np.random.default_rng(19).integers(30, 230, (height,width,3), dtype=np.uint8)
    bgra[:, :, 3] = 255
    runs = []
    for row in range(height):
        positions = np.flatnonzero(selected[row])
        if len(positions): runs += [int(row*width+positions[0]), int(len(positions))]
    source = folder / 'input'
    source.mkdir(exist_ok=True)
    session = source / 'session.khr'
    trajectory = []
    with gzip.open(session, 'wb') as output:
        name = b'KINECT_HOARD_SESSION_1'
        output.write(bytes([len(name)]) + name + struct.pack('<iq',7,0))
        for index in range(3):
            stamp = 638000000000000000 + index*5000000
            output.write(struct.pack('<bqiii',1,stamp,width,height,bgra.nbytes)+bgra.tobytes())
            output.write(struct.pack('<i',width*height)+depth.tobytes()+struct.pack('<i',0))
            trajectory.append({'timestamp_ticks_utc':stamp,'foreground_runs':runs})
    session.with_suffix('.intrinsics.json').write_text(json.dumps({'image_orientation':'camera','intrinsics':{
        'width':width,'height':height,'fx':160,'fy':160,'cx':80,'cy':60,'method':'synthetic'}}),encoding='utf-8')
    (source/'live.scan.json').write_text(json.dumps({'poses':trajectory}),encoding='utf-8')
    out = folder / 'output-r3'
    with Lease(vram_mb=2048,gpu=0,owner='codex-kinect',purpose='939 archive fixture',timeout_s=30,autostart=False):
        subprocess.run([str(ROOT/'KinectHoard.App/bin/Release/net48/KinectHoard.App.exe'),
                        '--scanner-replay',str(session),'one','fixed',str(out),'amp'],check=True,timeout=180)
    manifest = json.loads((out/'live.scan.json').read_text(encoding='utf-8'))
    archived = list(frames(out/'session.khr', with_quality=True))
    assert archived and len(archived)==len(manifest['poses'])
    for frame, pose in zip(archived, manifest['poses']):
        assert frame[0]==pose['timestamp_ticks_utc']
        assert np.array_equal(np.frombuffer(frame[4],dtype='<u2').reshape(depth.shape),depth), 'raw depth was replaced by mask'
        restored=np.zeros(depth.size,dtype=bool)
        for start,count in zip(pose['foreground_runs'][::2],pose['foreground_runs'][1::2]):
            restored[start:start+count]=True
        assert np.array_equal(restored.reshape(depth.shape),selected)
    for name in ('scan.ply','scan.obj','scan.mtl','scan-albedo.png','scan.scan.json'):
        assert (out/name).stat().st_size>0,name
    assert 'map_Kd scan-albedo.png' in (out/'scan.mtl').read_text(encoding='utf-8')
    assert 'mtllib scan.mtl' in (out/'scan.obj').read_text(encoding='utf-8')
    result=json.loads((out/'replay-result.json').read_text(encoding='utf-8'))
    assert result['state']=='finished' and result['frames_integrated']>0
    print('Raw depth + saved selection + native mesh/atlas round trip passed; stationary fixture only')


if __name__ == '__main__':
    main()
