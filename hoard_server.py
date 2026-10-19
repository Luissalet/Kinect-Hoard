"""Kinect Hoard's on-demand family UI and HTTP agent contract."""

import ast
import asyncio
import inspect
import json
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from typing import get_type_hints

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, create_model
from hoard_link import family
from hoard_link.copilot import install_copilot
import hoard_link
import mcp_server as toolkit

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
owned_engine = False


@asynccontextmanager
async def lifespan(app):
    yield
    if owned_engine and toolkit.live_scan_status()["state"] != "closed":
        await asyncio.to_thread(toolkit.control_live_scan, "close")


app = FastAPI(title="Kinect Hoard", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"service": "kinect-hoard", "hoard_link": family.health_block(),
            "camera_on_demand": True}


@app.get("/")
def index():
    return FileResponse(ROOT / "ui" / "scanner.html")


@app.get("/ui/hoard-theme.css")
def theme():
    return FileResponse(Path(hoard_link.__file__).parent / "ui" / "hoard-theme.css")


class ScanSettings(BaseModel):
    mode: str = "fixed"
    generation: str = "one"
    subject: str = "person"


@app.post("/api/scanner/connect")
async def connect(settings: ScanSettings):
    global owned_engine
    was_closed = toolkit.live_scan_status()["state"] == "closed"
    try:
        result = await asyncio.to_thread(toolkit._open_live_scan, settings.mode,
                                         settings.generation, settings.subject, False)
    except (ValueError, RuntimeError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc
    owned_engine = owned_engine or was_closed
    return result


@app.get("/api/scanner/status")
def status():
    return toolkit.live_scan_status()


@app.post("/api/studio/open")
def studio():
    try:
        return toolkit.open_studio()
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


class Command(BaseModel):
    action: str
    x: float = 0
    y: float = 0


@app.post("/api/scanner/control")
def control(command: Command):
    try:
        return toolkit.control_live_scan(command.action, command.x, command.y)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/scanner/{view}.png")
def preview(view: str):
    if view not in ("preview", "surface"):
        raise HTTPException(404)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:64320/api/scan/{view}.png", timeout=3) as response:
            return Response(response.read(), media_type="image/png", headers={"Cache-Control": "no-store"})
    except OSError as exc:
        raise HTTPException(503, "Vista todavía no disponible") from exc


@app.get("/api/scanner/download/{artifact}")
def download(artifact: str):
    if artifact not in ("scan.obj", "scan.mtl", "scan-albedo.png", "scan.ply", "scan.scan.json"):
        raise HTTPException(404)
    current = toolkit.live_scan_status()
    if current["state"] != "finished":
        raise HTTPException(409, "Finaliza la exportación antes de descargar")
    path = Path(current["directory"]) / artifact
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=artifact)


# Publish the very same functions and typed arguments as stdio MCP. No second
# implementation of camera/scan operations is hidden in the web application.
def install_tool(name):
    function = getattr(toolkit, name)
    hints = get_type_hints(function)
    fields = {p.name: (hints.get(p.name, str), ... if p.default is inspect.Parameter.empty else p.default)
              for p in inspect.signature(function).parameters.values()}
    model = create_model(name + "Arguments", **fields)

    async def endpoint(body):
        return await asyncio.to_thread(function, **body.model_dump())

    endpoint.__annotations__ = {"body": model}
    endpoint.__doc__ = inspect.getdoc(function)
    app.add_api_route("/api/agent/" + name, endpoint, methods=["POST"])


for definition in ast.parse((ROOT / "mcp_server.py").read_text(encoding="utf-8")).body:
    if isinstance(definition, ast.FunctionDef) and any(
        isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "tool"
        for d in definition.decorator_list
    ):
        install_tool(definition.name)

family.install_fastapi(app, "kinect-hoard", str(DATA), mcp_source=str(ROOT / "mcp_server.py"),
                       protect_tool_routes=True)
install_copilot(app, "kinect-hoard", str(DATA), app_name="Kinect Hoard")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=64321)
