"""Process-shared native endpoints. A fixed port can be occupied by an outbound socket."""
import json
import os
import socket
import subprocess
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


@contextmanager
def lifecycle():
    import msvcrt
    DATA.mkdir(exist_ok=True)
    with (DATA / "camera.lock").open("a+b") as handle:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b"0"); handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def endpoint(kind):
    try:
        return json.loads((DATA / (kind + "-endpoint.json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"port": 64320 if kind == "scanner" else 64323}


def request(kind, path, post=False, timeout=2):
    url = f"http://127.0.0.1:{endpoint(kind)['port']}/{path}"
    req = urllib.request.Request(url, data=b"" if post else None, method="POST" if post else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def available_ports(kind):
    candidates = (64320, 64322, 64324, 64325) if kind == "scanner" else (64323, 64324, 64325, 64322)
    for port in candidates:
        with socket.socket() as sock:
            # Include outbound Bound/CloseWait sockets, not just LISTEN.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
        yield port


def launch(kind, command, health_path, executable, seconds=75):
    DATA.mkdir(exist_ok=True)
    errors = []
    for port in available_ports(kind):
        log = DATA / (kind + "-worker.log")
        with log.open("w", encoding="utf-8") as output:
            process = subprocess.Popen(command(port), cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
        state = {"port": port, "pid": process.pid, "executable": str(executable)}
        temporary = DATA / f"{kind}-endpoint.{os.getpid()}.tmp"
        temporary.write_text(json.dumps(state), encoding="utf-8")
        temporary.replace(DATA / (kind + "-endpoint.json"))
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                detail = log.read_text(encoding="utf-8", errors="replace").strip()
                errors.append(detail or f"Proceso terminado con código {process.returncode}")
                break
            try:
                result = request(kind, health_path, timeout=.5)
                if kind == "camera" and result.get("service") != "kinect-hoard-camera":
                    raise OSError("Respuesta de otra aplicación")
                return {**result, "process_id": process.pid, "port": port}
            except (OSError, ValueError):
                time.sleep(.1)
        else:
            process.terminate(); process.wait(timeout=8)
            raise TimeoutError(f"No abrió el motor {kind}. Consulta {log}")
        # Retry binding conflicts only; driver/model errors need their actual message.
        if "Servidor local:" not in errors[-1]:
            break
    raise RuntimeError("No se pudo abrir " + kind + ": " + "\n".join(errors)[-1800:] + f". Registro: {DATA / (kind + '-worker.log')}")


def stop(kind):
    try:
        current = request(kind, "api/scan/status" if kind == "scanner" else "api/health", timeout=.3)
        if kind == "scanner" and current.get("format") != "KINECT_HOARD_LIVE_SCAN_1":
            return {"closed": True}
        if kind == "camera" and current.get("service") != "kinect-hoard-camera":
            return {"closed": True}
        request(kind, "api/scan/close" if kind == "scanner" else "api/stop", True)
    except OSError:
        return {"closed": True}
    for _ in range(100):
        try:
            request(kind, "api/health", timeout=.2)
        except OSError:
            return {"closed": True}
        time.sleep(.1)
    raise RuntimeError("El motor aún está cerrando; conserva la sesión antes de cambiar de sensor")
