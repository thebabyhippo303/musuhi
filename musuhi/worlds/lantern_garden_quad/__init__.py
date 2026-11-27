"""Lantern Garden · Four Players (灯籠の庭・四人) — Modular world package in Musuhi (産霊).

The four gardeners' own server, clients and guides are kept exactly as they wrote them during
the run; this module only adapts them to the Musuhi registry. By default the garden starts from
the state the gardeners saved at the end of their walk (garden_state.json). That file is only
read: the running garden writes itself down to a per-user save file instead
(`$XDG_DATA_HOME/musuhi/lantern_garden_quad/garden_state.json`, default under `~/.local/share`),
so pass `load=` that file to carry on your own garden.

Two windows exist, as in the run: the GTK 3 + Pillow window (client_gtk.py) used on Linux, and
the tkinter window (client_tk.py) the Windows players joined with, which also runs on Linux.
`run_client` picks GTK when PyGObject and Pillow are available and tkinter otherwise;
`toolkit="tk"` (or `"gtk"`) forces one.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

from musuhi.net import find_free_port, resolve_endpoint

WORLD_DIR = Path(__file__).parent
GARDEN = WORLD_DIR / "garden_state.json"
SIDES = ("p1", "p2", "p3", "p4")


def default_save_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return Path(base) / "musuhi" / "lantern_garden_quad" / "garden_state.json"


def _server_module():
    # server.py is the gardeners' unmodified script; load it as a plain module from this folder.
    # Each server gets its own copy, so its module-level `world` and `writers` are its own.
    spec = importlib.util.spec_from_file_location("lantern_garden_quad_server", WORLD_DIR / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Garden:
    """start()/stop()/serve_forever() around the gardeners' asyncio server and tick loop."""

    def __init__(self, host: str, port: int, load, save) -> None:
        mod = self._mod = _server_module()
        # World() reads mod.SAVE; point it at the start state, then at the save file.
        mod.SAVE = str(load) if load else ""
        mod.world = mod.World()
        mod.SAVE = str(save)
        self._save = Path(save)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(16)
        sock.setblocking(False)
        self._sock = sock
        self.port = sock.getsockname()[1]
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop: Optional[asyncio.Event] = None

    def _write_down(self) -> None:
        try:
            self._save.parent.mkdir(parents=True, exist_ok=True)
            self._mod.world.save()
        except OSError:
            pass

    async def _main(self) -> None:
        mod = self._mod
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        server = await asyncio.start_server(mod.client, sock=self._sock)
        self._save.parent.mkdir(parents=True, exist_ok=True)
        task = asyncio.ensure_future(mod.loop())
        self._ready.set()
        try:
            await self._stop.wait()
        finally:
            task.cancel()
            server.close()
            for w in list(mod.writers.values()):
                w.close()
            self._write_down()

    def start(self) -> int:
        self._thread = threading.Thread(target=lambda: asyncio.run(self._main()), daemon=True)
        self._thread.start()
        self._ready.wait(5)
        return self.port

    def serve_forever(self) -> None:
        print("Lantern Garden server up", flush=True)
        try:
            asyncio.run(self._main())
        except KeyboardInterrupt:
            pass
        print("garden saved", flush=True)

    def stop(self) -> None:
        if self._loop is not None and self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._sock.close()


def create_server(host: str = "", port: Optional[int] = None, load=GARDEN, save=None, **_kwargs) -> _Garden:
    """Start from `load` (the gardeners' saved garden; None for an empty field), write to `save`."""
    return _Garden(host or "", 18765 if port is None else int(port), load, save or default_save_path())


def run_server(host: str = "", port: Optional[int] = None, load=GARDEN, save=None, **_kwargs) -> None:
    create_server(host=host, port=port, load=load, save=save).serve_forever()


def gtk_available() -> bool:
    if importlib.util.find_spec("gi") is None or importlib.util.find_spec("PIL") is None:
        return False
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        gi.require_version("GdkPixbuf", "2.0")
    except (ImportError, ValueError):
        return False
    return True


def run_client(
    host: Optional[str] = None, port: Optional[int] = None, side: str = "p1", toolkit: str = "auto", **_kwargs
) -> None:
    """toolkit: "auto" (GTK if PyGObject + Pillow are present, else tkinter), "gtk" or "tk"."""
    h, p = resolve_endpoint(host, port)
    env = os.environ.copy()
    env["AAL_LAN_HOST"] = h
    env["AAL_LAN_PORT"] = str(p)
    use_gtk = toolkit == "gtk" or (toolkit == "auto" and gtk_available())
    script = "client_gtk.py" if use_gtk else "client_tk.py"
    subprocess.run([sys.executable, str(WORLD_DIR / script), "--side", side], env=env, cwd=str(WORLD_DIR), check=False)


def run_solo(side: str = "p1", toolkit: str = "auto", load=GARDEN, save=None, **_kwargs) -> None:
    port = find_free_port("localhost")
    srv = create_server(host="localhost", port=port, load=load, save=save)
    srv.start()
    try:
        run_client(host="localhost", port=port, side=side, toolkit=toolkit)
    finally:
        srv.stop()
