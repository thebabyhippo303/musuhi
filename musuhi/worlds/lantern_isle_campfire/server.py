#!/usr/bin/env python3
"""Lantern Isle (灯籠島・焚き火) — authoritative world server (see PROTOCOL.md), powered by musuhi.net."""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import threading
import time
from typing import Optional

from musuhi.net import JsonLineServer, PeerSession

COLS, ROWS = 26, 13
GOAL = 20
MAP = [
    "~~~~~~~~~~~~~~~~~~~~~~~~~~",
    "~~~~~....~~~~~~~~...~~~~~~",
    "~~~...,,,,F.~~~~..,,,..~~~",
    "~~..,,,T,,,,......,,T,,.~~",
    "~..,,T,,,^^,,,,,,,,,,,,..~",
    "~.,,,,,,,^,,,T,,,,,^^,,,.~",
    "~L,,T,,,,,,,,,,,,,,,,T,,.~",
    "~..,,,,,,,,T,,,,^,,,,,,..~",
    "~~.,,^,,,,,,,,,,,,,T,,,.~~",
    "~~..,,,,T,,,,..,,,,,,,..~~",
    "~~~...,,,,,...~~..,,,..~~~",
    "~~~~~.....~~~~~~~~...~~~~~",
    "~~~~~~~D~~~~~~~~~~~~~~~~~~",
]
PHASES = ["night", "aurora", "night", "dawn"]  # each lasts 40 s
COLORS = ["#ffb347", "#7ec8ff", "#c38bff", "#7dff9a", "#ff7eb6"]
SPAWNS = [(6, 6), (19, 6), (12, 9), (14, 3)]


def walkable(x, y):
    return 0 <= x < COLS and 0 <= y < ROWS and MAP[y][x] not in "~^LF"


class World:
    def __init__(self, seed=None):
        self.lock = threading.Lock()
        self.rng = random.Random(seed)
        self.players = {}
        self.lanterns = {}  # (x,y) -> owner id
        self.shells = set()
        self.chat = []
        self.tick = 0
        self.next_id = 1
        self.boats = []
        self.fireflies = []
        self.bursts = []
        self.star = None
        self.next_star = time.time() + 5
        for _ in range(8):
            self.spawn_firefly()
        for _ in range(14):
            self.spawn_shell()

    def free(self, x, y):
        return (walkable(x, y) and (x, y) not in self.lanterns
                and (x, y) not in self.shells
                and not any((p["x"], p["y"]) == (x, y) for p in self.players.values()))

    def spawn_shell(self):
        for _ in range(200):
            x, y = self.rng.randrange(COLS), self.rng.randrange(ROWS)
            if self.free(x, y):
                self.shells.add((x, y))
                return

    def spawn_firefly(self):
        for _ in range(100):
            x, y = self.rng.randrange(COLS), self.rng.randrange(ROWS)
            if walkable(x, y):
                a = self.rng.uniform(0, 2 * math.pi)
                self.fireflies.append({"x": float(x), "y": float(y), "a": a})
                return

    def catch_fireflies(self):
        for p in self.players.values():
            for f in list(self.fireflies):
                if math.hypot(f["x"] - p["x"], f["y"] - p["y"]) < 0.75:
                    self.fireflies.remove(f)
                    p["jar"] += 1
                    self.spawn_firefly()

    def add_player(self, name):
        with self.lock:
            pid = self.next_id
            self.next_id += 1
            sx, sy = SPAWNS[(pid - 1) % len(SPAWNS)]
            self.players[pid] = {"id": pid, "name": str(name)[:16] or f"P{pid}",
                                 "x": sx, "y": sy, "color": COLORS[(pid - 1) % len(COLORS)],
                                 "shells": 1, "jar": 0, "emote": None, "emote_until": 0}
            self.say_sys(f"{self.players[pid]['name']} washed ashore")
            return pid

    def remove_player(self, pid):
        with self.lock:
            p = self.players.pop(pid, None)
            if p:
                self.say_sys(f"{p['name']} sailed away")

    def say_sys(self, text):
        self.chat.append({"name": "*", "text": text})
        self.chat = self.chat[-6:]

    def handle(self, pid, msg):
        with self.lock:
            p = self.players.get(pid)
            if not p:
                return
            t = msg.get("t")
            if t == "move":
                dx = max(-1, min(1, int(msg.get("dx", 0))))
                dy = max(-1, min(1, int(msg.get("dy", 0))))
                nx, ny = p["x"] + dx, p["y"] + dy
                if walkable(nx, ny):  # lanterns no longer block walking (v3)
                    p["x"], p["y"] = nx, ny
                    if (nx, ny) in self.shells:  # auto-collect shells on walk
                        self.shells.discard((nx, ny))
                        p["shells"] += 1
                        self.spawn_shell()
                    self.catch_fireflies()
            elif t == "release":
                if p["jar"] > 0:
                    self.bursts.append({"x": p["x"], "y": p["y"], "n": p["jar"], "born": time.time()})
                    self.chat.append({"name": p["name"], "text": f"released {p['jar']} fireflies!"})
                    self.chat = self.chat[-6:]
                    p["jar"] = 0
            elif t == "act":
                pos = (p["x"], p["y"])
                # shells/lanterns may be on own tile or the faced neighbours; use own tile + adjacent
                if pos in self.shells:
                    self.shells.discard(pos)
                    p["shells"] += 1
                    self.spawn_shell()
                    return
                if p["shells"] > 0:
                    for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                        q = (p["x"] + dx, p["y"] + dy)
                        if self.free(*q):
                            was = len(self.lanterns)
                            self.lanterns[q] = pid
                            p["shells"] -= 1
                            if was < GOAL <= len(self.lanterns):
                                self.say_sys("The whole isle glows! Fireflies everywhere!")
                            return
                for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                    q = (p["x"] + dx, p["y"] + dy)
                    if self.lanterns.get(q) == pid:
                        del self.lanterns[q]
                        p["shells"] += 1
                        return
            elif t == "say":
                text = str(msg.get("text", ""))[:60].strip()
                if text:
                    self.chat.append({"name": p["name"], "text": text})
                    self.chat = self.chat[-6:]
            elif t == "wish":
                text = str(msg.get("text", ""))[:40].strip() or "a wish"
                spot = None
                for r in (1, 2, 3):
                    for dy in range(-r, r + 1):
                        for dx in range(-r, r + 1):
                            x, y = p["x"] + dx, p["y"] + dy
                            if 0 <= x < COLS and 0 <= y < ROWS and MAP[y][x] == "~" and spot is None:
                                spot = (x, y)
                    if spot:
                        break
                if spot is None:
                    return
                vx, vy = spot[0] - 12.5, spot[1] - 6
                n = math.hypot(vx, vy) or 1
                self.boats.append({"x": float(spot[0]), "y": float(spot[1]), "vx": vx / n * 0.04,
                                   "vy": vy / n * 0.04, "text": text, "owner": pid})
                self.boats = self.boats[-12:]
                self.chat.append({"name": p["name"], "text": f"~ wished: {text}"})
                self.chat = self.chat[-6:]
            elif t == "emote":
                e = msg.get("e")
                if e in ("wave", "heart", "dance"):
                    p["emote"] = e
                    p["emote_until"] = time.time() + 3

    def snapshot(self):
        with self.lock:
            self.tick += 1
            now = time.time()
            players = []
            for p in self.players.values():
                if p["emote"] and now > p["emote_until"]:
                    p["emote"] = None
                players.append({k: p[k] for k in ("id", "name", "x", "y", "color", "shells", "jar", "emote")})
            for b in self.boats:
                b["x"] += b["vx"]
                b["y"] += b["vy"]
            for f in self.fireflies:
                f["a"] += self.rng.uniform(-0.5, 0.5)
                nx = f["x"] + math.cos(f["a"]) * 0.06
                ny = f["y"] + math.sin(f["a"]) * 0.06
                if 1 <= nx <= COLS - 2 and 1 <= ny <= ROWS - 2:
                    f["x"], f["y"] = nx, ny
                else:
                    f["a"] += math.pi
            self.catch_fireflies()
            if now >= self.next_star:
                x0 = self.rng.uniform(0, COLS)
                self.star = {"x0": round(x0, 2), "y0": -0.5, "x1": round(x0 + self.rng.uniform(-8, 8), 2),
                             "y1": round(self.rng.uniform(3, 9), 2), "born": now}
                self.next_star = now + self.rng.uniform(8, 16)
            if self.star and now - self.star["born"] > 1.5:
                self.star = None
            self.bursts = [b for b in self.bursts if now - b["born"] < 3]
            self.boats = [b for b in self.boats if -2 < b["x"] < COLS + 1 and -2 < b["y"] < ROWS + 1]
            owners = self.lanterns
            return {"t": "state", "tick": self.tick, "players": players,
                    "lanterns": [{"x": x, "y": y, "owner": o} for (x, y), o in owners.items()],
                    "shells": [{"x": x, "y": y} for x, y in sorted(self.shells)],
                    "boats": [{"x": round(b["x"], 2), "y": round(b["y"], 2), "text": b["text"],
                               "owner": b["owner"]} for b in self.boats],
                    "fireflies": [{"x": round(f["x"], 2), "y": round(f["y"], 2)} for f in self.fireflies],
                    "bursts": [{"x": b["x"], "y": b["y"], "n": b["n"], "age": round(now - b["born"], 2)}
                               for b in self.bursts],
                    "chat": list(self.chat), "lit": len(owners), "goal": GOAL,
                    "star": (dict(self.star, age=round(now - self.star["born"], 2)) if self.star else None),
                    "beacon": round((now * 0.8) % (2 * math.pi), 3),
                    "phase": PHASES[int(now // 40) % len(PHASES)]}


SAVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_save.json")


def save_world(world, path=SAVE):
    with world.lock:
        data = {"lanterns": [[x, y] for (x, y) in world.lanterns]}
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def load_world(world, path=SAVE):
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    for x, y in data.get("lanterns", []):
        if walkable(x, y):
            world.lanterns[(x, y)] = 0  # restored lanterns belong to the whole isle
            world.shells.discard((x, y))


def create_server(host: str = "", port: Optional[int] = None, save_path=SAVE, seed=None, **_kwargs) -> JsonLineServer:
    world = World(seed)
    save = str(save_path) if save_path is not None else None
    if save:
        load_world(world, save)
    srv: JsonLineServer

    def on_message(peer: PeerSession, msg: dict) -> None:
        pid = peer.meta.get("pid")
        if pid is None:
            if msg.get("t") == "hello":
                pid = world.add_player(msg.get("name", ""))
                peer.meta["pid"] = pid
                peer.send({"t": "welcome", "id": pid, "cols": COLS, "rows": ROWS, "map": MAP})
                print(f"player {pid} joined", flush=True)
        else:
            try:
                world.handle(pid, msg)
            except (ValueError, TypeError):
                pass

    def on_disconnect(peer: PeerSession) -> None:
        pid = peer.meta.get("pid")
        if pid is not None:
            world.remove_player(pid)
            print(f"player {pid} left", flush=True)

    def on_tick() -> None:
        snap = world.snapshot()
        for peer in srv.peers():
            if peer.meta.get("pid") is not None and not peer.send(snap):
                peer.close()
        if snap["tick"] % 50 == 0 and save:
            try:
                save_world(world, save)
            except OSError:
                pass

    srv = JsonLineServer(
        host=host,
        port=port,
        on_message=on_message,
        on_disconnect=on_disconnect,
        tick_interval=0.1,
        on_tick=on_tick,
        banner="Lantern Isle (灯籠島・焚き火) server ready.",
    )
    srv.world = world  # type: ignore[attr-defined]
    return srv


def main() -> None:
    ap = argparse.ArgumentParser(description="Lantern Isle (Campfire) server")
    ap.add_argument("--host", default="")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--save", default=SAVE, help="Lantern save file (default: world_save.json beside this file)")
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()
    create_server(host=args.host, port=args.port, save_path=None if args.no_save else args.save).serve_forever()


if __name__ == "__main__":
    main()
