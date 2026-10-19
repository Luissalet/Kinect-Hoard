"""Kinect Hoard's on-demand family UI and HTTP agent contract."""

import ast
import asyncio
import inspect
import json
import urllib.request
import concurrent.futures
import uuid
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
owned_camera = False


@asynccontextmanager
async def lifespan(app):
    yield
    if owned_engine and toolkit.live_scan_status()["state"] != "closed":
        await asyncio.to_thread(toolkit.control_live_scan, "close")
    if owned_camera:
        await asyncio.to_thread(toolkit.close_camera)


app = FastAPI(title="Kinect Hoard", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"service": "kinect-hoard", "hoard_link": family.health_block(),
            "camera_on_demand": True}


@app.get("/")
def index():
    return FileResponse(ROOT / "ui" / "workspace.html")


@app.get("/scanner")
def scanner_page():
    return FileResponse(ROOT / "ui" / "scanner.html")


@app.get("/app-icon.svg")
def logo():
    return FileResponse(ROOT / "app-icon.svg")


@app.get("/ui/{asset}")
def ui_asset(asset: str):
    if asset == "hoard-theme.css":
        return FileResponse(Path(hoard_link.__file__).parent / "ui" / "hoard-theme.css")
    if asset not in ("workspace.js", "workspace.css"):
        raise HTTPException(404)
    return FileResponse(ROOT / "ui" / asset)


@app.get("/api/workspace/modes")
def modes():
    return toolkit.list_modes()


@app.get("/api/camera/status")
def camera_status():
    return toolkit.camera_status()


@app.get("/api/camera/frame")
def camera_frame():
    try:
        return toolkit.get_live_frame()
    except OSError as exc:
        raise HTTPException(503, "Conecta el flujo Esqueleto para recibir articulaciones") from exc


@app.get("/api/camera/{view}")
def camera_image(view: str):
    if view not in ("frame.png", "avatar.png", "frame.raw", "rgbd"):
        raise HTTPException(404)
    endpoint = "api/rgbd" if view == "rgbd" else view
    port = toolkit.runtime.endpoint("camera")["port"]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/{endpoint}", timeout=2) as response:
            return Response(response.read(), media_type="image/png" if view.endswith(".png") else "application/octet-stream", headers={"Cache-Control": "no-store"})
    except OSError as exc:
        raise HTTPException(503, "El lector todavía no ha entregado este flujo") from exc


@app.get("/camera-output")
def clean_output():
    return Response('''<!doctype html><html lang="es"><meta charset="utf-8"><title>Kinect Hoard · Salida de cámara</title><style>html,body{margin:0;background:transparent;width:100%;height:100%;overflow:hidden}img{width:100%;height:100%;object-fit:contain}</style><img id="video" alt="Salida Kinect"><script>const image=document.getElementById('video');function frame(){image.src='/api/camera/frame.png?t='+Date.now()}image.onload=()=>setTimeout(frame,70);image.onerror=()=>setTimeout(frame,500);frame()</script></html>''', media_type="text/html")


@app.get("/api/workspace/source")
def source(path: str):
    try:
        if path in ("integrations/blender_kinect.py", "examples/opencv_live.py", "examples/opencv_raw.py", "examples/matlab_live.m", "examples/matlab_depth.m"):
            return Response((ROOT / path).read_text(encoding="utf-8"), media_type="text/plain")
        return Response(toolkit.read_hoard_source(path), media_type="text/plain")
    except (ValueError, OSError) as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/workspace/file/{filename:path}")
def artifact(filename: str):
    path = (toolkit.CAPTURE_DIR / filename).resolve()
    if not path.is_relative_to(toolkit.CAPTURE_DIR.resolve()) or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


jobs = {}
executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
tool_functions = {}


class ToolCommand(BaseModel):
    tool: str
    arguments: dict = {}


@app.post("/api/workspace/run")
def run_tool(command: ToolCommand):
    if command.tool not in tool_functions:
        raise HTTPException(404, "Herramienta desconocida")
    function, model = tool_functions[command.tool]
    try:
        arguments = model(**command.arguments).model_dump()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    job_id = uuid.uuid4().hex
    job = {"id": job_id, "tool": command.tool, "state": "queued"}
    jobs[job_id] = job
    def execute():
        global owned_camera
        job["state"] = "running"
        try:
            job["result"] = function(**arguments)
            if command.tool in ("start_camera", "connect_blender"):
                owned_camera = True
            job["state"] = "finished"
        except Exception as exc:
            job.update(state="error", error=str(exc))
    executor.submit(execute)
    return job


@app.get("/api/workspace/jobs")
def job_status():
    return list(jobs.values())


@app.get("/api/workspace/files")
def files():
    return toolkit.list_artifacts()


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
    was_closed = (await asyncio.to_thread(toolkit.live_scan_status))["state"] == "closed"
    try:
        result = await asyncio.to_thread(toolkit._open_live_scan, settings.mode,
                                         settings.generation, settings.subject, False)
    except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
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
        port = toolkit.runtime.endpoint("scanner")["port"]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/scan/{view}.png", timeout=3) as response:
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
    tool_functions[name] = (function, model)

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
