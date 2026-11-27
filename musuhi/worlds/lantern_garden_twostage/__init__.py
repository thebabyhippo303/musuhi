"""Lantern Garden · Two-Stage (灯籠の庭・二段) — Modular world package in Musuhi (産霊).

The gardeners' own server, clients and guide are kept exactly as they wrote them during the run;
this module only adapts them to the Musuhi registry. By default the garden starts from the state
the gardeners' server saved at the end of their session (garden_state.json): every lantern,
bloom, plaque and the two gardeners P1 and P2. That shipped file is never written to: the
running server keeps saving to its own copy (save_path, by default under
~/.local/share/musuhi/lantern_garden_twostage/).

Sides: p1 runs host_client.py (the purple gardener, joins as P1); p2 runs client.py --side p2
(the green gardener, joins as P2).
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

from musuhi.net import find_free_port, resolve_bind_port, resolve_endpoint

WORLD_DIR = Path(__file__).parent
GARDEN = WORLD_DIR / "garden_state.json"
DEFAULT_SAVE = Path.home() / ".local" / "share" / "musuhi" / "lantern_garden_twostage" / "garden_state.json"

# server.py is the gardeners' unmodified script. Its serve() loop installs a signal handler and
# reads its port from AAL_LAN_PORT, so it runs in its own process; only STATE_FILE is pointed at
# the save copy before serve() is called.
_BOOT = (
    "import importlib.util, sys\n"
    "spec = importlib.util.spec_from_file_location('lantern_garden_twostage_server', sys.argv[1])\n"
    "mod = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(mod)\n"
    "mod.STATE_FILE = sys.argv[2]\n"
    "mod.serve()\n"
)


class _Garden:
    """start()/stop()/serve_forever() around the gardeners' selector server process."""

    def __init__(self, port: int, save_path: Path) -> None:
        self.port = port
        self.save_path = save_path
        self._proc: Optional[subprocess.Popen] = None

    def start(self) -> int:
        env = os.environ.copy()
        env["AAL_LAN_PORT"] = str(self.port)
        self._proc = subprocess.Popen(
            [sys.executable, "-u", "-c", _BOOT, str(WORLD_DIR / "server.py"), str(self.save_path)],
            env=env, cwd=str(WORLD_DIR), stdout=subprocess.PIPE, text=True,
        )
        # The server prints "Lantern Garden server listening" once its socket is bound.
        for line in self._proc.stdout:
            if "listening" in line:
                break
        else:
            raise RuntimeError("Lantern Garden server exited before listening")
        threading.Thread(target=self._drain, daemon=True).start()
        return self.port

    def _drain(self) -> None:
        for line in self._proc.stdout:
            print(line, end="", flush=True)

    def serve_forever(self) -> None:
        self.start()
        try:
            self._proc.wait()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        if self._proc is None or self._proc.poll() is not None:
            return
        self._proc.send_signal(signal.SIGTERM)  # the server saves the garden on SIGTERM
        try:
            self._proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()


def create_server(host: str = "", port: Optional[int] = None, load=GARDEN, save_path=None,
                  resume: bool = False, **_kwargs) -> _Garden:
    """The gardeners' server binds every interface; `host` is accepted for the common interface.

    load: start state copied into save_path (default: the gardeners' saved garden; None = fresh).
    resume: keep an existing save_path instead of starting again from `load`.
    """
    save = Path(save_path) if save_path else DEFAULT_SAVE
    save.parent.mkdir(parents=True, exist_ok=True)
    if not (resume and save.exists()):
        if load:
            shutil.copyfile(str(load), str(save))
        elif save.exists():
            save.unlink()
    if port is None:
        port = resolve_bind_port(None)
    elif int(port) == 0:
        port = find_free_port("")
    return _Garden(int(port), save)


def run_server(host: str = "", port: Optional[int] = None, load=GARDEN, save_path=None,
               resume: bool = False, **_kwargs) -> None:
    create_server(host=host, port=port, load=load, save_path=save_path, resume=resume).serve_forever()


def run_client(host: Optional[str] = None, port: Optional[int] = None, side: str = "p1", **_kwargs) -> None:
    h, p = resolve_endpoint(host, port)
    env = os.environ.copy()
    env["AAL_LAN_HOST"] = h
    env["AAL_LAN_PORT"] = str(p)
    if side == "p1":
        env.setdefault("AAL_PLAYER_NAME", "P1")
        cmd = [sys.executable, str(WORLD_DIR / "host_client.py")]
    else:
        cmd = [sys.executable, str(WORLD_DIR / "client.py"), "--side", "p2"]
    subprocess.run(cmd, env=env, cwd=str(WORLD_DIR), check=False)


def run_solo(side: str = "p1", **_kwargs) -> None:
    port = find_free_port("localhost")
    srv = create_server(host="localhost", port=port, **_kwargs)
    srv.start()
    try:
        run_client(host="localhost", port=port, side=side)
    finally:
        srv.stop()
