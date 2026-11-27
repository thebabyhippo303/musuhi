"""Tidal Atlas (潮の地図帳) — Modular world package in Musuhi (産霊).

The keepers' own server, clients, guides and plates are kept exactly as they wrote them during the
run; this module only adapts them to the Musuhi registry. The keepers kept no saved state: their
world lives in memory, so every start is a fresh, dark island with the same coastline (their
README: "restarting the server starts a new, dark island").

Two sheets: Teal (side p1, the host's keeper) used client_p1_fallback.py; Amber (side p2) used
client.py --side p2.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from musuhi.net import find_free_port, resolve_endpoint

WORLD_DIR = Path(__file__).parent


def _server_module():
    # server.py is the keepers' unmodified script; load it as a plain module from this folder.
    import importlib.util

    spec = importlib.util.spec_from_file_location("tidal_atlas_server", WORLD_DIR / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Atlas:
    """start()/stop()/serve_forever() around the keepers' asyncio server, on its own event loop."""

    def __init__(self, port: int) -> None:
        self._loop = asyncio.new_event_loop()
        self._game = _server_module().Server()
        self._srv = self._loop.run_until_complete(self._game.start(port))
        self.port = self._srv.sockets[0].getsockname()[1]
        self._thread: Optional[threading.Thread] = None

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            self._srv.close()
            tasks = asyncio.all_tasks(self._loop)
            for t in tasks:
                t.cancel()
            self._loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            self._loop.close()

    def start(self) -> int:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self.port

    def serve_forever(self) -> None:
        try:
            self._run()
        except KeyboardInterrupt:
            pass

    def stop(self) -> None:
        if self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=2)


def create_server(host: str = "", port: Optional[int] = None, **_kwargs) -> _Atlas:
    """The keepers' server binds every interface; `host` is accepted for the common interface.

    Port 0 is resolved to one free port first: asyncio would otherwise give the IPv4 and IPv6
    sockets two different ephemeral ports.
    """
    port = 18765 if port is None else int(port)
    return _Atlas(port or find_free_port(""))


def run_server(host: str = "", port: Optional[int] = None, **_kwargs) -> None:
    create_server(host=host, port=port).serve_forever()


def run_client(host: Optional[str] = None, port: Optional[int] = None, side: str = "p1", **_kwargs) -> None:
    h, p = resolve_endpoint(host, port)
    env = os.environ.copy()
    env["AAL_LAN_HOST"] = h
    env["AAL_LAN_PORT"] = str(p)
    if side == "p2":
        cmd = [sys.executable, str(WORLD_DIR / "client.py"), "--side", "p2"]  # Amber's sheet
    else:
        cmd = [sys.executable, str(WORLD_DIR / "client_p1_fallback.py"), "Teal", "teal"]  # Teal's sheet
    subprocess.run(cmd, env=env, cwd=str(WORLD_DIR), check=False)


def run_solo(side: str = "p1", **_kwargs) -> None:
    port = find_free_port("localhost")
    srv = create_server(host="localhost", port=port)
    srv.start()
    time.sleep(0.15)
    try:
        run_client(host="localhost", port=port, side=side)
    finally:
        srv.stop()
