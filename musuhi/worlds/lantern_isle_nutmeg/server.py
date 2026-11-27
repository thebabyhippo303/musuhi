#!/usr/bin/env python3
"""Lantern Isle (灯籠島とナツメグ) — authoritative world server (see PROTOCOL.md), powered by musuhi.net."""
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

W, H, TILE = 35, 18, 24
TICK_HZ = 5
DAY_SECONDS = 120.0
GROW_DRY, GROW_WET = 12.0, 5.0
WET_SECONDS = 20.0
SEED_EVERY, SEED_MAX = 20.0, 9
MOVE_MIN_DT = 0.11
COLORS = [[240, 120, 90], [90, 170, 240], [250, 210, 90], [170, 120, 230],
          [120, 220, 150], [240, 150, 200]]
EMOTES = ("wave", "heart", "laugh", "star")
STAGES = ("sprout", "bud", "flower")
RAIN_SECONDS = 14.0
RAIN_GAP = (70.0, 110.0)
FOX_NAME = "Nutmeg"
FOX_STEP_DT = 0.8
FOX_GIFT_COOLDOWN = 12.0
AURORA_SECONDS = 40.0
GOAL_BASE, GOAL_STEP = 100, 50
STAR_NAMES = ["Lumen", "Petalwake", "Foxfire", "Tidewick", "Mothlight", "Dewbell",
              "Emberly", "Saltwink", "Fernglow", "Hushlamp"]
DUET_WINDOW, DUET_COOLDOWN = 4.0, 30.0
APPLAUSE_COOLDOWN = 8.0
SAVE_EVERY = 3.0
SAVE_PATH = os.environ.get("LANTERN_SAVE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "world.json")


def make_map(seed=7):
    """Deterministic island: water border, sandy shore, grass core, a pond, rocks, trees."""
    rng = random.Random(seed)
    cx, cy = (W - 1) / 2.0, (H - 1) / 2.0
    rows = []
    for y in range(H):
        row = []
        for x in range(W):
            dx, dy = (x - cx) / (W / 2.0), (y - cy) / (H / 2.0)
            d = math.hypot(dx, dy) + 0.06 * math.sin(x * 0.9) + 0.06 * math.cos(y * 1.3)
            if d > 0.93:
                c = "~"
            elif d > 0.80:
                c = "s"
            else:
                c = "."
                r = rng.random()
                if r < 0.05:
                    c = "T"
                elif r < 0.08:
                    c = "#"
            row.append(c)
        rows.append(row)
    # a little pond east of center
    for (px, py) in ((24, 6), (25, 6), (24, 7), (25, 7), (26, 7), (25, 8)):
        rows[py][px] = "~"
    # keep the central plaza clear
    for y in range(int(cy) - 1, int(cy) + 3):
        for x in range(int(cx) - 3, int(cx) + 4):
            rows[y][x] = "."
    return ["".join(r) for r in rows]


class World:
    def __init__(self, now=0.0):
        self.tiles = make_map()
        self.players = {}
        self.objs = {}          # (x,y) -> dict(k, wet_until, t_stage)
        self.flies = []
        self.blooms = 0
        self.log = ["The isle awakens."]
        self.tick = 0
        self.t0 = now
        self.now = now
        self.next_seed = now + SEED_EVERY
        self.stars = 0          # auroras completed; chapter = stars + 1
        self.aurora_until = 0.0
        self.sky = []           # named stars: {"name", "by"}
        self.next_duet = 0.0
        self.wish = None        # (text, keeper) whispered during the current aurora
        self._n = 0
        self.palette = []       # keeper names in first-arrival order (stable colours)
        self.known = {}         # name -> saved keeper (seeds, petals, x, y)
        self.rain_until = 0.0
        self.next_rain = now + random.uniform(*RAIN_GAP) / 2
        self.fox = {"x": W // 2 + 4, "y": H // 2 + 3, "mood": "walk",
                    "friends": {}, "_next": now, "_gift": 0.0, "_mood_until": 0.0}

    # ---- helpers
    def terrain(self, x, y):
        if 0 <= x < W and 0 <= y < H:
            return self.tiles[y][x]
        return "~"

    def walkable(self, x, y):
        return self.terrain(x, y) in ".s"

    def time_phase(self):
        return ((self.now - self.t0) / DAY_SECONDS) % 1.0

    def is_night(self):
        return self.time_phase() >= 0.5

    def say_log(self, text):
        self.log.append(text)
        del self.log[:-6]

    def counts(self):
        c = {"flower": 0, "lantern": 0, "path": 0, "sprout": 0, "bud": 0}
        for o in self.objs.values():
            c[o["k"]] += 1
        return c

    def goal(self):
        return GOAL_BASE + GOAL_STEP * self.stars

    def raw_harmony(self):
        c = self.counts()
        return (4 * c["flower"] + 6 * c["lantern"] + min(10 + 5 * self.stars, c["path"])
                + min(20 + 10 * self.stars, 2 * self.blooms))

    def aurora(self):
        return self.now < self.aurora_until

    def harmony(self):
        if self.aurora():
            return 100
        return min(100, self.raw_harmony() * 100 // self.goal())

    # ---- players
    def add_player(self, name):
        self._n += 1
        pid = "p%d" % self._n
        name = (str(name or pid).strip() or pid)[:12]
        cx, cy = W // 2, H // 2
        spot = (cx, cy)
        for (ox, oy) in ((0, 0), (-1, 0), (1, 0), (0, 1), (-2, 0), (2, 0), (0, -1), (-1, 1), (1, 1)):
            cand = (cx + ox, cy + oy)
            if self.walkable(*cand) and all((p["x"], p["y"]) != cand for p in self.players.values()):
                spot = cand
                break
        self.players[pid] = {
            "name": name, "x": spot[0], "y": spot[1],
            "color": COLORS[(self._n - 1) % len(COLORS)],
            "seeds": 5, "petals": 0, "emote": "", "say": "", "face": [0, 1],
            "_emote_until": 0.0, "_say_until": 0.0, "_last_move": 0.0,
            "note": -1, "_note_until": 0.0,
        }
        old = self.known.get(name)
        if name not in self.palette:
            self.palette.append(name)
        self.players[pid]["color"] = COLORS[self.palette.index(name) % len(COLORS)]
        if old:
            p = self.players[pid]
            p["seeds"], p["petals"] = int(old["seeds"]), int(old["petals"])
            if self.walkable(old["x"], old["y"]):
                p["x"], p["y"] = old["x"], old["y"]
            self.say_log("%s returns to the isle." % name)
        else:
            self.say_log("%s arrives on the isle." % name)
        return pid

    def remember(self, p):
        self.known[p["name"]] = {"seeds": p["seeds"], "petals": p["petals"],
                                 "x": p["x"], "y": p["y"]}

    def remove_player(self, pid):
        p = self.players.pop(pid, None)
        if p:
            self.remember(p)
            self.say_log("%s sails away." % p["name"])

    # ---- messages; returns error string or None
    def handle(self, pid, msg):
        p = self.players.get(pid)
        if p is None or not isinstance(msg, dict):
            return "unknown player"
        t = msg.get("t")
        if t == "move":
            return self._move(p, msg)
        if t == "act":
            return self._act(p, msg)
        if t == "emote":
            e = msg.get("e")
            if e not in EMOTES:
                return "unknown emote"
            p["emote"], p["_emote_until"] = e, self.now + 3.0
            if e == "heart":
                self._pet_fox(p)
            if e == "wave":
                self._duet(p)
            if e == "star":
                self._applaud(p)
            return None
        if t == "say":
            text = str(msg.get("text", "")).strip()[:60]
            if not text:
                return "empty text"
            p["say"], p["_say_until"] = text, self.now + 5.0
            self.say_log("%s: %s" % (p["name"], text))
            if self.aurora():
                self.wish = (text[:18].strip(), p["name"])
            return None
        if t == "name_star":
            try:
                i = int(msg.get("i", -1))
            except (TypeError, ValueError):
                return "bad star"
            name = " ".join(str(msg.get("name", "")).split())[:24]
            if not 0 <= i < len(self.sky):
                return "no such star yet"
            if not name:
                return "a star needs a name"
            self.sky[i] = {"name": name, "by": p["name"]}
            self.say_log('%s names star %d "%s".' % (p["name"], i + 1, name))
            return None
        if t == "chime":
            return self._chime(p, msg)
        if t in ("ping", "hello"):
            return None
        return "unknown message"

    def _move(self, p, msg):
        try:
            dx, dy = int(msg.get("dx", 0)), int(msg.get("dy", 0))
        except (TypeError, ValueError):
            return "bad move"
        dx, dy = max(-1, min(1, dx)), max(-1, min(1, dy))
        if dx == 0 and dy == 0:
            return "bad move"
        if self.now - p["_last_move"] < MOVE_MIN_DT:
            return "too fast"
        p["face"] = [dx, dy]
        nx, ny = p["x"] + dx, p["y"] + dy
        if not self.walkable(nx, ny):
            return "blocked"
        p["x"], p["y"], p["_last_move"] = nx, ny, self.now
        return None

    def _act(self, p, msg):
        a = msg.get("a")
        try:
            x = int(msg.get("x", p["x"]))
            y = int(msg.get("y", p["y"]))
        except (TypeError, ValueError):
            return "bad target"
        if max(abs(x - p["x"]), abs(y - p["y"])) > 1:
            return "too far"
        ter = self.terrain(x, y)
        o = self.objs.get((x, y))
        if a == "plant":
            if ter != ".":
                return "plants need grass"
            if o is not None:
                return "tile occupied"
            if p["seeds"] < 1:
                return "no seeds"
            p["seeds"] -= 1
            self.objs[(x, y)] = {"k": "sprout", "wet_until": 0.0, "grow": 0.0}
            return None
        if a == "water":
            if o is None or o["k"] not in STAGES:
                return "nothing to water"
            o["wet_until"] = self.now + WET_SECONDS
            return None
        if a == "harvest":
            if o is None or o["k"] != "flower":
                return "no flower here"
            del self.objs[(x, y)]
            p["petals"] += 2
            p["seeds"] = min(SEED_MAX, p["seeds"] + 1)
            self.blooms += 1
            self.say_log("%s gathers petals." % p["name"])
            return None
        if a == "path":
            if ter not in ".s":
                return "cannot build here"
            if o is not None:
                return "tile occupied"
            self.objs[(x, y)] = {"k": "path", "wet_until": 0.0, "grow": 0.0}
            return None
        if a == "lantern":
            if ter not in ".s":
                return "cannot build here"
            if o is not None and o["k"] != "path":
                return "tile occupied"
            if p["petals"] < 3:
                return "need 3 petals"
            p["petals"] -= 3
            self.objs[(x, y)] = {"k": "lantern", "wet_until": 0.0, "grow": 0.0}
            self.say_log("%s lights a lantern." % p["name"])
            return None
        if a == "clear":
            if o is None:
                return "nothing here"
            del self.objs[(x, y)]
            return None
        return "unknown action"

    # ---- greeting duet: two nearby keepers wave within a few seconds -> a wildflower springs up
    def _duet(self, p):
        if self.now < self.next_duet:
            return
        for q in self.players.values():
            if q is p or q["emote"] != "wave" or q["_emote_until"] - 3.0 < self.now - DUET_WINDOW:
                continue
            if max(abs(q["x"] - p["x"]), abs(q["y"] - p["y"])) > 3:
                continue
            mx, my = (p["x"] + q["x"]) // 2, (p["y"] + q["y"]) // 2
            spots = sorted(((x, y) for x in range(mx - 3, mx + 4) for y in range(my - 3, my + 4)
                            if self.terrain(x, y) == "." and (x, y) not in self.objs),
                           key=lambda s: abs(s[0] - mx) + abs(s[1] - my))
            if not spots:
                return
            self.objs[spots[0]] = {"k": "flower", "wet_until": 0.0, "grow": 0.0}
            self.next_duet = self.now + DUET_COOLDOWN
            self.say_log("%s and %s wave hello. A wildflower springs up between them!"
                         % (q["name"], p["name"]))
            return

    # ---- chimes: five notes; an ascending run shared by two keepers makes the isle hum along
    def _chime(self, p, msg):
        try:
            n = int(msg.get("n", -1))
        except (TypeError, ValueError):
            return "bad note"
        if not 0 <= n <= 4:
            return "bad note"
        p["note"], p["_note_until"] = n, self.now + 1.5
        self.tune = (getattr(self, "tune", []) + [{"n": n, "by": p["name"]}])[-8:]
        last = self.tune[-5:]
        if [d["n"] for d in last] == [0, 1, 2, 3, 4] and len({d["by"] for d in last}) >= 2:
            for o in self.objs.values():
                if o["k"] in STAGES:
                    o["wet_until"] = max(o["wet_until"], self.now + WET_SECONDS)
            self.tune = []
            self.say_log("%s ring the five chimes in turn. The isle hums along and every leaf drinks."
                         % " and ".join(sorted({d["by"] for d in last})))
        return None

    # ---- applause: a star emote for a keeper speaking by lantern light earns them a petal
    def _applaud(self, p):
        if self.now < getattr(self, "next_applause", 0.0):
            return
        for q in self.players.values():
            if q is p or not q["say"] or not self.near_lantern(q["x"], q["y"]):
                continue
            if max(abs(q["x"] - p["x"]), abs(q["y"] - p["y"])) > 6:
                continue
            q["petals"] += 1
            self.next_applause = self.now + APPLAUSE_COOLDOWN
            self.say_log("%s applauds %s's verse by lantern light. A petal drifts down."
                         % (p["name"], q["name"]))
            return

    # ---- the fox
    def _pet_fox(self, p):
        f = self.fox
        if max(abs(f["x"] - p["x"]), abs(f["y"] - p["y"])) > 2:
            return
        f["mood"], f["_mood_until"] = "happy", self.now + 3.0
        if self.now >= f["_gift"]:
            f["_gift"] = self.now + FOX_GIFT_COOLDOWN
            p["seeds"] = min(SEED_MAX, p["seeds"] + 1)
            if p["name"] not in f["friends"]:
                self.say_log("%s befriends %s the fox!" % (p["name"], FOX_NAME))
            else:
                self.say_log("%s the fox brings %s a seed." % (FOX_NAME, p["name"]))
            f["friends"][p["name"]] = f["friends"].get(p["name"], 0) + 1

    def _step_fox(self, now, night, lanterns):
        f = self.fox
        if f["mood"] == "happy":
            if now < f["_mood_until"]:
                return
            f["mood"] = "walk"
        if now < f["_next"]:
            return
        f["_next"] = now + FOX_STEP_DT
        target = None
        if night and lanterns:
            target = min(lanterns, key=lambda l: abs(l[0] - f["x"]) + abs(l[1] - f["y"]))
            if max(abs(target[0] - f["x"]), abs(target[1] - f["y"])) <= 1:
                f["mood"] = "nap"
                return
        f["mood"] = "walk"
        steps = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        random.shuffle(steps)
        if target:
            steps.sort(key=lambda d: abs(target[0] - f["x"] - d[0]) + abs(target[1] - f["y"] - d[1]))
        elif random.random() < 0.35:
            return
        for dx, dy in steps:
            nx, ny = f["x"] + dx, f["y"] + dy
            if self.walkable(nx, ny) and self.objs.get((nx, ny), {}).get("k") != "lantern":
                f["x"], f["y"] = nx, ny
                return

    # ---- persistence
    def to_save(self):
        for p in self.players.values():
            self.remember(p)
        return {"v": 1, "phase": self.time_phase(), "blooms": self.blooms,
                "objs": [[x, y, o["k"], round(o["grow"], 3)] for (x, y), o in sorted(self.objs.items())],
                "known": self.known, "fox": [self.fox["x"], self.fox["y"]],
                "friends": self.fox["friends"], "stars": self.stars, "sky": self.sky, "palette": self.palette, "log": self.log}

    def load_save(self, data):
        self.t0 = self.now - float(data.get("phase", 0.0)) * DAY_SECONDS
        self.blooms = int(data.get("blooms", 0))
        self.stars = int(data.get("stars", 0))
        self.sky = [{"name": str(d["name"]), "by": str(d["by"])} for d in data.get("sky", [])]
        while len(self.sky) < self.stars:
            self.sky.append({"name": STAR_NAMES[len(self.sky) % len(STAR_NAMES)], "by": "the isle"})
        self.objs = {}
        for x, y, k, grow in data.get("objs", []):
            if k in ("sprout", "bud", "flower", "path", "lantern") and self.terrain(x, y) in ".s":
                self.objs[(int(x), int(y))] = {"k": k, "wet_until": 0.0, "grow": float(grow)}
        self.known = dict(data.get("known", {}))
        self.palette = [str(n) for n in data.get("palette", [])] or ["Bram", "Wren"]
        fx, fy = data.get("fox", [self.fox["x"], self.fox["y"]])
        if self.walkable(fx, fy):
            self.fox["x"], self.fox["y"] = int(fx), int(fy)
        self.fox["friends"] = {str(k): int(v) for k, v in data.get("friends", {}).items()}
        self.log = [str(l) for l in data.get("log", [])][-5:] + ["The isle remembers."]

    # ---- simulation
    def near_lantern(self, x, y, r=2):
        for (ox, oy), o in self.objs.items():
            if o["k"] == "lantern" and max(abs(ox - x), abs(oy - y)) <= r:
                return True
        return False

    def step(self, now):
        dt = max(0.0, now - self.now)
        self.now = now
        self.tick += 1
        night = self.is_night()
        if now >= self.next_rain:
            self.rain_until = now + RAIN_SECONDS
            self.next_rain = now + RAIN_SECONDS + random.uniform(*RAIN_GAP)
            self.say_log("Soft rain drifts over the isle.")
        raining = now < self.rain_until
        for (x, y), o in self.objs.items():
            if raining and o["k"] in STAGES:
                o["wet_until"] = max(o["wet_until"], now + 6.0)
            if o["k"] in ("sprout", "bud"):
                if night and not self.near_lantern(x, y):
                    continue
                wet = o["wet_until"] > now
                o["grow"] += dt / (GROW_WET if wet else GROW_DRY)
                if o["grow"] >= 1.0:
                    o["grow"] = 0.0
                    o["k"] = STAGES[STAGES.index(o["k"]) + 1]
                    if o["k"] == "flower":
                        self.say_log("A flower blooms!")
        for p in self.players.values():
            if p["emote"] and now >= p["_emote_until"]:
                p["emote"] = ""
            if p["say"] and now >= p["_say_until"]:
                p["say"] = ""
            if p["note"] >= 0 and now >= p["_note_until"]:
                p["note"] = -1
        if now >= self.next_seed:
            self.next_seed = now + SEED_EVERY
            for p in self.players.values():
                p["seeds"] = min(SEED_MAX, p["seeds"] + 1)
        # fireflies drift around lanterns at night
        lanterns = [xy for xy, o in self.objs.items() if o["k"] == "lantern"]
        self._step_fox(now, night, lanterns)
        if night and lanterns:
            want = min(24, 3 * len(lanterns))
            while len(self.flies) < want:
                lx, ly = random.choice(lanterns)
                self.flies.append([lx + random.uniform(-2, 2), ly + random.uniform(-2, 2), lx, ly])
            del self.flies[want:]
            for f in self.flies:
                f[0] += random.uniform(-0.25, 0.25) + (f[2] - f[0]) * 0.05
                f[1] += random.uniform(-0.25, 0.25) + (f[3] - f[1]) * 0.05
        else:
            self.flies = []
        if self.aurora_until and now >= self.aurora_until:
            self.aurora_until = 0.0
            self.stars += 1
            name, by = self.wish or (STAR_NAMES[len(self.sky) % len(STAR_NAMES)], "the isle")
            self.wish = None
            self.sky.append({"name": name, "by": by})
            self.say_log('Star "%s" is named by %s. Chapter %d begins.' % (name, by, self.stars + 1))
        elif not self.aurora_until and self.raw_harmony() >= self.goal():
            self.aurora_until = now + AURORA_SECONDS
            self.wish = None
            self.say_log("The aurora dances! Speak a name and the new star keeps it.")

    def snapshot(self):
        now = self.now
        return {
            "t": "state", "tick": self.tick, "time": round(self.time_phase(), 4),
            "night": self.is_night(),
            "players": {pid: {k: v for k, v in p.items() if not k.startswith("_")}
                        for pid, p in self.players.items()},
            "objs": [{"x": x, "y": y, "k": o["k"], "wet": o["wet_until"] > now}
                     for (x, y), o in sorted(self.objs.items())],
            "flies": [[round(f[0], 2), round(f[1], 2)] for f in self.flies],
            "rain": now < self.rain_until,
            "critters": [{"x": self.fox["x"], "y": self.fox["y"], "k": "fox",
                          "name": FOX_NAME, "mood": self.fox["mood"],
                          "friends": dict(self.fox["friends"])}],
            "harmony": self.harmony(), "blooms": self.blooms,
            "aurora": self.aurora(), "sky": list(self.sky),
            "star_names": [d["name"] for d in self.sky], "stars": self.stars, "chapter": self.stars + 1,
            "goal": self.goal(), "raw": self.raw_harmony(), "log": list(self.log),
            "tune": list(getattr(self, "tune", [])),
        }

    def welcome(self, pid):
        return {"t": "welcome", "id": pid, "w": W, "h": H, "tile": TILE,
                "tiles": self.tiles, "proto": 2}


class _IsleServer(JsonLineServer):
    """JsonLineServer that also saves the isle when it shuts down."""

    on_stop = None

    def stop(self) -> None:
        super().stop()
        if self.on_stop:
            self.on_stop()


def create_server(host: str = "", port: Optional[int] = None, save_path=SAVE_PATH, **_kwargs) -> JsonLineServer:
    world = World(time.monotonic())
    lock = threading.RLock()
    save_file = str(save_path) if save_path is not None else None
    if save_file:
        try:
            with open(save_file) as fh:
                world.load_save(json.load(fh))
            print("world restored from save (%d objects)" % len(world.objs), flush=True)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    next_save = [time.monotonic() + SAVE_EVERY]
    srv: _IsleServer

    def save():
        if not save_file:
            return
        try:
            tmp = save_file + ".tmp"
            with lock:
                data = world.to_save()
            with open(tmp, "w") as fh:
                json.dump(data, fh)
            os.replace(tmp, save_file)
        except OSError:
            pass

    def on_message(peer: PeerSession, msg: dict) -> None:
        with lock:
            world.now = time.monotonic()
            if peer.meta.get("pid") is None:
                if msg.get("t") != "hello":
                    peer.send({"t": "err", "msg": "say hello first"})
                    return
                pid = world.add_player(msg.get("name"))
                peer.meta["pid"] = pid
                peer.send(world.welcome(pid))
                print("PHASE: LAN CONNECTED player joined: %s (players=%d)"
                      % (pid, len(world.players)), flush=True)
                return
            if msg.get("t") == "ping":
                peer.send({"t": "pong"})
                return
            err = world.handle(peer.meta["pid"], msg)
        if err:
            peer.send({"t": "err", "msg": err})

    def on_disconnect(peer: PeerSession) -> None:
        pid = peer.meta.get("pid")
        if pid:
            with lock:
                world.remove_player(pid)
                n = len(world.players)
            print("player left: %s (players=%d)" % (pid, n), flush=True)

    def on_tick() -> None:
        now = time.monotonic()
        with lock:
            world.step(now)
            snap = world.snapshot()
        if now >= next_save[0]:
            next_save[0] = now + SAVE_EVERY
            save()
        for peer in srv.peers():
            if peer.meta.get("pid"):
                peer.send(snap)

    srv = _IsleServer(
        host=host,
        port=port,
        on_message=on_message,
        on_disconnect=on_disconnect,
        tick_interval=1.0 / TICK_HZ,
        on_tick=on_tick,
        banner="Lantern Isle server listening (LAN ready)",
    )
    srv.on_stop = save
    srv.world = world  # type: ignore[attr-defined]
    return srv


def main() -> None:
    ap = argparse.ArgumentParser(description="Lantern Isle (Nutmeg the Fox) server")
    ap.add_argument("--host", default="")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--save", default=SAVE_PATH, help="Isle save file (default: world.json beside this file)")
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()
    create_server(host=args.host, port=args.port, save_path=None if args.no_save else args.save).serve_forever()


if __name__ == "__main__":
    main()
