#!/usr/bin/env python3
"""Tidal Atlas - authoritative world server.

Two lighthouse surveyors chart a night island, plant signal gardens,
light the lighthouses and bury notes for each other to discover.
Wire format: one JSON object per line over TCP. See PROTOCOL.md.
"""
import asyncio
import json
import math
import os
import re
import time

W, H = 24, 12
TICK_HZ = 5
TIDE_PERIOD = 60.0          # seconds for one full tide cycle
TIDE_LOW, TIDE_HIGH = 0.5, 2.5
GROW_SECONDS = 6.0          # dry seconds per garden stage
MOVE_INTERVAL = 0.07        # min seconds between moves per player
MAX_TEXT = 80
MAX_GARDENS = 60
MAX_NOTES = 40
LIGHTHOUSES = [(4, 5), (19, 6)]
SPAWNS = [(5, 5), (18, 6), (11, 5), (12, 6)]

_ADDR_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}|(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}")


def clean_text(text):
    """Trim chat/note text and scrub anything that looks like an address."""
    text = "".join(ch for ch in str(text) if ch.isprintable())
    text = _ADDR_RE.sub("[hidden]", text)
    return text.strip()[:MAX_TEXT]


def make_elevation():
    """Deterministic island: 0 sea, 1 tidal flat, 2 shore, 3 high ground."""
    rows = []
    for y in range(H):
        row = []
        for x in range(W):
            d = ((x - 11.5) / 12.0) ** 2 + ((y - 5.5) / 6.0) ** 2
            v = 1.0 - d + 0.14 * math.sin(x * 0.9) * math.cos(y * 1.3)
            v += 0.06 * math.sin(x * 2.3 + y * 1.7)
            if x in (0, W - 1) or y in (0, H - 1):
                e = 0
            elif v > 0.62:
                e = 3
            elif v > 0.38:
                e = 2
            elif v > 0.12:
                e = 1
            else:
                e = 0
            row.append(e)
        rows.append(row)
    for lx, ly in LIGHTHOUSES:
        rows[ly][lx] = 3
    for sx, sy in SPAWNS:
        rows[sy][sx] = 3
    return rows


class World:
    def __init__(self, now=0.0):
        self.elev = make_elevation()
        self.t0 = now
        self.now = now
        self.tick = 0
        self.players = {}       # id -> dict
        self.gardens = {}       # (x, y) -> dict
        self.notes = []         # dicts with hidden flag
        self.lights = {pos: False for pos in LIGHTHOUSES}
        self.charted = set()
        self.log = []
        self.next_id = 1
        self.walkable_total = sum(
            1 for y in range(H) for x in range(W)
            if self.elev[y][x] >= 1 and (x, y) not in self.lights)

    # ---- environment -------------------------------------------------
    def tide(self):
        phase = (self.now - self.t0) / TIDE_PERIOD * 2 * math.pi
        mid = (TIDE_LOW + TIDE_HIGH) / 2
        amp = (TIDE_HIGH - TIDE_LOW) / 2
        return mid - amp * math.cos(phase)

    def flooded(self, x, y):
        return self.elev[y][x] < self.tide()

    def say(self, line):
        self.log.append(line)
        del self.log[:-5]

    # ---- players -----------------------------------------------------
    def add_player(self, name, color):
        pid = self.next_id
        self.next_id += 1
        taken = {(p["x"], p["y"]) for p in self.players.values()}
        spot = next((s for s in SPAWNS if s not in taken), SPAWNS[0])
        name = clean_text(name)[:16] or "Surveyor %d" % pid
        color = clean_text(color)[:16] or "white"
        self.players[pid] = {"id": pid, "name": name, "color": color,
                             "x": spot[0], "y": spot[1], "last_move": -1.0}
        self.charted.add(spot)
        self.say("%s arrives on the island." % name)
        return pid

    def remove_player(self, pid):
        p = self.players.pop(pid, None)
        if p:
            self.say("%s leaves the island." % p["name"])

    def move(self, pid, dx, dy):
        p = self.players[pid]
        if dx not in (-1, 0, 1) or dy not in (-1, 0, 1) or (dx == 0 and dy == 0):
            return False
        if self.now - p["last_move"] < MOVE_INTERVAL:
            return False
        nx, ny = p["x"] + dx, p["y"] + dy
        if not (0 <= nx < W and 0 <= ny < H):
            return False
        if self.elev[ny][nx] == 0 or (nx, ny) in self.lights:
            return False
        # Dry feet may not step into flood water, but a surveyor caught
        # by the tide may wade through the shallows to get out.
        if self.flooded(nx, ny) and not self.flooded(p["x"], p["y"]):
            return False
        p["x"], p["y"], p["last_move"] = nx, ny, self.now
        self.charted.add((nx, ny))
        self._discover(p)
        return True

    def _discover(self, p):
        for n in self.notes:
            if n["hidden"] and n["by_id"] != p["id"] and (n["x"], n["y"]) == (p["x"], p["y"]):
                n["hidden"] = False
                n["found_by"] = p["name"]
                self.say("%s found a note from %s." % (p["name"], n["by"]))

    def plant(self, pid):
        p = self.players[pid]
        pos = (p["x"], p["y"])
        if pos in self.gardens or self.flooded(*pos) or len(self.gardens) >= MAX_GARDENS:
            return False
        self.gardens[pos] = {"x": pos[0], "y": pos[1], "owner": pid,
                             "stage": 0, "dry": 0.0}
        self.say("%s planted a signal garden." % p["name"])
        return True

    def bury(self, pid, text):
        p = self.players[pid]
        text = clean_text(text)
        if not text or self.flooded(p["x"], p["y"]) or len(self.notes) >= MAX_NOTES:
            return False
        if any((n["x"], n["y"]) == (p["x"], p["y"]) for n in self.notes):
            return False
        self.notes.append({"x": p["x"], "y": p["y"], "by": p["name"],
                           "by_id": pid, "text": text, "hidden": True})
        self.say("%s buried something." % p["name"])
        return True

    def light(self, pid):
        p = self.players[pid]
        for (lx, ly), lit in self.lights.items():
            if not lit and max(abs(lx - p["x"]), abs(ly - p["y"])) <= 1:
                self.lights[(lx, ly)] = True
                self.say("%s lit a lighthouse." % p["name"])
                if all(self.lights.values()):
                    self.say("Both lighthouses burn across the water.")
                return True
        return False

    def chat(self, pid, text):
        text = clean_text(text)
        if not text:
            return False
        self.say("%s: %s" % (self.players[pid]["name"], text))
        return True

    def hum(self, pid):
        p = self.players.get(pid)
        if not p:
            return 0
        best = 0
        for n in self.notes:
            if n["hidden"] and n["by_id"] != pid:
                d = max(abs(n["x"] - p["x"]), abs(n["y"] - p["y"]))
                best = max(best, 3 if d <= 1 else 2 if d <= 3 else 1 if d <= 6 else 0)
        return best

    # ---- simulation --------------------------------------------------
    def step(self, now):
        dt = max(0.0, now - self.now)
        self.now = now
        self.tick += 1
        for g in self.gardens.values():
            if g["stage"] < 3 and not self.flooded(g["x"], g["y"]):
                g["dry"] += dt
                if g["dry"] >= GROW_SECONDS:
                    g["dry"] = 0.0
                    g["stage"] += 1

    def handle(self, pid, msg):
        """Apply one client message. Returns an error string or None."""
        t = msg.get("t")
        try:
            if t == "move":
                self.move(pid, int(msg.get("dx", 0)), int(msg.get("dy", 0)))
            elif t == "plant":
                self.plant(pid)
            elif t == "note":
                self.bury(pid, msg.get("text", ""))
            elif t == "light":
                self.light(pid)
            elif t == "say":
                self.chat(pid, msg.get("text", ""))
        except (TypeError, ValueError):
            return "bad fields for %s" % t
        return None

    def welcome(self, pid):
        return {"t": "welcome", "id": pid, "w": W, "h": H,
                "elev": ["".join(str(e) for e in row) for row in self.elev]}

    def snapshot(self, pid):
        pct = int(round(100.0 * len(self.charted) / max(1, self.walkable_total)))
        return {
            "t": "state", "tick": self.tick, "tide": round(self.tide(), 3),
            "players": [{k: p[k] for k in ("id", "name", "color", "x", "y")}
                        for p in self.players.values()],
            "gardens": [{k: g[k] for k in ("x", "y", "owner", "stage")}
                        for g in self.gardens.values()],
            "notes": [{"x": n["x"], "y": n["y"], "by": n["by"], "text": n["text"]}
                      for n in self.notes if not n["hidden"]],
            "lights": [{"x": x, "y": y, "lit": lit}
                       for (x, y), lit in self.lights.items()],
            "charted": min(100, pct),
            "chart": ["".join("1" if (x, y) in self.charted else "0"
                              for x in range(W)) for y in range(H)],
            "hum": self.hum(pid),
            "log": list(self.log),
        }


class Server:
    def __init__(self):
        self.world = World(time.monotonic())
        self.clients = {}       # pid -> writer

    async def on_client(self, reader, writer):
        pid = None
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                if len(line) > 4096:
                    continue
                try:
                    msg = json.loads(line)
                    if not isinstance(msg, dict):
                        raise ValueError
                except ValueError:
                    self.send(writer, {"t": "error", "msg": "not a JSON object"})
                    continue
                if pid is None:
                    if msg.get("t") != "hello":
                        self.send(writer, {"t": "error", "msg": "send hello first"})
                        continue
                    pid = self.world.add_player(msg.get("name", ""), msg.get("color", ""))
                    self.clients[pid] = writer
                    self.send(writer, self.world.welcome(pid))
                    print("player %d joined" % pid, flush=True)
                    continue
                self.world.now = time.monotonic()
                err = self.world.handle(pid, msg)
                if err:
                    self.send(writer, {"t": "error", "msg": err})
        except (ConnectionError, asyncio.IncompleteReadError, ValueError):
            pass
        finally:
            if pid is not None:
                self.clients.pop(pid, None)
                self.world.remove_player(pid)
                print("player %d left" % pid, flush=True)
            try:
                writer.close()
            except Exception:
                pass

    @staticmethod
    def send(writer, obj):
        try:
            writer.write((json.dumps(obj, separators=(",", ":")) + "\n").encode())
        except Exception:
            pass

    async def ticker(self):
        while True:
            await asyncio.sleep(1.0 / TICK_HZ)
            self.world.step(time.monotonic())
            for pid, writer in list(self.clients.items()):
                if writer.transport.get_write_buffer_size() < 262144:
                    self.send(writer, self.world.snapshot(pid))

    async def start(self, port):
        srv = await asyncio.start_server(self.on_client, "", port)
        asyncio.ensure_future(self.ticker())
        return srv


async def main():
    port = int(os.environ.get("AAL_LAN_PORT", "18765"))
    srv = await Server().start(port)
    print("Tidal Atlas server listening for LAN players", flush=True)
    async with srv:
        await srv.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
