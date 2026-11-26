#!/usr/bin/env python3
"""Twilight Sky Garden authoritative server."""
import json, os, socket, threading, time

W, H = 20, 10
ISLAND = [
    "....############....",
    "..################..",
    ".##################.",
    "####################",
    "####################",
    "####################",
    ".##################.",
    "..################..",
    "....############....",
    "......########......",
]
CHIMES = [(3, 3), (16, 3), (9, 7)]
STARS = [(0.08, 0.30), (0.17, 0.12), (0.28, 0.35), (0.38, 0.15), (0.47, 0.40), (0.56, 0.10),
         (0.65, 0.32), (0.74, 0.14), (0.83, 0.38), (0.92, 0.18)]
SAVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_save.json")
SPAWN = {"lantern": (6, 4), "prism": (13, 4)}


class World:
    def __init__(self):
        self.lock = threading.Lock()
        self.tick = 0
        self.players = {}
        self.plants = {}
        self.chimes = [{"x": x, "y": y, "ring_t": None} for x, y in CHIMES]
        self.stars = [{"x": x, "y": y, "lit": False, "by": None} for x, y in STARS]
        self.notes = []
        self.log = []
        self.next_id = 1
        self.island = [list(r) for r in ISLAND]
        self.lamps = []
        self.hearts = {}
        self.wish_t = None
        self.wishes = 0
        self.load()

    def save(self):
        try:
            with open(SAVE, "w") as f:
                json.dump({"plants": list(self.plants.values()), "stars": self.stars, "notes": self.notes,
                           "island": ["".join(r) for r in self.island], "lamps": self.lamps,
                           "wishes": self.wishes, "log": self.log}, f)
        except OSError:
            pass

    def load(self):
        try:
            with open(SAVE) as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        self.plants = {(p["x"], p["y"]): p for p in d.get("plants", [])}
        self.stars = d.get("stars", self.stars)
        self.notes = d.get("notes", [])
        self.island = [list(r) for r in d.get("island", ISLAND)]
        self.lamps = d.get("lamps", [])
        self.wishes = d.get("wishes", 0)
        self.log = d.get("log", [])

    def walkable(self, x, y):
        if not (0 <= x < W and 0 <= y < H) or self.island[y][x] not in "#*":
            return False
        return (x, y) not in CHIMES

    def add_log(self, s):
        self.log = (self.log + [s])[-6:]

    def bloom(self):
        b = sum(p["stage"] for p in self.plants.values()) * 4 + sum(s["lit"] for s in self.stars) * 4
        b += min(len(self.notes), 5) * 2 + len(self.lamps) * 3 + self.wishes * 5
        return min(100, b)

    def join(self, name, role):
        pid = "p%d" % self.next_id
        self.next_id += 1
        role = role if role in SPAWN else "prism"
        x, y = SPAWN[role]
        self.players[pid] = {"name": str(name)[:16] or role.title(), "role": role, "x": x, "y": y,
                             "emote": None, "emote_t": None}
        self.add_log("%s drifted onto the island" % self.players[pid]["name"])
        return pid

    def leave(self, pid):
        p = self.players.pop(pid, None)
        if p:
            self.add_log("%s faded into the dusk" % p["name"])

    def handle(self, pid, m):
        p = self.players.get(pid)
        if not p:
            return False
        t = m.get("t")
        if t == "move":
            dx = max(-1, min(1, int(m.get("dx", 0))))
            dy = max(-1, min(1, int(m.get("dy", 0))))
            nx, ny = p["x"] + dx, p["y"] + dy
            if self.walkable(nx, ny):
                p["x"], p["y"] = nx, ny
                return True
            return False
        if t == "plant":
            k = (p["x"], p["y"])
            pl = self.plants.get(k)
            if pl is None:
                self.plants[k] = {"x": k[0], "y": k[1], "stage": 1, "by": p["name"]}
                self.add_log("%s planted a glowing seed" % p["name"])
            elif pl["stage"] < 3:
                pl["stage"] += 1
                self.add_log("%s helped a flower bloom (stage %d)" % (p["name"], pl["stage"]))
            else:
                return False
            return True
        if t == "chime":
            best = None
            for c in self.chimes:
                if max(abs(c["x"] - p["x"]), abs(c["y"] - p["y"])) <= 1:
                    best = c
            if best is None:
                return False
            best["ring_t"] = time.time()
            self.add_log("%s rang a sky chime ~ding~" % p["name"])
            return True
        if t == "star":
            for s in self.stars:
                if not s["lit"]:
                    s["lit"], s["by"] = True, p["name"]
                    self.add_log("%s lit a star" % p["name"])
                    return True
            return False
        if t == "note":
            text = str(m.get("text", ""))[:60].strip()
            if not text:
                return False
            self.notes = [n for n in self.notes if (n["x"], n["y"]) != (p["x"], p["y"])]
            self.notes.append({"x": p["x"], "y": p["y"], "text": text, "by": p["name"]})
            self.notes = self.notes[-20:]
            self.add_log('%s left a note: "%s"' % (p["name"], text[:24]))
            return True
        if t == "emote":
            e = m.get("e")
            if e not in ("wave", "heart", "spark"):
                return False
            now = time.time()
            p["emote"], p["emote_t"] = e, now
            if e == "heart":
                self.hearts[pid] = now
                for qid, q in self.players.items():
                    if qid != pid and now - self.hearts.get(qid, 0) <= 10 and \
                            max(abs(q["x"] - p["x"]), abs(q["y"] - p["y"])) <= 2:
                        self.wish_t = now
                        self.wishes += 1
                        self.hearts.clear()
                        self.add_log("Two hearts met - a shooting star! (wish #%d)" % self.wishes)
                        break
            return True
        if t == "build":
            dx = max(-1, min(1, int(m.get("dx", 0))))
            dy = max(-1, min(1, int(m.get("dy", 0))))
            nx, ny = p["x"] + dx, p["y"] + dy
            if (dx or dy) and 0 <= nx < W and 0 <= ny < H and self.island[ny][nx] == ".":
                self.island[ny][nx] = "*"
                self.add_log("%s wove a glowing stepping-stone" % p["name"])
                return True
            return False
        if t == "lamp":
            k = (p["x"], p["y"])
            if any((l["x"], l["y"]) == k for l in self.lamps):
                return False
            self.lamps.append({"x": k[0], "y": k[1], "by": p["name"], "role": p["role"]})
            self.add_log("%s raised a lamp post" % p["name"])
            return True
        return False

    def snapshot(self):
        now = time.time()
        age = lambda t: None if t is None else round(now - t, 2)
        return {
            "t": "state", "tick": self.tick, "island": ["".join(r) for r in self.island],
            "lamps": self.lamps, "wishes": self.wishes, "wish_age": age(self.wish_t),
            "players": {k: {"name": v["name"], "role": v["role"], "x": v["x"], "y": v["y"],
                            "emote": v["emote"], "emote_age": age(v["emote_t"])}
                        for k, v in self.players.items()},
            "plants": list(self.plants.values()),
            "chimes": [{"x": c["x"], "y": c["y"], "ring_age": age(c["ring_t"])} for c in self.chimes],
            "stars": self.stars, "notes": self.notes, "log": self.log, "bloom": self.bloom(),
        }



import argparse
from pathlib import Path
from musuhi.net import JsonLineServer, PeerSession


def create_server(host: str = "", port=None, scars: bool = True, **_kwargs) -> JsonLineServer:
    world = World()
    if not scars:
        world.island = [list(r) for r in ISLAND]
        world.plants = {}
        world.lamps = []
        world.notes = []
        world.stars = [{"x": x, "y": y, "lit": False, "by": None} for x, y in STARS]
        world.wishes = 0
        world.log = ["Twilight settles over a fresh sky island."]
    srv: JsonLineServer

    def broadcast():
        with world.lock:
            world.tick += 1
            snap = world.snapshot()
        srv.broadcast(snap)

    def on_message(peer: PeerSession, m: dict):
        pid = peer.meta.get("pid")
        if pid is None:
            if m.get("t") != "hello":
                return
            with world.lock:
                pid = world.join(m.get("name", ""), m.get("role", ""))
            peer.meta["pid"] = pid
            peer.send({"t": "welcome", "id": pid})
            broadcast()
            return
        if m.get("t") == "ping":
            peer.send({"t": "pong"})
            return
        with world.lock:
            changed = world.handle(pid, m)
            if changed:
                world.save()
        if changed:
            broadcast()

    def on_disconnect(peer: PeerSession):
        pid = peer.meta.get("pid")
        if pid:
            with world.lock:
                world.leave(pid)
            broadcast()

    srv = JsonLineServer(
        host=host,
        port=port,
        on_message=on_message,
        on_disconnect=on_disconnect,
        tick_interval=0.5,
        on_tick=broadcast,
        banner="Twilight Sky Garden (空庭と未知の存在) server ready.",
    )
    srv.world = world
    return srv


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Twilight Sky Garden server")
    ap.add_argument("--host", default="")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--fresh", action="store_true", help="Start fresh instead of loading kintsugi save")
    args = ap.parse_args()
    create_server(host=args.host, port=args.port, scars=not args.fresh).serve_forever()
