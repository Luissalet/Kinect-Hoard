"""Own the live scanner process and its cooperative GPU reservation."""

import subprocess
import sys
from hoard_link.lease import Lease
from mcp_server import ROOT, _exe


def main():
    if sys.argv[1] == "replay":
        # replay SESSION TRACKER SPEED PORT DIRECTORY: a saved take through the live engine.
        session, tracker, speed, port, directory = sys.argv[2:7]
        command = [str(_exe()), "--scanner-replay-server", session, tracker, speed, port, directory]
        purpose = "RGBD scan Fusion replay"
    else:
        mode, generation, subject, window, *port = sys.argv[1:]
        command = [str(_exe()), "--scanner" if window == "window" else "--scanner-server", mode, generation, subject, *port]
        purpose = "RGBD scan Fusion"
    # Preview and fusion share one process. Reserve before starting it, retain
    # while that process lives, and release even when its window is closed.
    with Lease(vram_mb=2048, gpu=0, owner="kinect-hoard", purpose=purpose,
               timeout_s=60, autostart=False):
        process = subprocess.Popen(command, cwd=ROOT, stdout=sys.stdout, stderr=sys.stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
