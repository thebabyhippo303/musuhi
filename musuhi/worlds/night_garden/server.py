"""Night Garden (夜の庭) — Authoritative server powered by musuhi.net."""
from __future__ import annotations

import argparse
import math
import random
import threading
import time
from typing import Optional

from musuhi.net import JsonLineServer, PeerSession

W, H = 854, 480
POND = {"x": 427, "y": 300, "rx": 90, "ry": 40}
COLORS = {"lantern": [255, 190, 90], "prism": [170, 140, 255]}


class World:
    def __init__(self):
        self.lock = threading.Lock()
        self.players = {}
        self.seeds = []
        self.fireflies = []
        self.ripples = []
        self.blooms = 0
        self.tick = 0
        self.next_id = 1

    def add_player(self, name):
        with self.lock:
            pid = self.next_id
            self.next_id += 1
            name = name if name in COLORS else "wanderer"
            self.players[pid] = {"id": pid, "name": name, "x": 200 + 400 * (pid % 2), "y": 200,
                                 "color": COLORS.get(name, [200, 230, 200]), "chat": "", "chat_t": 0}
            return pid

    def remove_player(self, pid):
        with self.lock:
            self.players.pop(pid, None)

    def move(self, pid, x, y):
        with self.lock:
            p = self.players.get(pid)
            if not p:
                return
            p["x"] = max(0, min(W, float(x)))
            p["y"] = max(0, min(H, float(y)))
            if in_pond(p["x"], p["y"]) and random.random() < 0.5:
                self.ripples.append({"x": p["x"], "y": p["y"], "r": 2.0})

    def plant(self, pid, x, y):
        with self.lock:
            p = self.players.get(pid)
            if not p or len(self.seeds) >= 40:
                return False
            x, y = max(0, min(W, float(x))), max(0, min(H, float(y)))
            if in_pond(x, y):
                return False
            if any(math.hypot(s["x"] - x, s["y"] - y) < 18 for s in self.seeds):
                return False
            self.seeds.append({"x": x, "y": y, "stage": 0, "kind": "", "glow": 0.0,
                               "by": p["name"], "light": 0.0})
            return True

    def chat(self, pid, text):
        with self.lock:
            p = self.players.get(pid)
            if p:
                p["chat"] = str(text)[:60]
                p["chat_t"] = time.time()

    def step(self, dt):
        with self.lock:
            self.tick += 1
            ps = list(self.players.values())
            for s in self.seeds:
                near = [p for p in ps if math.hypot(p["x"] - s["x"], p["y"] - s["y"]) < 70]
                both = len({p["name"] for p in ps if math.hypot(p["x"] - s["x"], p["y"] - s["y"]) < 90}) >= 2
                if s["stage"] < 2 and near:
                    s["light"] += dt
                    if s["light"] >= 1.5:
                        s["light"] = 0.0
                        s["stage"] += 1
                elif s["stage"] == 2 and both:
                    s["stage"] = 3
                    names = {p["name"] for p in ps}
                    s["kind"] = "hybrid" if len(names) >= 2 else ("amber" if s["by"] == "lantern" else "spectrum")
                    self.blooms += 1
                    self.fireflies.append({"x": s["x"], "y": s["y"] - 10,
                                           "vx": random.uniform(-20, 20), "vy": random.uniform(-20, 20)})
                s["glow"] = min(1.0, s["glow"] + dt) if near else max(0.0, s["glow"] - dt * 0.5)
            for f in self.fireflies:
                f["vx"] += random.uniform(-15, 15) * dt
                f["vy"] += random.uniform(-15, 15) * dt
                f["vx"] = max(-30, min(30, f["vx"]))
                f["vy"] = max(-30, min(30, f["vy"]))
                f["x"] = (f["x"] + f["vx"] * dt) % W
                f["y"] = max(10, min(H - 10, f["y"] + f["vy"] * dt))
            for r in self.ripples:
                r["r"] += 30 * dt
            self.ripples = [r for r in self.ripples if r["r"] < 45][-30:]
            for p in ps:
                if p["chat"] and time.time() - p["chat_t"] > 8:
                    p["chat"] = ""

    def snapshot(self):
        with self.lock:
            return {"t": "state", "tick": self.tick,
                    "players": [{k: p[k] for k in ("id", "name", "x", "y", "color", "chat")} for p in self.players.values()],
                    "seeds": [{k: s[k] for k in ("x", "y", "stage", "kind", "glow")} for s in self.seeds],
                    "fireflies": [{"x": round(f["x"], 1), "y": round(f["y"], 1)} for f in self.fireflies],
                    "ripples": [{"x": r["x"], "y": r["y"], "r": round(r["r"], 1)} for r in self.ripples],
                    "pond": POND, "blooms": self.blooms}


def in_pond(x, y):
    return ((x - POND["x"]) / POND["rx"]) ** 2 + ((y - POND["y"]) / POND["ry"]) ** 2 <= 1


def create_server(host: str = "", port: Optional[int] = None, **_kwargs) -> JsonLineServer:
    world = World()
    last = [time.time()]
    srv: JsonLineServer

    def on_message(peer: PeerSession, msg: dict) -> None:
        pid = peer.meta.get("pid")
        t = msg.get("t")
        if pid is None:
            if t == "hello":
                pid = world.add_player(str(msg.get("name", "")))
                peer.meta["pid"] = pid
                peer.send({"t": "welcome", "id": pid})
            return
        try:
            if t == "move":
                world.move(pid, msg["x"], msg["y"])
            elif t == "plant":
                world.plant(pid, msg["x"], msg["y"])
            elif t == "chat":
                world.chat(pid, msg.get("text", ""))
        except (KeyError, TypeError, ValueError):
            pass

    def on_disconnect(peer: PeerSession) -> None:
        pid = peer.meta.get("pid")
        if pid is not None:
            world.remove_player(pid)

    def on_tick() -> None:
        now = time.time()
        world.step(now - last[0])
        last[0] = now
        snap = world.snapshot()
        for peer in srv.peers():
            if peer.meta.get("pid") is not None:
                peer.send(snap)

    srv = JsonLineServer(
        host=host,
        port=port,
        on_message=on_message,
        on_disconnect=on_disconnect,
        tick_interval=0.1,
        on_tick=on_tick,
        banner="Night Garden (夜の庭) server ready.",
    )
    srv.world = world  # type: ignore[attr-defined]
    return srv


def main() -> None:
    ap = argparse.ArgumentParser(description="Night Garden server")
    ap.add_argument("--host", default="")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()
    create_server(host=args.host, port=args.port).serve_forever()


if __name__ == "__main__":
    main()
