#!/usr/bin/env python3
"""Twilight Sky-Garden (記憶石の庭) — Authoritative server powered by musuhi.net."""
from __future__ import annotations

import argparse
import json, math, os, random, threading, time
from pathlib import Path
from typing import Optional

from musuhi.net import JsonLineServer, PeerSession

COLS, ROWS = 20, 10
STARS = [(2, 1), (6, 2), (10, 1), (14, 2), (18, 1), (4, 6), (9, 8), (15, 7), (17, 5), (1, 8)]


class World:
    def __init__(self, save=None):
        self.lock = threading.Lock()
        self.players = {}
        self.flora = {}
        self.stars = [{"x": x, "y": y, "lit": False} for x, y in STARS]
        self.links = []
        self.last_star = None
        self.chimes = []
        self.tick = 0
        self.next_id = 1
        self.fireflies = []
        self.stones = []
        self.harmonies = []
        self.last_chime = {}
        self.save_path = save
        if save:
            self.load(save)

    def load(self, path="garden_save.json"):
        if not os.path.exists(path):
            return
        with open(path) as fh:
            snap = json.load(fh)
        self.flora = {(f["x"], f["y"]): f["stage"] for f in snap.get("flora", [])}
        for st, saved in zip(self.stars, snap.get("stars", [])):
            st["lit"] = saved["lit"]
        self.links = [list(l) for l in snap.get("links", [])]
        self.stones = list(snap.get("stones", []))

    def add_player(self):
        with self.lock:
            pid = self.next_id
            self.next_id += 1
            self.players[pid] = {"id": pid, "name": "Wanderer", "avatar": "lantern",
                                 "x": (3 + 3 * pid) % COLS, "y": 4, "say": "", "say_t": 0}
            return pid

    def remove_player(self, pid):
        with self.lock:
            self.players.pop(pid, None)

    def handle(self, pid, msg):
        with self.lock:
            p = self.players.get(pid)
            if p is None:
                return
            t = msg.get("t")
            if t == "hello":
                p["name"] = str(msg.get("name", "Wanderer"))[:16]
                av = msg.get("avatar")
                p["avatar"] = av if av in ("lantern", "constellation") else "lantern"
            elif t == "move":
                dx = max(-1, min(1, int(msg.get("dx", 0))))
                dy = max(-1, min(1, int(msg.get("dy", 0))))
                p["x"] = max(0, min(COLS - 1, p["x"] + dx))
                p["y"] = max(0, min(ROWS - 1, p["y"] + dy))
            elif t == "plant":
                key = (p["x"], p["y"])
                self.flora[key] = min(3, self.flora.get(key, 0) + 1)
            elif t == "light":
                for i, s in enumerate(self.stars):
                    if abs(s["x"] - p["x"]) <= 1 and abs(s["y"] - p["y"]) <= 1:
                        s["lit"] = True
                        if self.last_star is not None and self.last_star != i:
                            pair = sorted((self.last_star, i))
                            if pair not in self.links:
                                self.links.append(pair)
                        self.last_star = i
                        break
            elif t == "chime":
                self.chimes.append({"x": p["x"], "y": p["y"], "note": p["x"] % 8, "age": 0})
                now = time.time()
                for oid, (ot, ox, oy) in self.last_chime.items():
                    if oid != pid and oid in self.players and now - ot <= 2.0:
                        self.harmonies.append({"x1": ox, "y1": oy, "x2": p["x"], "y2": p["y"], "age": 0})
                        for k in range(6):
                            fx = ox + (p["x"] - ox) * k / 5.0
                            fy = oy + (p["y"] - oy) * k / 5.0
                            self.fireflies.append({"x": fx, "y": fy, "a": random.uniform(0, 6.28), "life": 60})
                        break
                self.last_chime[pid] = (now, p["x"], p["y"])
            elif t == "inscribe":
                text = str(msg.get("text", ""))[:60].strip()
                if text:
                    self.stones = [st for st in self.stones if (st["x"], st["y"]) != (p["x"], p["y"])]
                    self.stones.append({"x": p["x"], "y": p["y"], "text": text, "by": p["name"]})
            elif t == "say":
                p["say"] = str(msg.get("text", ""))[:60]
                p["say_t"] = time.time()

    def step(self):
        with self.lock:
            self.tick += 1
            for c in self.chimes:
                c["age"] += 1
            self.chimes = [c for c in self.chimes if c["age"] < 15]
            for h in self.harmonies:
                h["age"] += 1
            self.harmonies = [h for h in self.harmonies if h["age"] < 20]
            trees = [k for k, v in self.flora.items() if v >= 3]
            if trees and len(self.fireflies) < 4 * len(trees) and random.random() < 0.3:
                tx, ty = random.choice(trees)
                self.fireflies.append({"x": tx + 0.0, "y": ty + 0.0, "a": random.uniform(0, 6.28), "life": 80})
            for f in self.fireflies:
                f["a"] += random.uniform(-0.4, 0.4)
                f["x"] = max(0.0, min(COLS - 1.0, f["x"] + 0.12 * math.cos(f["a"])))
                f["y"] = max(0.0, min(ROWS - 1.0, f["y"] + 0.12 * math.sin(f["a"])))
                f["life"] -= 1
            self.fireflies = [f for f in self.fireflies if f["life"] > 0]
            now = time.time()
            for p in self.players.values():
                if p["say"] and now - p["say_t"] > 6:
                    p["say"] = ""

    def snapshot(self):
        with self.lock:
            glow = min(100, sum(self.flora.values()) * 3
                       + sum(s["lit"] for s in self.stars) * 4 + len(self.links) * 3)
            return {"t": "state", "tick": self.tick,
                    "players": [{k: v for k, v in p.items() if k != "say_t"} for p in self.players.values()],
                    "flora": [{"x": x, "y": y, "stage": s} for (x, y), s in self.flora.items()],
                    "stars": [dict(s) for s in self.stars], "links": [list(l) for l in self.links],
                    "chimes": [dict(c) for c in self.chimes], "glow": glow,
                    "harmonies": [dict(h) for h in self.harmonies],
                    "stones": [dict(st) for st in self.stones],
                    "aurora": all(s["lit"] for s in self.stars),
                    "fireflies": [{"x": round(f["x"], 2), "y": round(f["y"], 2)} for f in self.fireflies]}


SAVE_PATH = Path(__file__).with_name("garden_save.json")


def create_server(host: str = "", port: Optional[int] = None, save_path=SAVE_PATH, **_kwargs) -> JsonLineServer:
    world = World(save=str(save_path) if save_path is not None else None)
    srv: JsonLineServer

    def on_connect(peer: PeerSession) -> None:
        pid = world.add_player()
        peer.meta["pid"] = pid
        peer.send({"t": "welcome", "id": pid, "cols": COLS, "rows": ROWS})
        print(f"player {pid} joined", flush=True)

    def on_message(peer: PeerSession, msg: dict) -> None:
        try:
            world.handle(peer.meta["pid"], msg)
        except (ValueError, TypeError, KeyError):
            pass

    def on_disconnect(peer: PeerSession) -> None:
        pid = peer.meta.get("pid")
        if pid is not None:
            world.remove_player(pid)
            print(f"player {pid} left", flush=True)

    def on_tick() -> None:
        world.step()
        snap = world.snapshot()
        if world.save_path and world.tick % 50 == 0:
            tmp = world.save_path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(snap, fh)
            os.replace(tmp, world.save_path)
        srv.broadcast(snap)

    srv = JsonLineServer(
        host=host,
        port=port,
        on_connect=on_connect,
        on_message=on_message,
        on_disconnect=on_disconnect,
        tick_interval=0.1,
        on_tick=on_tick,
        banner="Twilight Sky-Garden (記憶石の庭) server ready.",
    )
    srv.world = world  # type: ignore[attr-defined]
    return srv


def main() -> None:
    ap = argparse.ArgumentParser(description="Twilight Sky-Garden (Memory Stones) server")
    ap.add_argument("--host", default="")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--save", default=str(SAVE_PATH), help="Garden save file (default: garden_save.json beside this file)")
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()
    create_server(host=args.host, port=args.port, save_path=None if args.no_save else args.save).serve_forever()


if __name__ == "__main__":
    main()
