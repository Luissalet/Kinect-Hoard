"""A capability must have a usable mode and the same callable schema in web and MCP."""
import asyncio
import json
import socket
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from mcp import Client, StdioServerParameters
import camera_runtime
import hoard_server
import mcp_server


async def main():
    root = Path(__file__).resolve().parents[1]
    with TestClient(hoard_server.app) as web:
        assert web.get("/").status_code == 200
        for path in ("/ui/workspace.css", "/ui/workspace.js", "/ui/hoard-theme.css", "/app-icon.svg", "/scanner"):
            assert web.get(path).status_code == 200, path
        modes = web.get("/api/workspace/modes").json()
        assert len(modes) == 10
        assert {item["id"] for mode in modes for item in mode["references"]} == {
            item["id"] for item in mcp_server._catalog()["capabilities"]}
        contract = {tool["name"]: tool for tool in web.get("/api/agent/tools").json()["tools"]}
        for mode in modes:
            assert mode["recipe"] and all(name in contract for name in mode["tools"]), mode["id"]
            for ref in mode["references"]:
                assert web.get("/api/workspace/source", params={"path": ref["docs"]}).status_code == 200
        assert web.get("/api/workspace/file/../mcp_server.py").status_code == 404
        assert web.get("/api/workspace/source", params={"path": "../MEMORY.md"}).status_code == 404
    async with Client(StdioServerParameters(command=sys.executable, args=[str(root / "mcp_server.py")])) as client:
        published = (await client.list_tools()).tools
        assert {tool.name for tool in published} == set(contract)
        result = await client.call_tool("list_modes", {})
        assert not result.is_error
        for tool in published:
            assert set(tool.input_schema.get("properties", {})) == set(contract[tool.name]["inputSchema"].get("properties", {})), tool.name
    # Reproduce a non-listening Bound socket. LISTEN-only checks miss this case.
    with socket.socket() as occupied:
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        occupied.bind(("127.0.0.1", 64324))
        assert 64324 not in list(camera_runtime.available_ports("scanner"))
    print("10 modes cover all 26 capabilities; web/MCP schemas match; Bound ports skipped")


asyncio.run(main())
