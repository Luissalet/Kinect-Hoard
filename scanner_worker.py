"""Own the live scanner process and its cooperative GPU reservation."""

import subprocess
import sys
from hoard_link.lease import Lease
from mcp_server import ROOT, _exe


def main():
    mode, generation, subject, window = sys.argv[1:]
    # Preview and fusion share one process. Reserve before starting it, retain
    # while that process lives, and release even when its window is closed.
    with Lease(vram_mb=2048, gpu=0, owner="kinect-hoard", purpose="RGBD scan Fusion",
               timeout_s=60, autostart=False):
        process = subprocess.Popen([str(_exe()), "--scanner" if window == "window" else "--scanner-server",
                                    mode, generation, subject], cwd=ROOT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
