#!/usr/bin/env python3
"""Lantern Garden — authoritative world server. See PROTOCOL.md."""
import asyncio
import json
import math
import os
import random
import signal
import time

W, H = 854, 480
MIN_X, MAX_X, MIN_Y, MAX_Y = 12, 842, 56, 468
SPEED = 150.0
TOUCH = 16.0
STEP = 30.0
MAX_SEEDS = 8
MAX_BLOOMS = 150
TICK_HZ = 20
RETOUCH_COOLDOWN = 1.5
WILD = "garden"          # the garden itself plants pale wild seeds
WILD_COLOR = [236, 232, 200]
MAX_WILD = 3
SAVE = os.environ.get("AAL_GARDEN_SAVE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "garden_state.json")


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class World:
    def __init__(self):
        self.players = {}   # id -> dict
        self.seeds = {}     # id -> dict
        self.blooms = {}    # id -> dict
        self.msgs = []
        self.next_id = 1
        self.tick = 0
        self.places = {}    # name -> (x, y) remembered across visits
        self.load()

    def load(self):
        try:
            with open(SAVE) as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        now = time.monotonic()
        for s in d.get("seeds", []):
            s["owner"] = 0
            self.seeds[s["id"]] = s
        for b in d.get("blooms", []):
            b.setdefault("last", b["names"][-1])
            b["when"] = now
            self.blooms[b["id"]] = b
        self.msgs = d.get("msgs", [])[-5:]
        self.places = {k: tuple(v) for k, v in d.get("places", {}).items()}
        ids = list(self.seeds) + list(self.blooms)
        self.next_id = max(ids + [0]) + 100

    def save(self):
        for p in self.players.values():
            self.places[p["name"]] = (p["x"], p["y"])
        d = {"seeds": list(self.seeds.values()),
             "blooms": [{k: v for k, v in b.items() if k != "when"}
                        for b in self.blooms.values()],
             "msgs": self.msgs, "places": self.places}
        with open(SAVE + ".tmp", "w") as f:
            json.dump(d, f)
        os.replace(SAVE + ".tmp", SAVE)

    def wild_seed(self):
        """The garden answers a star bloom with a seed of its own."""
        if sum(1 for s in self.seeds.values() if s["name"] == WILD) >= MAX_WILD:
            return
        things = list(self.seeds.values()) + list(self.blooms.values()) \
            + list(self.players.values())
        for _ in range(40):
            x = random.randint(60, W - 60)
            y = random.randint(110, H - 50)
            if all(math.hypot(t["x"] - x, t["y"] - y) > 50 for t in things):
                break
        sid = self.new_id()
        self.seeds[sid] = {"id": sid, "x": x, "y": y, "owner": 0,
                           "name": WILD, "color": list(WILD_COLOR)}
        self.log("*", "The garden planted a wild seed")

    def new_id(self):
        i = self.next_id
        self.next_id += 1
        return i

    def log(self, who, text):
        self.msgs.append({"from": who, "text": text[:60]})
        del self.msgs[:-5]

    def add_player(self, name, shape, color):
        pid = self.new_id()
        n = len(self.players)
        x = 227 + (n % 4) * 133
        y = 250 + (n % 2) * 40
        if name in self.places:
            x, y = self.places[name]
        for s in self.seeds.values():
            if s["name"] == name:
                s["owner"] = pid
        self.players[pid] = {
            "id": pid, "name": name, "shape": shape, "color": color,
            "x": float(x), "y": float(y), "tx": float(x), "ty": float(y),
            "planted": 0, "touched": 0,
        }
        self.log("*", "%s arrived as a %s" % (name, shape))
        return pid

    def remove_player(self, pid):
        p = self.players.pop(pid, None)
        if p:
            self.places[p["name"]] = (p["x"], p["y"])
            self.log("*", "%s left the garden" % p["name"])

    def handle(self, pid, msg):
        p = self.players.get(pid)
        if p is None or not isinstance(msg, dict):
            return
        t = msg.get("t")
        try:
            if t == "move":
                p["tx"] = clamp(float(msg["x"]), MIN_X, MAX_X)
                p["ty"] = clamp(float(msg["y"]), MIN_Y, MAX_Y)
            elif t == "step":
                dx = clamp(float(msg.get("dx", 0)), -1, 1)
                dy = clamp(float(msg.get("dy", 0)), -1, 1)
                p["tx"] = clamp(p["x"] + dx * STEP, MIN_X, MAX_X)
                p["ty"] = clamp(p["y"] + dy * STEP, MIN_Y, MAX_Y)
            elif t == "plant":
                self.plant(p)
            elif t == "say":
                text = str(msg.get("text", "")).strip()
                if text.lower().startswith("name "):
                    self.name_bloom(p, text[5:].strip())
                elif text:
                    self.log(p["name"], text)
        except (KeyError, TypeError, ValueError):
            pass

    def name_bloom(self, p, word):
        """Carve a word into the nearest bloom this player helped make."""
        word = "".join(c for c in word if 32 <= ord(c) < 127)[:14]
        near = [b for b in self.blooms.values()
                if p["name"] in b["names"]
                and math.hypot(b["x"] - p["x"], b["y"] - p["y"]) <= TOUCH + 6]
        if not word or not near:
            self.log("*", "%s: stand on a bloom you touched to name it"
                     % p["name"])
            return
        b = min(near, key=lambda b: math.hypot(b["x"] - p["x"],
                                               b["y"] - p["y"]))
        b["word"] = word
        self.log("*", "%s named a bloom: %s" % (p["name"], word))

    def plant(self, p):
        mine = [s for s in self.seeds.values() if s["name"] == p["name"]]
        if len(mine) >= MAX_SEEDS:
            return
        for s in self.seeds.values():
            if math.hypot(s["x"] - p["x"], s["y"] - p["y"]) < 10:
                return
        sid = self.new_id()
        self.seeds[sid] = {"id": sid, "x": round(p["x"]), "y": round(p["y"]),
                           "owner": p["id"], "name": p["name"],
                           "color": p["color"]}
        p["planted"] += 1

    def step(self, dt):
        self.tick += 1
        now = time.monotonic()
        for p in self.players.values():
            dx, dy = p["tx"] - p["x"], p["ty"] - p["y"]
            d = math.hypot(dx, dy)
            if d > 0.01:
                m = min(d, SPEED * dt)
                p["x"] += dx / d * m
                p["y"] += dy / d * m
        for p in self.players.values():
            # wake seeds planted by someone else
            for sid, s in list(self.seeds.items()):
                if s["name"] == p["name"]:
                    continue
                if math.hypot(s["x"] - p["x"], s["y"] - p["y"]) <= TOUCH:
                    del self.seeds[sid]
                    bid = self.new_id()
                    color = [(a + b) // 2 for a, b in zip(s["color"], p["color"])]
                    self.blooms[bid] = {
                        "id": bid, "x": s["x"], "y": s["y"], "color": color,
                        "names": [s["name"], p["name"]], "level": 2,
                        "last": p["name"], "when": now,
                    }
                    p["touched"] += 1
                    self.log("*", "%s woke %s's seed" % (p["name"], s["name"]))
                    if len(self.blooms) > MAX_BLOOMS:
                        oldest = min(self.blooms)
                        del self.blooms[oldest]
            # change blooms someone else touched last
            for b in self.blooms.values():
                if b["last"] == p["name"] or now - b["when"] < RETOUCH_COOLDOWN:
                    continue
                if math.hypot(b["x"] - p["x"], b["y"] - p["y"]) <= TOUCH:
                    b["last"] = p["name"]
                    b["when"] = now
                    b["color"] = [(2 * a + c) // 3
                                  for a, c in zip(b["color"], p["color"])]
                    if p["name"] not in b["names"]:
                        b["names"].append(p["name"])
                        was = b["level"]
                        real = [n for n in b["names"] if n != WILD]
                        b["level"] = max(2, min(4, len(real)))
                        p["touched"] += 1
                        if b["level"] >= 4 and was < 4:
                            self.log("*", "A star bloom! All four touched it")
                            self.wild_seed()
                        elif b["level"] >= 4:
                            pass
                        else:
                            self.log("*", "%s joined a bloom (%d names)"
                                     % (p["name"], b["level"]))

    def snapshot(self):
        return {
            "t": "state", "tick": self.tick,
            "glow": sum(b["level"] for b in self.blooms.values()),
            "players": [{"id": p["id"], "name": p["name"], "shape": p["shape"],
                         "color": p["color"], "x": round(p["x"], 1),
                         "y": round(p["y"], 1), "planted": p["planted"],
                         "touched": p["touched"]}
                        for p in self.players.values()],
            "seeds": list(self.seeds.values()),
            "blooms": [{"id": b["id"], "x": b["x"], "y": b["y"],
                        "color": b["color"], "names": b["names"],
                        "level": b["level"], "word": b.get("word", "")}
                       for b in self.blooms.values()],
            "msgs": list(self.msgs),
        }


world = World()
writers = {}  # pid -> StreamWriter


def clean_color(c):
    try:
        c = [int(clamp(int(v), 0, 255)) for v in c][:3]
        if len(c) == 3:
            return c
    except (TypeError, ValueError):
        pass
    return [220, 220, 220]


async def client(reader, writer):
    pid = None
    try:
        line = await asyncio.wait_for(reader.readline(), 30)
        hello = json.loads(line.decode("utf-8", "replace"))
        if not isinstance(hello, dict) or hello.get("t") != "hello":
            return
        name = str(hello.get("name", "guest"))[:12] or "guest"
        shape = str(hello.get("shape", "circle"))[:12] or "circle"
        pid = world.add_player(name, shape, clean_color(hello.get("color")))
        writer.write((json.dumps({"t": "welcome", "id": pid, "w": W, "h": H})
                      + "\n").encode())
        writers[pid] = writer
        print("player joined:", name, flush=True)
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                world.handle(pid, json.loads(line.decode("utf-8", "replace")))
            except ValueError:
                continue
    except (asyncio.TimeoutError, ConnectionError, ValueError, OSError):
        pass
    finally:
        if pid is not None:
            writers.pop(pid, None)
            world.remove_player(pid)
            print("player left", flush=True)
        try:
            writer.close()
        except Exception:
            pass


async def loop():
    dt = 1.0 / TICK_HZ
    n = 0
    while True:
        await asyncio.sleep(dt)
        world.step(dt)
        n += 1
        if n % (TICK_HZ * 10) == 0:
            try:
                world.save()  # autosave so the garden outlives a hard stop
            except OSError:
                pass
        if n % 2 == 0:
            data = (json.dumps(world.snapshot()) + "\n").encode()
            for pid, w in list(writers.items()):
                try:
                    if w.transport.get_write_buffer_size() < 262144:
                        w.write(data)
                except Exception:
                    writers.pop(pid, None)


async def main():
    port = int(os.environ.get("AAL_LAN_PORT", "18765"))
    server = await asyncio.start_server(client, "", port)
    print("Lantern Garden server up", flush=True)
    stop = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
    async with server:
        task = asyncio.ensure_future(loop())
        await stop.wait()
        task.cancel()
        world.save()
        print("garden saved", flush=True)
        os._exit(0)  # do not wait for open connections to drain


if __name__ == "__main__":
    asyncio.run(main())
