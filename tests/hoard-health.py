"""The Hub health check must not wait for a stopped camera's Windows socket."""
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
        assert len(tools) == 24
        assert len(hoard_server.toolkit._catalog()['capabilities']) == 26
print('Health avoids camera probe; 24 MCP tools describe 26 catalogue capabilities')
