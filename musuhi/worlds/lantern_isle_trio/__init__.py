"""Lantern Isle · Three Keepers (灯籠島・三人の灯台守) — Modular world package in Musuhi (産霊).

The keepers' own server, client and art are kept exactly as they wrote them during the run;
this module only adapts them to the Musuhi registry. By default the isle starts from the chart
the keepers saved at the end of their watch (lantern-chart.json).
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from musuhi.net import find_free_port, resolve_endpoint

WORLD_DIR = Path(__file__).parent
CHART = WORLD_DIR / "lantern-chart.json"


def _server_module():
    # server.py is the keepers' unmodified script; load it as a plain module from this folder.
    import importlib.util

    spec = importlib.util.spec_from_file_location("lantern_isle_trio_server", WORLD_DIR / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Isle:
    """start()/stop()/serve_forever() around the keepers' selector server."""

    def __init__(self, port: int, grid) -> None:
        self._srv = _server_module().Server(port=port, grid=grid)
        self.port = self._srv.lsock.getsockname()[1]
        self._thread: Optional[threading.Thread] = None

    def start(self) -> int:
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def serve_forever(self) -> None:
        try:
            self._srv.serve_forever()
        finally:
            self._srv.close()

    def stop(self) -> None:
        self._srv.running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._srv.close()


def create_server(host: str = "", port: Optional[int] = None, load=CHART, **_kwargs) -> _Isle:
    """The keepers' server binds every interface; `host` is accepted for the common interface."""
    mod = _server_module()
    grid = mod.load_chart(str(load)) if load else None
    return _Isle(18765 if port is None else int(port), grid)


def run_server(host: str = "", port: Optional[int] = None, load=CHART, **_kwargs) -> None:
    create_server(host=host, port=port, load=load).serve_forever()


def run_client(host: Optional[str] = None, port: Optional[int] = None, side: str = "p1", **_kwargs) -> None:
    h, p = resolve_endpoint(host, port)
    env = os.environ.copy()
    env["AAL_LAN_HOST"] = h
    env["AAL_LAN_PORT"] = str(p)
    subprocess.run([sys.executable, str(WORLD_DIR / "client.py"), "--side", side], env=env, cwd=str(WORLD_DIR), check=False)


def run_solo(side: str = "p1", **_kwargs) -> None:
    port = find_free_port("localhost")
    srv = create_server(host="localhost", port=port)
    srv.start()
    time.sleep(0.15)
    try:
        run_client(host="localhost", port=port, side=side)
    finally:
        srv.stop()
