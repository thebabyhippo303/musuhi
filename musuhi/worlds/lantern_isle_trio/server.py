#!/usr/bin/env python3
"""Lantern Isle — authoritative world server (see PROTOCOL.md)."""
import json
import os
import random
import selectors
import socket
import time

W, H = 40, 20
WALKABLE = set(".=*L")
TILES = set(".=*L~#T^")
EMOTES = {"wave", "heart", "dance", "sleep", "!", "?"}
SIDES = ("p1", "p2", "p3")
DEFAULT_NAMES = {"p1": "Laptop", "p2": "MiniPC", "p3": "Desktop"}
SPAWNS = {"p1": (18, 10), "p2": (20, 10), "p3": (22, 10)}
MAX_SPARKS = 6
GOAL = 25
DAY_SECONDS = 240.0
REACH = 3


def make_world(seed=7):
    rng = random.Random(seed)
    g = [["." for _ in range(W)] for _ in range(H)]
    # sea border with a wobbly shoreline
    for y in range(H):
        for x in range(W):
            edge = min(x, y, W - 1 - x, H - 1 - y)
            if edge == 0 or (edge == 1 and rng.random() < 0.45):
                g[y][x] = "~"
    # a pond
    for y in range(4, 8):
        for x in range(28, 34):
            if (x - 30.5) ** 2 / 9 + (y - 5.5) ** 2 / 3 <= 1.0:
                g[y][x] = "~"
    # groves, rocks, flowers
    for _ in range(46):
        x, y = rng.randrange(2, W - 2), rng.randrange(2, H - 2)
        if g[y][x] == ".":
            g[y][x] = "T"
    for _ in range(14):
        x, y = rng.randrange(2, W - 2), rng.randrange(2, H - 2)
        if g[y][x] == ".":
            g[y][x] = "^"
    for _ in range(30):
        x, y = rng.randrange(2, W - 2), rng.randrange(2, H - 2)
        if g[y][x] == ".":
            g[y][x] = "*"
    # central plaza with crossing paths and four lanterns
    for x in range(4, W - 4):
        g[10][x] = "="
    for y in range(3, H - 3):
        g[y][20] = "="
    for y in range(8, 13):
        for x in range(16, 25):
            g[y][x] = "="
    for x, y in ((16, 8), (24, 8), (16, 12), (24, 12)):
        g[y][x] = "L"
    return g


class Client:
    def __init__(self, sock):
        self.sock = sock
        self.inbuf = b""
        self.outbuf = b""
        self.side = None


def load_chart(path):
    """Read a saved chart: 20 plain rows of 40 tiles, or JSON with a "tiles" list."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        data = json.loads(text)
        rows = data["tiles"] if isinstance(data, dict) else data
    except ValueError:
        rows = text.splitlines()
    rows = [str(r) for r in rows if str(r).strip()]
    if len(rows) != H or any(len(r) != W or set(r) - TILES for r in rows):
        raise ValueError("chart must be %d rows of %d known tiles" % (H, W))
    return [list(r) for r in rows]


class World:
    def __init__(self, grid=None):
        self.grid = grid or make_world()
        self.players = {}
        for s in SIDES:
            x, y = SPAWNS[s]
            self.players[s] = {"x": x, "y": y, "name": DEFAULT_NAMES[s], "online": False,
                               "emote": "", "sparks": 0}
        self.emote_until = {s: 0.0 for s in SIDES}
        self.sparks = []
        self.score = 0
        self.chat = []
        self.chat_n = 0
        self.t0 = time.time()
        self.next_spark = 0.0
        self.rng = random.Random()

    def rows(self):
        return ["".join(r) for r in self.grid]

    def clock(self):
        return round(((time.time() - self.t0) / DAY_SECONDS) % 1.0, 3)

    def occupied(self, x, y):
        return any(p["online"] and p["x"] == x and p["y"] == y for p in self.players.values())

    def state_msg(self):
        return {"t": "state", "players": self.players, "sparks": self.sparks,
                "score": self.score, "clock": self.clock(), "goal": GOAL}


class Server:
    def __init__(self, port=None, grid=None):
        self.port = int(os.environ.get("AAL_LAN_PORT", "18765")) if port is None else port
        self.world = World(grid)
        self.sel = selectors.DefaultSelector()
        self.clients = {}      # sock -> Client
        self.by_side = {}      # side -> Client
        self.dirty = False
        self.lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.lsock.bind(("", self.port))
        self.lsock.listen(16)
        self.lsock.setblocking(False)
        self.sel.register(self.lsock, selectors.EVENT_READ)
        self.running = True

    # ---- output helpers -------------------------------------------------
    def send(self, c, msg):
        c.outbuf += (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
        self.flush(c)

    def flush(self, c):
        if not c.outbuf:
            return
        try:
            n = c.sock.send(c.outbuf)
            c.outbuf = c.outbuf[n:]
        except (BlockingIOError, InterruptedError):
            pass
        except OSError:
            self.drop(c)
            return
        if len(c.outbuf) > 4_000_000:
            self.drop(c)

    def broadcast(self, msg):
        for c in list(self.clients.values()):
            if c.side:
                self.send(c, msg)

    def say(self, frm, name, text):
        w = self.world
        w.chat_n += 1
        m = {"t": "chat", "from": frm, "name": name, "text": text, "n": w.chat_n}
        w.chat.append(m)
        del w.chat[:-30]
        self.broadcast(m)
        print("CHAT %s: %s" % (name, text), flush=True)

    def drop(self, c):
        if c.sock not in self.clients:
            return
        del self.clients[c.sock]
        try:
            self.sel.unregister(c.sock)
        except (KeyError, ValueError):
            pass
        try:
            c.sock.close()
        except OSError:
            pass
        if c.side and self.by_side.get(c.side) is c:
            del self.by_side[c.side]
            p = self.world.players[c.side]
            p["online"] = False
            self.say("sys", "Isle", "%s left the isle." % p["name"])
            self.dirty = True

    # ---- message handling -----------------------------------------------
    def handle(self, c, msg):
        w = self.world
        t = msg.get("t")
        if t == "ping":
            self.send(c, {"t": "pong"})
            return
        if t == "hello":
            side = msg.get("side")
            if side not in SIDES:
                self.send(c, {"t": "err", "text": "side must be p1, p2 or p3"})
                return
            old = self.by_side.get(side)
            if old is not None and old is not c:
                old.side = None
                self.drop(old)
            c.side = side
            self.by_side[side] = c
            p = w.players[side]
            name = str(msg.get("name") or "").strip()[:16]
            if name:
                p["name"] = name
            p["online"] = True
            if w.grid[p["y"]][p["x"]] not in WALKABLE:
                p["x"], p["y"] = SPAWNS[side]
                w.grid[p["y"]][p["x"]] = "="
            self.send(c, {"t": "welcome", "side": side, "w": W, "h": H, "tiles": w.rows(),
                          "players": w.players, "sparks": w.sparks, "score": w.score,
                          "chat": w.chat, "clock": w.clock(), "goal": GOAL})
            self.say("sys", "Isle", "%s (%s) arrived on the isle." % (p["name"], side))
            self.dirty = True
            return
        if not c.side:
            self.send(c, {"t": "err", "text": "say hello first"})
            return
        p = w.players[c.side]
        if t == "move":
            try:
                dx, dy = int(msg.get("dx", 0)), int(msg.get("dy", 0))
            except (TypeError, ValueError):
                return
            dx, dy = max(-1, min(1, dx)), max(-1, min(1, dy))
            if dx == 0 and dy == 0:
                return
            nx, ny = p["x"] + dx, p["y"] + dy
            if 0 <= nx < W and 0 <= ny < H and w.grid[ny][nx] in WALKABLE:
                p["x"], p["y"] = nx, ny
                if [nx, ny] in w.sparks:
                    w.sparks.remove([nx, ny])
                    p["sparks"] += 1
                    w.score += 1
                    if w.score % GOAL == 0:
                        self.bloom(nx, ny)
                        self.say("sys", "Isle", "The isle glows! Team reached %d sparks - "
                                 "flowers bloom around %s." % (w.score, p["name"]))
                self.dirty = True
        elif t == "place":
            try:
                x, y = int(msg.get("x")), int(msg.get("y"))
            except (TypeError, ValueError):
                return
            tile = msg.get("tile")
            if tile not in TILES or not (0 <= x < W and 0 <= y < H):
                self.send(c, {"t": "err", "text": "bad tile or position"})
                return
            if max(abs(x - p["x"]), abs(y - p["y"])) > REACH:
                self.send(c, {"t": "err", "text": "too far - build within 3 tiles"})
                return
            if tile not in WALKABLE and w.occupied(x, y):
                self.send(c, {"t": "err", "text": "someone is standing there"})
                return
            if w.grid[y][x] != tile:
                w.grid[y][x] = tile
                if tile not in WALKABLE and [x, y] in w.sparks:
                    w.sparks.remove([x, y])
                self.broadcast({"t": "tile", "x": x, "y": y, "tile": tile, "by": c.side})
                self.dirty = True
        elif t == "chat":
            text = " ".join(str(msg.get("text", "")).split())[:200]
            if text:
                self.say(c.side, p["name"], text)
        elif t == "emote":
            e = msg.get("e")
            if e in EMOTES:
                p["emote"] = e
                w.emote_until[c.side] = time.time() + 4.0
                self.dirty = True

    def bloom(self, cx, cy):
        w = self.world
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                x, y = cx + dx, cy + dy
                if max(abs(dx), abs(dy)) == 2 and 0 <= x < W and 0 <= y < H \
                        and w.grid[y][x] == ".":
                    w.grid[y][x] = "*"
                    self.broadcast({"t": "tile", "x": x, "y": y, "tile": "*", "by": "sys"})

    # ---- periodic work --------------------------------------------------
    def tick(self, now):
        w = self.world
        for s in SIDES:
            if w.players[s]["emote"] and now > w.emote_until[s]:
                w.players[s]["emote"] = ""
                self.dirty = True
        if len(w.sparks) < MAX_SPARKS and now >= w.next_spark:
            for _ in range(40):
                x, y = w.rng.randrange(W), w.rng.randrange(H)
                if w.grid[y][x] in WALKABLE and [x, y] not in w.sparks \
                        and not w.occupied(x, y):
                    w.sparks.append([x, y])
                    self.dirty = True
                    break
            w.next_spark = now + 2.5

    def on_readable(self, c):
        try:
            data = c.sock.recv(65536)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""
        if not data:
            self.drop(c)
            return
        c.inbuf += data
        if len(c.inbuf) > 1_000_000:
            self.drop(c)
            return
        while b"\n" in c.inbuf:
            line, c.inbuf = c.inbuf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self.send(c, {"t": "err", "text": "bad json"})
                continue
            if isinstance(msg, dict):
                try:
                    self.handle(c, msg)
                except Exception as e:  # never let one bad message kill the world
                    print("handler error: %s" % type(e).__name__, flush=True)
            if c.sock not in self.clients:
                return

    def serve_forever(self):
        print("Lantern Isle server listening. PHASE: SERVER READY", flush=True)
        last_state = 0.0
        while self.running:
            for key, _ in self.sel.select(timeout=0.05):
                if key.fileobj is self.lsock:
                    try:
                        sock, _addr = self.lsock.accept()
                    except OSError:
                        continue
                    sock.setblocking(False)
                    try:
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    except OSError:
                        pass
                    c = Client(sock)
                    self.clients[sock] = c
                    self.sel.register(sock, selectors.EVENT_READ)
                    print("client connected (%d total)" % len(self.clients), flush=True)
                else:
                    c = self.clients.get(key.fileobj)
                    if c:
                        self.on_readable(c)
            now = time.time()
            self.tick(now)
            if self.dirty or now - last_state >= 0.2:
                self.broadcast(self.world.state_msg())
                self.dirty = False
                last_state = now
            for c in list(self.clients.values()):
                if c.outbuf:
                    self.flush(c)

    def close(self):
        self.running = False
        for c in list(self.clients.values()):
            try:
                c.sock.close()
            except OSError:
                pass
        self.lsock.close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--load", help="optional saved chart to start the isle from")
    args = ap.parse_args()
    grid = None
    if args.load:
        try:
            grid = load_chart(args.load)
            print("Saved chart loaded.", flush=True)
        except (OSError, ValueError, KeyError, TypeError) as e:
            print("Saved chart not usable (%s) - starting a fresh isle." % type(e).__name__,
                  flush=True)
    srv = Server(grid=grid)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()
