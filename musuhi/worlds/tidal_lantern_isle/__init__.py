"""Tidal Lantern Isle (潮灯の島) — Modular world package in Musuhi (産霊).

The keepers' own server, client, atlas art and tests are kept exactly as they wrote them during
the run; this module only adapts them to the Musuhi registry. By default the isle starts from the
world the keepers saved at the end of their watch (world_save.json): their channels, reeds, lamps,
waypost signs and pockets. That file is only read; autosaves go to `save_path` when one is given,
and nowhere otherwise.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from musuhi.net import find_free_port, resolve_bind_port, resolve_endpoint

WORLD_DIR = Path(__file__).parent
WORLD_SAVE = WORLD_DIR / "world_save.json"


def _server_module():
    # server.py is the keepers' unmodified script; load it as a plain module from this folder.
    import importlib.util

    spec = importlib.util.spec_from_file_location("tidal_lantern_isle_server", WORLD_DIR / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Isle:
    """start()/stop()/serve_forever() around the keepers' asyncio server, on its own event loop."""

    def __init__(self, host: str, port: int, load=WORLD_SAVE, save_path=None) -> None:
        self._srv = _server_module().Server()  # no save path yet: never writes to this folder
        source = save_path if save_path and os.path.exists(save_path) else load
        if source:
            with open(source, encoding="utf-8") as f:
                self._srv.world.load_save(json.load(f))
        self._srv.save_path = str(save_path) if save_path else None
        self._loop = asyncio.new_event_loop()
        self._aserver = self._loop.run_until_complete(asyncio.start_server(self._srv.on_client, host, port))
        self.port = self._aserver.sockets[0].getsockname()[1]
        self._tick = self._loop.create_task(self._srv.ticker())
        self._thread: Optional[threading.Thread] = None
        self._closed = False

    async def _shutdown(self) -> None:
        self._tick.cancel()
        self._srv.save()
        self._aserver.close()
        for w in list(self._srv.writers.values()):
            w.close()
        others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for t in others:
            t.cancel()
        await asyncio.gather(*others, return_exceptions=True)

    def start(self) -> int:
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        return self.port

    def serve_forever(self) -> None:
        print("Tidal Lantern Isle server listening (LAN ready)", flush=True)
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                self._loop.add_signal_handler(sig, self._loop.stop)
            except (NotImplementedError, RuntimeError):
                pass
        try:
            self._loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._close()
            print("world saved; server stopped", flush=True)

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loop.run_until_complete(self._shutdown())
        self._loop.close()

    def stop(self) -> None:
        if self._thread is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=2)
            self._thread = None
        self._close()


def create_server(host: str = "", port: Optional[int] = None, load=WORLD_SAVE, save_path=None, **_kwargs) -> _Isle:
    """Bind like the keepers' server (every interface on AAL_LAN_PORT or 18765 by default).

    load: start state (the keepers' world_save.json; None for a fresh isle).
    save_path: where to autosave every 5 s and on shutdown; resumes from it if it already exists.
    """
    return _Isle(host, resolve_bind_port(port), load=load, save_path=save_path)


def run_server(host: str = "", port: Optional[int] = None, load=WORLD_SAVE, save_path=None, **_kwargs) -> None:
    create_server(host=host, port=port, load=load, save_path=save_path).serve_forever()


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
