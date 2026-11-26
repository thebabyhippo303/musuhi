#!/usr/bin/env python3
"""Emberglow Isle — authoritative world server (see PROTOCOL.md)."""
import json
import os
import random
import socket
import threading
import time

W, H = 24, 12
TILES = [
    "~~~~~~~~~~~~~~~~~~~~~~~~",
    "~~ss.....T....#....ss~~~",
    "~s....T.......p.......s~",
    "~s.......#....p..T....s~",
    "~...T.........p........~",
    "~.....pppppppBppppp....~",
    "~.............p....#...~",
    "~s..#.........p.......s~",
    "~s.......T....p..T....s~",
    "~~s...........p......s~~",
    "~~~ss......T......sss~~~",
    "~~~~~~~~~~~~~~~~~~~~~~~~",
]
WALKABLE = set(".sp")
PLANTABLE = set(".s")
MAX_LANTERNS = 8
MAX_PLANTS = 40
LIGHT_RADIUS = 2
GROW_SECONDS = 3.0
EMOTES = ("wave", "heart", "dance", "glow")
SKIES = ((20, "dawnsong"), (12, "aurora"), (5, "starlit"), (0, "dusk"))
SPAWNS = {"gardener": (11, 6), "keeper": (15, 4)}


class World:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.tick = 0
        self.players = {}
        self.lanterns = set()
        self.plants = {}   # (x, y) -> {"stage": int, "t": seconds of light banked}
        self.notes = {}    # (x, y) -> {"text": str, "by": str}
        self.fireflies = []
        self.event = ""
        self.log = []
        self.sky = "dusk"
        self.next_id = 1
        self.note_seq = 0
        self.homes = {}    # name -> (x, y) last seen, so a rejoin resumes in place
        self.bell = next((x, y) for y, row in enumerate(TILES)
                         for x, c in enumerate(row) if c == "B")

    # -- helpers
    def say(self, line, event=False):
        self.log = (self.log + [line])[-6:]
        if event:
            self.event = line

    def walkable(self, x, y):
        return 0 <= x < W and 0 <= y < H and TILES[y][x] in WALKABLE

    def lit(self, x, y):
        return any(max(abs(x - lx), abs(y - ly)) <= LIGHT_RADIUS
                   for lx, ly in self.lanterns)

    def near_bell(self, p):
        return max(abs(p["x"] - self.bell[0]), abs(p["y"] - self.bell[1])) <= 1

    def blooms(self):
        return sum(1 for p in self.plants.values() if p["stage"] >= 3)

    # -- players
    def join(self, msg):
        role = msg.get("role") if msg.get("role") in SPAWNS else "gardener"
        pid = self.next_id
        self.next_id += 1
        name = str(msg.get("name") or "Guest")[:16]
        x, y = self.homes.get(name, SPAWNS[role])
        if not self.walkable(x, y):
            x, y = SPAWNS[role]
        self.players[pid] = {
            "id": pid, "name": name, "role": role,
            "kind": str(msg.get("kind") or "wanderer")[:16],
            "color": str(msg.get("color") or "#ffffff")[:9],
            "x": x, "y": y, "face": "d", "emote": "", "emote_until": 0.0,
        }
        self.say("%s arrived on the isle" % self.players[pid]["name"])
        return pid

    def leave(self, pid):
        p = self.players.pop(pid, None)
        if p:
            self.homes[p["name"]] = (p["x"], p["y"])
            self.say("%s drifted away" % p["name"])

    # -- actions; each returns an error string or None
    def handle(self, pid, msg, now=None):
        now = time.time() if now is None else now
        p = self.players.get(pid)
        if p is None:
            return "not joined"
        t = msg.get("t")
        if t == "ping":
            return None
        if t == "move":
            return self.move(p, msg)
        if t == "act":
            return self.act(p, msg, now)
        return "unknown message"

    def move(self, p, msg):
        try:
            dx = max(-1, min(1, int(msg.get("dx", 0))))
            dy = max(-1, min(1, int(msg.get("dy", 0))))
        except (TypeError, ValueError):
            return "bad move"
        if dx:
            p["face"] = "r" if dx > 0 else "l"
        elif dy:
            p["face"] = "d" if dy > 0 else "u"
        nx, ny = p["x"] + dx, p["y"] + dy
        if not self.walkable(nx, ny):
            return "blocked"
        p["x"], p["y"] = nx, ny
        return None

    def act(self, p, msg, now):
        a = msg.get("a")
        if a == "primary":
            a = "lantern" if p["role"] == "keeper" else "seed"
        pos = (p["x"], p["y"])
        if a == "lantern":
            if p["role"] != "keeper":
                return "only the keeper carries lanterns"
            if pos in self.lanterns:
                self.lanterns.discard(pos)
                self.say("%s lifted a lantern" % p["name"])
            elif len(self.lanterns) >= MAX_LANTERNS:
                return "all lanterns are placed"
            else:
                self.lanterns.add(pos)
                self.say("%s lit a lantern" % p["name"])
            return None
        if a == "seed":
            if p["role"] != "gardener":
                return "only the gardener carries seeds"
            if TILES[pos[1]][pos[0]] not in PLANTABLE:
                return "seeds need grass or sand"
            if pos in self.plants:
                return "something already grows here"
            if len(self.plants) >= MAX_PLANTS:
                return "the seed pouch is empty"
            self.plants[pos] = {"stage": 0, "t": 0.0, "hue": ""}
            self.say("%s planted a seed" % p["name"])
            return None
        if a == "ring":
            if not self.near_bell(p):
                return "too far from the bell"
            if len(self.players) >= 2 and all(self.near_bell(q) for q in self.players.values()):
                grown = 0
                for (x, y), pl in self.plants.items():
                    if pl["stage"] < 3 and self.lit(x, y):
                        pl["stage"] += 1
                        pl["t"] = 0.0
                        grown += 1
                        if pl["stage"] == 3:
                            pl["hue"] = self.sky
                self.spawn_fireflies(12)
                self.say("Duet! The bell hums and %d plants stir." % grown, event=True)
                self.update_sky()
            else:
                self.spawn_fireflies(2)
                self.say("%s rang the bell. It waits for a second voice." % p["name"], event=True)
            return None
        if a == "emote":
            e = msg.get("e")
            if e not in EMOTES:
                return "unknown emote"
            p["emote"], p["emote_until"] = e, now + 3.0
            self.say("%s: %s" % (p["name"], e))
            return None
        if a == "note":
            text = " ".join(str(msg.get("text") or "").split())[:40]
            if not text:
                return "empty note"
            self.note_seq += 1
            self.notes[pos] = {"text": text, "by": p["name"], "n": self.note_seq}
            self.say("%s left a note" % p["name"])
            return None
        return "unknown action"

    # -- simulation
    def spawn_fireflies(self, n):
        spots = [k for k, pl in self.plants.items() if pl["stage"] >= 3] or [self.bell]
        for _ in range(n):
            x, y = self.rng.choice(spots)
            self.fireflies.append([max(0, min(W - 1, x + self.rng.randint(-2, 2))),
                                   max(0, min(H - 1, y + self.rng.randint(-2, 2)))])
        self.fireflies = self.fireflies[-24:]

    def update_sky(self):
        b = self.blooms()
        sky = next(name for need, name in SKIES if b >= need)
        if sky != self.sky:
            self.sky = sky
            self.say({"starlit": "The first stars answer the blooms.",
                      "aurora": "An aurora unfurls over Emberglow Isle!",
                      "dawnsong": "Dawnsong: the whole isle is in flower.",
                      "dusk": "Dusk settles again."}[sky], event=True)

    def step(self, dt, now=None):
        """Advance the world by dt seconds. Returns True if anything changed."""
        now = time.time() if now is None else now
        self.tick += 1
        changed = False
        for p in self.players.values():
            if p["emote"] and now >= p["emote_until"]:
                p["emote"] = ""
                changed = True
        for (x, y), pl in self.plants.items():
            if pl["stage"] < 3 and self.lit(x, y):
                pl["t"] += dt
                if pl["t"] >= GROW_SECONDS:
                    pl["t"] = 0.0
                    pl["stage"] += 1
                    changed = True
                    if pl["stage"] == 3:
                        pl["hue"] = self.sky  # a flower remembers the sky it opened under
                        self.say("A flower bloomed in the lantern light")
                        self.spawn_fireflies(1)
        if changed:
            self.update_sky()
        if self.fireflies and self.tick % 3 == 0:
            for f in self.fireflies:
                f[0] = max(0, min(W - 1, f[0] + self.rng.randint(-1, 1)))
                f[1] = max(0, min(H - 1, f[1] + self.rng.randint(-1, 1)))
            changed = True
        return changed

    def snapshot(self):
        return {
            "t": "state", "tick": self.tick,
            "players": [{k: p[k] for k in ("id", "name", "role", "kind", "color",
                                           "x", "y", "face", "emote")}
                        for p in self.players.values()],
            "lanterns": sorted([x, y] for x, y in self.lanterns),
            "plants": [{"x": x, "y": y, "stage": pl["stage"], "lit": self.lit(x, y),
                        "hue": pl.get("hue", ""), "recalled": bool(pl.get("recalled"))}
                       for (x, y), pl in sorted(self.plants.items())],
            "notes": [{"x": x, "y": y, "text": n["text"], "by": n["by"], "n": n.get("n", 0)}
                      for (x, y), n in sorted(self.notes.items(),
                                              key=lambda kv: kv[1].get("n", 0))],
            "fireflies": [list(f) for f in self.fireflies],
            "blooms": self.blooms(), "sky": self.sky,
            "event": self.event, "log": list(self.log),
        }


    # -- persistence, so the isle survives a server restart
    def to_save(self):
        homes = dict(self.homes)
        homes.update({p["name"]: (p["x"], p["y"]) for p in self.players.values()})
        return {
            "lanterns": sorted([x, y] for x, y in self.lanterns),
            "plants": [[x, y, pl["stage"], pl.get("hue", ""), bool(pl.get("recalled"))]
                       for (x, y), pl in sorted(self.plants.items())],
            "notes": [[x, y, n["text"], n["by"], n.get("n", 0)]
                      for (x, y), n in sorted(self.notes.items())],
            "homes": {k: list(v) for k, v in homes.items()},
            "sky": self.sky, "event": self.event, "log": list(self.log),
            "note_seq": self.note_seq,
        }

    def load_save(self, data):
        self.lanterns = {(int(x), int(y)) for x, y in data.get("lanterns", [])}
        # row: x, y, stage, hue[, recalled]; recalled = hue set from memory, not witnessed
        self.plants = {(int(r[0]), int(r[1])): {"stage": int(r[2]), "t": 0.0, "hue": str(r[3]),
                                                "recalled": bool(r[4]) if len(r) > 4 else False}
                       for r in data.get("plants", [])}
        self.notes = {(int(x), int(y)): {"text": str(text), "by": str(by), "n": int(n)}
                      for x, y, text, by, n in data.get("notes", [])}
        self.homes = {str(k): (int(v[0]), int(v[1])) for k, v in data.get("homes", {}).items()}
        self.note_seq = max([int(data.get("note_seq", 0))] +
                            [n["n"] for n in self.notes.values()])
        self.sky = next(name for need, name in SKIES if self.blooms() >= need)
        self.event = str(data.get("event", ""))
        self.log = [str(x) for x in data.get("log", [])][-6:]
        if any(pl["stage"] >= 3 for pl in self.plants.values()):
            self.spawn_fireflies(10)



from pathlib import Path
import argparse
from musuhi.net import JsonLineServer, PeerSession

SAVE_PATH = Path(__file__).with_name("world_save.json")


def create_server(host: str = "", port=None, save_path=SAVE_PATH, **_kwargs) -> JsonLineServer:
    world = World()
    save_file = Path(save_path) if save_path is not None else None
    saved_cache = [None]
    if save_file and save_file.exists():
        try:
            world.load_save(json.loads(save_file.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, KeyError):
            pass
    lock = threading.Lock()
    last_t = [time.time()]
    srv: JsonLineServer

    def save_locked():
        if not save_file:
            return
        data = json.dumps(world.to_save())
        if data == saved_cache[0]:
            return
        try:
            tmp = save_file.with_suffix(".json.tmp")
            tmp.write_text(data, encoding="utf-8")
            os.replace(tmp, save_file)
            saved_cache[0] = data
        except OSError:
            pass

    def broadcast_locked():
        srv.broadcast(world.snapshot())

    def on_message(peer: PeerSession, msg: dict):
        with lock:
            pid = peer.meta.get("pid")
            if pid is None:
                if msg.get("t") != "join":
                    peer.send({"t": "error", "msg": "join first"})
                    return
                pid = world.join(msg)
                peer.meta["pid"] = pid
                peer.send({"t": "welcome", "id": pid, "w": W, "h": H, "tiles": TILES, "world": "Emberglow Isle"})
            else:
                err = world.handle(pid, msg)
                if err:
                    peer.send({"t": "error", "msg": err})
            broadcast_locked()

    def on_disconnect(peer: PeerSession):
        with lock:
            pid = peer.meta.get("pid")
            if pid is not None:
                world.leave(pid)
                broadcast_locked()

    def on_tick():
        now = time.time()
        with lock:
            world.step(now - last_t[0], now)
            broadcast_locked()
            if world.tick % 5 == 0:
                save_locked()
        last_t[0] = now

    srv = JsonLineServer(
        host=host,
        port=port,
        on_message=on_message,
        on_disconnect=on_disconnect,
        tick_interval=0.2,
        on_tick=on_tick,
        banner="Emberglow Isle (熾火の島) server ready.",
    )
    srv.world = world
    return srv


def main():
    ap = argparse.ArgumentParser(description="Emberglow Isle server")
    ap.add_argument("--host", default="")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()
    create_server(host=args.host, port=args.port, save_path=None if args.no_save else SAVE_PATH).serve_forever()


if __name__ == "__main__":
    main()
