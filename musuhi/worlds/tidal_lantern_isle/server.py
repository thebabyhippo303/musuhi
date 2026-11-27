#!/usr/bin/env python3
"""Tidal Lantern Isle — authoritative world server (see PROTOCOL.md)."""
import asyncio
import json
import math
import os
import random
import signal
import time
from collections import deque

W, H = 22, 13
TICK_HZ = 5
TIDE_PERIOD = 40.0
DAY_PERIOD = 240.0
MAX_REACH = 14
GROW_PER_STAGE = 5
EMOTES = {"wave", "heart", "dance", "cheer", "zzz"}
ACTIONS = {"dig", "fill", "plant", "harvest", "lantern", "unlantern"}

BASE_MAP = [
    "wwwwwwwwwwwwwwwwwwwwww",
    "wwssgggggggggggggggrrw",
    "wsssggggggggggggggggrw",
    "wssgggggggrggggggggggw",
    "wssggggggggggggggggggw",
    "wssgggggggggggggwwgggw",
    "wsssgggggggggggwwwwggw",
    "wssggggggggggggggwwggw",
    "wssgggggrggggggggggggw",
    "wssggggggggggggggggggw",
    "wsssggggggggggggggrggw",
    "wwssssgggggggggggsssww",
    "wwwwwwwwwwwwwwwwwwwwww",
]
SPAWNS = [(4, 4), (4, 8), (6, 6), (8, 5)]
WALKABLE = set("gcs")
SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_save.json")
# The Moonwell: the inland pond (sea tiles that do not touch the map border ring).
POND = {(x, y) for y in range(2, H - 2) for x in range(2, W - 2) if BASE_MAP[y][x] == "w"}
MAX_SIGNS = 16
HERON_LAMPS = 5
HERON_BONUS = 5
HERON_GIFT_RANGE = 2
SPRING_EXTRA = 6


class Player:
    def __init__(self, pid, color):
        self.id = pid
        self.name = "P%d" % pid
        self.x, self.y = SPAWNS[color % len(SPAWNS)]
        self.face = [1, 0]
        self.seeds = 6
        self.glow = 0
        self.emote = ""
        self.say = ""
        self.emote_until = 0.0
        self.say_until = 0.0
        self.color = color
        self.last_move = 0.0

    def snap(self):
        return {"id": self.id, "name": self.name, "x": self.x, "y": self.y,
                "face": self.face, "seeds": self.seeds, "glow": self.glow,
                "emote": self.emote, "say": self.say, "color": self.color}


class World:
    """Pure game logic; no sockets. `now` is injected so tests are deterministic."""

    def __init__(self, seed=7):
        self.rng = random.Random(seed)
        self.tiles = [list(r) for r in BASE_MAP]
        self.plants = {}    # (x, y) -> {"growth": int, "by": id}
        self.lanterns = {}  # (x, y) -> by
        self.players = {}
        self.next_id = 1
        self.tick = 0
        self.t = 0.0
        self.last_grow = 0.0
        self.level = 1
        self.goal = 30
        self.log = deque(maxlen=6)
        self.tide_dir = 0
        self.flies = [[self.rng.uniform(4, 18), self.rng.uniform(2, 10)] for _ in range(6)]
        self.signs = {}     # (x, y) -> {"text": str, "by": id}
        self.stash = {}     # name -> saved keeper (position + pockets) for reconnects
        self.koi = [[16, 6], [17, 6], [17, 7]]
        self.heron = None   # (x, y) while the heron visits the Moonwell
        self.heron_move_at = 0.0
        self.wet = set()
        self.recompute_wet()

    # ---- derived values -------------------------------------------------
    def tide(self):
        return 0.5 - 0.5 * math.cos(2 * math.pi * self.t / TIDE_PERIOD)

    def day(self):
        return (self.t / DAY_PERIOD) % 1.0

    def spring(self):
        """Every third tide is a spring tide that pushes further inland."""
        return int(self.t // TIDE_PERIOD) % 3 == 2

    def reach(self):
        return int(round(self.tide() * (MAX_REACH + (SPRING_EXTRA if self.spring() else 0))))

    def recompute_wet(self):
        """BFS from sea tiles through channel tiles, up to reach() steps."""
        reach = self.reach()
        wet = set()
        frontier = []
        for y in range(H):
            for x in range(W):
                if self.tiles[y][x] == "w":
                    frontier.append((x, y))
        seen = set(frontier)
        depth = 0
        while frontier and depth < reach:
            depth += 1
            nxt = []
            for (x, y) in frontier:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < W and 0 <= ny < H and (nx, ny) not in seen \
                            and self.tiles[ny][nx] == "c":
                        seen.add((nx, ny))
                        wet.add((nx, ny))
                        nxt.append((nx, ny))
            frontier = nxt
        self.wet = wet

    def light(self):
        lum = sum(1 for p in self.plants.values() if self.stage(p) >= 3)
        return 3 * len(self.lanterns) + lum + (HERON_BONUS if self.heron else 0)

    @staticmethod
    def stage(plant):
        return min(3, plant["growth"] // GROW_PER_STAGE)

    # ---- players --------------------------------------------------------
    def add_player(self, name=None):
        used = {p.color for p in self.players.values()}
        color = next(c for c in range(64) if c not in used)
        p = Player(self.next_id, color)
        self.next_id += 1
        if name:
            p.name = str(name)[:12]
        old = self.stash.pop(p.name, None)
        if old:
            p.seeds, p.glow = int(old["seeds"]), int(old["glow"])
            ox, oy = int(old["x"]), int(old["y"])
            if self.tiles[oy][ox] in WALKABLE and (ox, oy) not in self.lanterns \
                    and not self.occupied(ox, oy):
                p.x, p.y = ox, oy
        self.players[p.id] = p
        self.log.append("%s arrived on the isle" % p.name)
        return p

    def remove_player(self, pid):
        p = self.players.pop(pid, None)
        if p:
            self.stash[p.name] = {"x": p.x, "y": p.y, "seeds": p.seeds, "glow": p.glow}
            self.log.append("%s sailed away" % p.name)

    def occupied(self, x, y, ignore=None):
        return any(p.x == x and p.y == y and p.id != ignore for p in self.players.values())

    # ---- commands (each returns a private note string or None) ------------
    def move(self, pid, dx, dy, now=None):
        p = self.players[pid]
        if (dx, dy) not in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            return "Bad move"
        now = time.monotonic() if now is None else now
        if now - p.last_move < 0.08:
            return None
        p.last_move = now
        p.face = [dx, dy]
        nx, ny = p.x + dx, p.y + dy
        if not (0 <= nx < W and 0 <= ny < H):
            return None
        if self.tiles[ny][nx] not in WALKABLE:
            return "The sea is too deep" if self.tiles[ny][nx] == "w" else "A rock blocks the way"
        if (nx, ny) in self.lanterns:
            return "A lantern stands there"
        if self.occupied(nx, ny, pid):
            return None
        p.x, p.y = nx, ny
        return None

    def act(self, pid, a, x, y):
        p = self.players[pid]
        if a not in ACTIONS:
            return "Unknown action"
        if not (isinstance(x, int) and isinstance(y, int) and 0 <= x < W and 0 <= y < H):
            return "Out of bounds"
        if max(abs(x - p.x), abs(y - p.y)) > 1:
            return "Too far away"
        tile = self.tiles[y][x]
        pos = (x, y)
        if a == "dig":
            if tile != "g" and tile != "s":
                return "Can only dig grass or sand"
            if pos in self.plants or pos in self.lanterns or pos in self.signs:
                return "Something is in the way"
            if self.occupied(x, y, pid):
                return "Someone is standing there"
            self.tiles[y][x] = "c"
            self.recompute_wet()
            return None
        if a == "fill":
            if tile != "c":
                return "No channel here"
            self.tiles[y][x] = BASE_MAP[y][x] if BASE_MAP[y][x] in "gs" else "g"
            self.recompute_wet()
            return None
        if a == "plant":
            if tile != "g":
                return "Reeds need grass"
            if pos in self.plants or pos in self.lanterns or pos in self.signs:
                return "Tile is taken"
            if p.seeds < 1:
                return "No seeds left"
            p.seeds -= 1
            self.plants[pos] = {"growth": 0, "by": pid}
            self.log.append("%s planted a reed" % p.name)
            return None
        if a == "harvest":
            pl = self.plants.get(pos)
            if not pl:
                return "Nothing to harvest"
            del self.plants[pos]
            if self.stage(pl) >= 3:
                p.glow += 1
                p.seeds += 2
                self.log.append("%s harvested glow" % p.name)
                return "+1 glow, +2 seeds"
            p.seeds += 1
            return "Uprooted a young reed"
        if a == "lantern":
            if tile != "g" and tile != "s":
                return "Lanterns need solid ground"
            if pos in self.plants or pos in self.lanterns or pos in self.signs:
                return "Tile is taken"
            if self.occupied(x, y):
                return "Stand next to the tile, not on it"
            if p.glow < 2:
                return "Need 2 glow"
            p.glow -= 2
            self.lanterns[pos] = pid
            self.log.append("%s lit a lantern" % p.name)
            self.check_goal()
            return None
        if a == "unlantern":
            if pos not in self.lanterns:
                return "No lantern here"
            del self.lanterns[pos]
            p.glow += 2
            return "Picked up the lantern"
        return None

    def give(self, pid, item):
        p = self.players[pid]
        if item not in ("seed", "glow"):
            return "Unknown item"
        attr = "seeds" if item == "seed" else "glow"
        if getattr(p, attr) < 1:
            return "You have no %s" % item
        near = [o for o in self.players.values()
                if o.id != pid and max(abs(o.x - p.x), abs(o.y - p.y)) <= 2]
        if not near:
            return "Nobody close enough"
        o = near[0]
        setattr(p, attr, getattr(p, attr) - 1)
        setattr(o, attr, getattr(o, attr) + 1)
        self.log.append("%s gave %s a %s" % (p.name, o.name, item))
        return None

    def sign(self, pid, x, y, text):
        """Plant a little wooden signpost with a few words; empty text removes it."""
        p = self.players[pid]
        if not (isinstance(x, int) and isinstance(y, int) and 0 <= x < W and 0 <= y < H):
            return "Out of bounds"
        if max(abs(x - p.x), abs(y - p.y)) > 1:
            return "Too far away"
        pos = (x, y)
        text = " ".join(str(text or "").split())[:24]
        if not text:
            if pos in self.signs:
                del self.signs[pos]
                return "Sign removed"
            return "No sign here"
        if self.tiles[y][x] not in "gs":
            return "Signs need solid ground"
        if pos in self.plants or pos in self.lanterns:
            return "Tile is taken"
        if pos not in self.signs and len(self.signs) >= MAX_SIGNS:
            return "The isle has enough signs"
        self.signs[pos] = {"text": text, "by": pid}
        self.log.append("%s named a place: %s" % (p.name, text))
        return None

    def emote(self, pid, e):
        p = self.players[pid]
        if e not in EMOTES:
            return "Unknown emote"
        p.emote = e
        p.emote_until = self.t + 3.0
        return None

    def chat(self, pid, text):
        p = self.players[pid]
        text = " ".join(str(text).split())[:60]
        if not text:
            return None
        p.say = text
        p.say_until = self.t + 5.0
        self.log.append("%s: %s" % (p.name, text))
        return None

    # ---- simulation -----------------------------------------------------
    def check_goal(self):
        if self.light() >= self.goal:
            self.log.append("The isle is lit! Level %d" % (self.level + 1))
            self.level += 1
            self.goal += 30
            for p in self.players.values():
                p.seeds += 3

    def step(self, dt):
        prev_tide = self.tide()
        self.t += dt
        self.tick += 1
        tide = self.tide()
        d = 1 if tide > prev_tide else -1
        if d != self.tide_dir:
            if self.tide_dir != 0:
                if d > 0:
                    self.log.append("A spring tide is rising" if self.spring() else "Tide is rising")
                else:
                    self.log.append("Tide is ebbing")
            self.tide_dir = d
        self.recompute_wet()
        while self.t - self.last_grow >= 1.0:
            self.last_grow += 1.0
            self.grow()
        for p in self.players.values():
            if p.emote and self.t >= p.emote_until:
                p.emote = ""
            if p.say and self.t >= p.say_until:
                p.say = ""
        self.move_flies(dt)
        self.move_critters()

    # ---- wildlife ---------------------------------------------------------
    def ring_lamps(self):
        """Lanterns standing on the Moonwell's bank (within one tile of the pond)."""
        return sum(1 for (x, y) in self.lanterns
                   if any(max(abs(x - px), abs(y - py)) <= 1 for (px, py) in POND))

    def heron_spots(self):
        spots = []
        for (px, py) in POND:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                pos = (px + dx, py + dy)
                if self.tiles[pos[1]][pos[0]] in "gs" and pos not in self.lanterns \
                        and pos not in self.plants and pos not in self.signs \
                        and not self.occupied(*pos):
                    spots.append(pos)
        return sorted(set(spots))

    def move_critters(self):
        # Koi live in the Moonwell and explore whatever ditch water touches it.
        if self.tick % 3 == 0:
            water = POND | self.wet
            for k in self.koi:
                pos = (k[0], k[1])
                if pos not in water:  # stranded by the ebb: wriggle to the nearest water
                    k[0], k[1] = min(water, key=lambda w: abs(w[0] - pos[0]) + abs(w[1] - pos[1]))
                    continue
                opts = [(pos[0] + dx, pos[1] + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                        if (pos[0] + dx, pos[1] + dy) in water]
                if opts and self.rng.random() < 0.75:
                    k[0], k[1] = self.rng.choice(opts)
        # The heron lands when enough lamps ring the Moonwell.
        ring = self.ring_lamps()
        if self.heron is None and ring >= HERON_LAMPS:
            spots = self.heron_spots()
            if spots:
                self.heron = self.rng.choice(spots)
                self.heron_move_at = self.t + 12.0
                self.log.append("A heron landed by the Moonwell")
                self.check_goal()
        elif self.heron is not None:
            if ring < HERON_LAMPS:
                self.heron = None
                self.log.append("The heron flew off")
            elif self.t >= self.heron_move_at or self.heron in self.lanterns \
                    or self.occupied(*self.heron):
                if self.t >= self.heron_move_at:
                    self.heron_gift()
                spots = self.heron_spots()
                if spots:
                    self.heron = self.rng.choice(spots)
                self.heron_move_at = self.t + 12.0

    def heron_gift(self):
        """As it hops on, the heron leaves a seed for every keeper waiting quietly nearby."""
        hx, hy = self.heron
        for p in self.players.values():
            if max(abs(p.x - hx), abs(p.y - hy)) <= HERON_GIFT_RANGE:
                p.seeds += 1
                self.log.append("The heron left %s a seed" % p.name)

    # ---- persistence ------------------------------------------------------
    def to_save(self):
        stash = dict(self.stash)
        for p in self.players.values():
            stash[p.name] = {"x": p.x, "y": p.y, "seeds": p.seeds, "glow": p.glow}
        return {
            "v": 1, "t": self.t, "level": self.level, "goal": self.goal,
            "tiles": ["".join(r) for r in self.tiles],
            "plants": [[x, y, pl["growth"], pl["by"]] for (x, y), pl in self.plants.items()],
            "lanterns": [[x, y, by] for (x, y), by in self.lanterns.items()],
            "signs": [[x, y, sg["text"], sg["by"]] for (x, y), sg in self.signs.items()],
            "stash": stash, "log": list(self.log),
        }

    def load_save(self, d):
        self.t = float(d.get("t", 0.0))
        self.last_grow = self.t
        self.level = int(d.get("level", 1))
        self.goal = int(d.get("goal", 30))
        tiles = d.get("tiles")
        if tiles and len(tiles) == H and all(len(r) == W for r in tiles):
            self.tiles = [list(r) for r in tiles]
        self.plants = {(x, y): {"growth": g, "by": by} for x, y, g, by in d.get("plants", [])}
        self.lanterns = {(x, y): by for x, y, by in d.get("lanterns", [])}
        self.signs = {(x, y): {"text": t, "by": by} for x, y, t, by in d.get("signs", [])}
        self.stash = dict(d.get("stash", {}))
        self.log.extend(d.get("log", []))
        self.recompute_wet()

    def grow(self):
        changed = False
        for (x, y), pl in self.plants.items():
            if self.stage(pl) >= 3:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if n in self.wet or (0 <= n[0] < W and 0 <= n[1] < H
                                     and self.tiles[n[1]][n[0]] == "w"):
                    pl["growth"] += 1
                    if self.stage(pl) >= 3:
                        changed = True
                    break
        if changed:
            self.log.append("A reed began to glow")
            self.check_goal()

    def move_flies(self, dt):
        targets = list(self.lanterns.keys()) + \
            [pos for pos, pl in self.plants.items() if self.stage(pl) >= 3]
        for f in self.flies:
            f[0] += self.rng.uniform(-1, 1) * dt * 1.5
            f[1] += self.rng.uniform(-1, 1) * dt * 1.5
            if targets:
                tx, ty = min(targets, key=lambda t: (t[0] - f[0]) ** 2 + (t[1] - f[1]) ** 2)
                f[0] += (tx - f[0]) * dt * 0.15
                f[1] += (ty - f[1]) * dt * 0.15
            f[0] = min(W - 2.0, max(1.0, f[0]))
            f[1] = min(H - 2.0, max(1.0, f[1]))

    def snapshot(self):
        return {
            "t": "state", "tick": self.tick,
            "day": round(self.day(), 3), "tide": round(self.tide(), 3), "reach": self.reach(),
            "tiles": ["".join(r) for r in self.tiles],
            "wet": ["".join("1" if (x, y) in self.wet else "0" for x in range(W))
                    for y in range(H)],
            "plants": [{"x": x, "y": y, "stage": self.stage(pl), "by": pl["by"]}
                       for (x, y), pl in sorted(self.plants.items())],
            "lanterns": [{"x": x, "y": y, "by": by} for (x, y), by in sorted(self.lanterns.items())],
            "flies": [{"x": round(f[0], 2), "y": round(f[1], 2)} for f in self.flies],
            "players": [p.snap() for p in self.players.values()],
            "critters": [{"kind": "koi", "x": k[0], "y": k[1]} for k in self.koi]
                        + ([{"kind": "heron", "x": self.heron[0], "y": self.heron[1]}]
                           if self.heron else []),
            "signs": [{"x": x, "y": y, "text": sg["text"], "by": sg["by"]}
                      for (x, y), sg in sorted(self.signs.items())],
            "places": [{"name": "Moonwell", "x": 16.5, "y": 6.0}],
            "ring": self.ring_lamps(),
            "spring": self.spring(),
            "light": self.light(), "goal": self.goal, "level": self.level,
            "log": list(self.log),
        }

    def handle(self, pid, msg, now=None):
        """Dispatch one decoded client message. Returns a list of private replies."""
        t = msg.get("t")
        note = None
        if t == "move":
            note = self.move(pid, msg.get("dx", 0), msg.get("dy", 0), now)
        elif t == "act":
            note = self.act(pid, msg.get("a"), msg.get("x"), msg.get("y"))
        elif t == "give":
            note = self.give(pid, msg.get("item"))
        elif t == "emote":
            note = self.emote(pid, msg.get("e"))
        elif t == "chat":
            note = self.chat(pid, msg.get("text", ""))
        elif t == "sign":
            note = self.sign(pid, msg.get("x"), msg.get("y"), msg.get("text"))
        elif t == "ping":
            return [{"t": "pong"}]
        elif t == "hello":
            name = " ".join(str(msg.get("name", "")).split())[:12]
            if name:
                self.players[pid].name = name
        else:
            note = "Unknown message"
        return [{"t": "note", "text": note}] if note else []


class Server:
    def __init__(self, save_path=None):
        self.world = World()
        self.writers = {}  # pid -> StreamWriter
        self.save_path = save_path
        if save_path and os.path.exists(save_path):
            try:
                with open(save_path) as f:
                    self.world.load_save(json.load(f))
                print("world restored from save", flush=True)
            except Exception as e:
                print("could not restore save: %s" % type(e).__name__, flush=True)

    def save(self):
        if not self.save_path:
            return
        try:
            tmp = self.save_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.world.to_save(), f)
            os.replace(tmp, self.save_path)
        except OSError as e:
            print("save failed: %s" % type(e).__name__, flush=True)

    @staticmethod
    def send(writer, obj):
        try:
            writer.write((json.dumps(obj, separators=(",", ":")) + "\n").encode())
        except Exception:
            pass

    async def on_client(self, reader, writer):
        try:
            line = await asyncio.wait_for(reader.readline(), 15)
            first = json.loads(line.decode("utf-8", "replace")) if line.strip() else {}
        except Exception:
            writer.close()
            return
        name = first.get("name") if isinstance(first, dict) and first.get("t") == "hello" else None
        p = self.world.add_player(" ".join(str(name).split()) if name else None)
        pid = p.id
        self.writers[pid] = writer
        print("player %d joined (%s); %d online" % (pid, p.name, len(self.writers)), flush=True)
        self.send(writer, {"t": "welcome", "id": pid, "w": W, "h": H, "proto": 1})
        self.send(writer, self.world.snapshot())
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                if len(line) > 4096:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                try:
                    for reply in self.world.handle(pid, msg):
                        self.send(writer, reply)
                except Exception as e:  # never let one bad message kill the world
                    print("bad message from player %d: %s" % (pid, type(e).__name__), flush=True)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self.writers.pop(pid, None)
            self.world.remove_player(pid)
            print("player %d left; %d online" % (pid, len(self.writers)), flush=True)
            try:
                writer.close()
            except Exception:
                pass

    async def ticker(self):
        dt = 1.0 / TICK_HZ
        while True:
            await asyncio.sleep(dt)
            self.world.step(dt)
            if self.world.tick % (TICK_HZ * 5) == 0:
                self.save()
            snap = self.world.snapshot()
            for pid, w in list(self.writers.items()):
                if w.transport.get_write_buffer_size() > 1 << 20:
                    continue  # slow client: skip a frame
                self.send(w, snap)

    async def main(self):
        port = int(os.environ.get("AAL_LAN_PORT", "18765"))
        srv = await asyncio.start_server(self.on_client, "", port)
        print("Tidal Lantern Isle server listening (LAN ready)", flush=True)
        loop = asyncio.get_running_loop()
        stop = loop.create_future()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: stop.done() or stop.set_result(None))
        tick = asyncio.ensure_future(self.ticker())
        await stop
        tick.cancel()
        self.save()
        srv.close()  # no wait_closed(): it would block until every keeper hangs up
        for w in list(self.writers.values()):
            w.close()
        print("world saved; server stopped", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(Server(SAVE_PATH).main())
    except KeyboardInterrupt:
        pass
