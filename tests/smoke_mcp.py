"""Run with .venv/Scripts/python.exe tests/smoke_mcp.py."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp import Client, StdioServerParameters
from mcp_server import mcp


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / "docs" / "capabilities.json").read_text(encoding="utf-8"))
    for item in catalog["capabilities"]:
        for relative in [item["docs"], *item["code"]]:
            assert (root / relative).is_file(), f"Falta en el catálogo: {relative}"
    async with Client(mcp) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        assert {"start_live_scan", "live_scan_status", "control_live_scan"} <= names
        assert {"list_capabilities", "get_capability", "read_hoard_source", "sensor_status", "capture_artifact", "record_session", "record_audio", "recognize_speech", "analyze_face", "capture_face3d", "scan_head", "capture_gestures", "analyze_gesture_session", "scan_3d", "fuse_session", "session_info"} <= names
        listing = await client.call_tool("list_capabilities", {"generation": "one"})
        assert not listing.is_error
        detail = await client.call_tool("get_capability", {"capability_id": "point-cloud"})
        assert not detail.is_error
        source = await client.call_tool("read_hoard_source", {"relative_path": "KinectHoard.Core/Camera.cs"})
        assert not source.is_error
        docs = await client.call_tool("read_hoard_source", {"relative_path": "docs/mcp.md"})
        assert not docs.is_error
        outside = await client.call_tool("read_hoard_source", {"relative_path": "../audio-prueba.json"})
        assert outside.is_error
        session = Path(__file__).resolve().parents[1] / "captures" / "smoke-session.khr"
        if session.is_file():
            summary = await client.call_tool("session_info", {"filename": session.name})
            assert not summary.is_error
    server = StdioServerParameters(command=sys.executable, args=[str(root / "mcp_server.py")])
    async with Client(server) as client:
        listing = await client.call_tool("list_capabilities", {"generation": "360"})
        assert not listing.is_error
        print(f"MCP listo: {len(names)} herramientas; catálogo y transporte stdio verificados")


if __name__ == "__main__":
    asyncio.run(main())
