"""The Hub health check must not wait for a stopped camera's Windows socket."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import hoard_server

with patch.object(hoard_server.toolkit, 'live_scan_status', side_effect=AssertionError('Health probed scanner')):
    with TestClient(hoard_server.app) as client:
        response = client.get('/api/health')
        assert response.status_code == 200
        assert response.json()['service'] == 'kinect-hoard'
        assert response.json()['camera_on_demand'] is True
        tools = client.get('/api/agent/tools').json()['tools']
        assert len(tools) == len(hoard_server.tool_functions)
        assert {t['name'] for t in tools} >= {'list_modes', 'start_camera', 'connect_blender', 'get_live_frame', 'replay_session'}
        source = json.loads(hoard_server.toolkit.CATALOG.read_text(encoding='utf-8'))
    for generation in ('one', '360'):
        documented = source['capabilities']
        listed = hoard_server.toolkit.list_capabilities(generation)
        assert [row['id'] for row in listed] == [row['id'] for row in documented]
        assert [row['status'] for row in listed] == [row[generation] for row in documented]
print('Health avoids camera probe; shared tools include workspace and live bridges')
