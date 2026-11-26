"""Twilight Sky Garden (空庭と未知の存在) — Modular world package in Musuhi (産霊)."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from musuhi.net import find_free_port, resolve_endpoint
from .server import create_server

WORLD_DIR = Path(__file__).parent


def run_server(host: str = "", port: Optional[int] = None, scars: bool = False) -> None:
    create_server(host=host, port=port, scars=scars).serve_forever()


def _client_cmd(side: str) -> tuple[list[str], dict[str, str]]:
    if side == "p1":
        return [sys.executable, str(WORLD_DIR / "client.py")], {"AAL_NAME": "Lantern", "AAL_ROLE": "lantern"}
    return [sys.executable, str(WORLD_DIR / "client_p2.py"), "--side", "p2", "--name", "Prism", "--role", "prism"], {}


def run_client(host: Optional[str] = None, port: Optional[int] = None, side: str = "p1") -> None:
    h, p = resolve_endpoint(host, port)
    cmd, extra_env = _client_cmd(side)
    env = os.environ.copy()
    env["AAL_LAN_HOST"] = h
    env["AAL_LAN_PORT"] = str(p)
    env.update(extra_env)
    subprocess.run(cmd, env=env, cwd=str(WORLD_DIR), check=False)


def run_solo(side: str = "p1", scars: bool = False) -> None:
    port = find_free_port("localhost")
    srv = create_server(host="localhost", port=port, scars=scars)
    srv.start()
    time.sleep(0.15)
    try:
        run_client(host="localhost", port=port, side=side)
    finally:
        srv.stop()
