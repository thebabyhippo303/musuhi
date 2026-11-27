#!/usr/bin/env python3
"""Lantern Garden — authoritative world server (see PROTOCOL.md)."""
import json
import os
import random
import selectors
import signal
import socket
import time

W, H = 26, 13
TICK_HZ = 5
GROW_TICKS = 30          # ticks per growth stage (halved when tended)
GOAL = 12                # first goal; grows by GOAL each time it is reached
WIND_TICKS = 225         # a gust every ~45 s once the first goal is reached
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "garden_state.json")
COLORS = [(255, 180, 60), (90, 200, 255), (200, 130, 255), (130, 230, 140)]


class Player:
    def __init__(self, pid):
        self.id = pid
        self.name = "P%d" % pid
        self.x, self.y = (4, 6) if pid % 2 else (W - 5, 6)
        self.color = COLORS[(pid - 1) % len(COLORS)]
        self.say = ""
        self.say_until = 0
        self.seeds = 8
        self.lit = 0
        self.goto = None
        self.joined = False


class World:
    def __init__(self):
        self.tick = 0
        self.players = {}
        self.plants = {}     # (x, y) -> {"stage", "owner", "age"}
        self.plaques = {}    # (x, y) -> text
        self.roster = {}     # name -> saved player fields (survives reconnects)
        self.next_id = 1
        self.goal = GOAL
        self.chapter = 0
        self.wind_tick = None
        self.wind_at = None
        self.rng = random.Random()

    def add_player(self):
        p = Player(self.next_id)
        self.next_id += 1
        self.players[p.id] = p
        return p

    def remove_player(self, pid):
        p = self.players.pop(pid, None)
        if p is not None and p.joined:
            self.roster[p.name] = self._player_record(p)

    @staticmethod
    def _player_record(p):
        return {"id": p.id, "x": p.x, "y": p.y, "seeds": p.seeds, "lit": p.lit,
                "color": list(p.color)}

    def to_dict(self):
        roster = dict(self.roster)
        for p in self.players.values():
            if p.joined:
                roster[p.name] = self._player_record(p)
        return {"tick": self.tick, "next_id": self.next_id, "goal": self.goal,
                "chapter": self.chapter, "roster": roster,
                "plants": [dict(pl, x=x, y=y) for (x, y), pl in self.plants.items()],
                "plaques": [{"x": x, "y": y, "text": t}
                            for (x, y), t in self.plaques.items()]}

    def load_dict(self, d):
        self.tick = int(d.get("tick", 0))
        self.next_id = int(d.get("next_id", 1))
        self.goal = int(d.get("goal", GOAL))
        self.chapter = int(d.get("chapter", 0))
        self.roster = dict(d.get("roster", {}))
        for pl in d.get("plants", []):
            self.plants[(pl["x"], pl["y"])] = {
                "stage": pl["stage"], "owner": pl["owner"], "age": pl.get("age", 0),
                "color": pl["color"], "rung": pl.get("rung")}
        for q in d.get("plaques", []):
            self.plaques[(q["x"], q["y"])] = q["text"]

    def glow(self):
        return sum(1 for pl in self.plants.values() if pl["stage"] == 4)

    def handle(self, p, msg):
        t = msg.get("t")
        if t == "join":
            name = str(msg.get("name", ""))[:12].strip()
            if name:
                p.name = name
            p.joined = True
            rec = self.roster.get(p.name)
            if rec:
                p.x, p.y = rec["x"], rec["y"]
                p.seeds, p.lit = rec["seeds"], rec["lit"]
                p.color = tuple(rec["color"])
                old = rec.get("id")
                if old and old != p.id and old not in self.players:
                    del self.players[p.id]
                    p.id = old
                    self.players[old] = p
        elif t == "name":
            text = str(msg.get("text", ""))[:24].strip()
            if text:
                self.plaques[(p.x, p.y)] = text
            else:
                self.plaques.pop((p.x, p.y), None)
        elif t == "move":
            p.goto = None
            self._step(p, _sign(msg.get("dx", 0)), _sign(msg.get("dy", 0)))
        elif t == "goto":
            try:
                gx, gy = int(msg["x"]), int(msg["y"])
            except (KeyError, TypeError, ValueError):
                return
            if 0 <= gx < W and 0 <= gy < H:
                p.goto = (gx, gy)
        elif t == "act":
            self._act(p)
        elif t == "say":
            p.say = str(msg.get("text", ""))[:40]
            p.say_until = self.tick + 6 * TICK_HZ

    def _step(self, p, dx, dy):
        nx, ny = p.x + dx, p.y + dy
        if 0 <= nx < W and 0 <= ny < H:
            p.x, p.y = nx, ny

    def _act(self, p):
        pos = (p.x, p.y)
        plant = self.plants.get(pos)
        if plant is None:
            if p.seeds > 0:
                p.seeds -= 1
                self.plants[pos] = {"stage": 0, "owner": p.id, "age": 0,
                                    "color": list(p.color), "rung": None}
        elif plant["stage"] == 3:
            plant["stage"] = 4
            plant["rung"] = self.tick
            p.lit += 1
            p.seeds += 1
        elif plant["stage"] == 4:
            plant["rung"] = self.tick

    def step(self):
        self.tick += 1
        for p in self.players.values():
            if p.goto:
                gx, gy = p.goto
                if (p.x, p.y) == (gx, gy):
                    p.goto = None
                else:
                    self._step(p, _sign(gx - p.x), _sign(gy - p.y))
            if p.say and self.tick >= p.say_until:
                p.say = ""
        for (x, y), plant in self.plants.items():
            if plant["stage"] >= 3:
                continue
            tended = any(abs(p.x - x) <= 1 and abs(p.y - y) <= 1
                         for p in self.players.values())
            plant["age"] += 2 if tended else 1
            if plant["age"] >= GROW_TICKS:
                plant["age"] = 0
                plant["stage"] += 1
        if self.glow() >= self.goal:
            self.chapter += 1
            self.goal += GOAL
        if self.chapter > 0 and self.tick % WIND_TICKS == 0:
            self._gust()

    def _gust(self):
        """Wind snuffs one untended lantern back to a bloom."""
        far = [pos for pos, pl in self.plants.items()
               if pl["stage"] == 4 and not any(
                   abs(p.x - pos[0]) <= 2 and abs(p.y - pos[1]) <= 2
                   for p in self.players.values())]
        self.wind_tick = self.tick
        self.wind_at = None
        if far:
            pos = self.rng.choice(far)
            self.plants[pos]["stage"] = 3
            self.wind_at = pos

    def night(self):
        dark = 0.3 + 0.15 * self.chapter - 0.6 * self.glow() / float(self.goal)
        return round(max(0.0, min(1.0, dark)), 3)

    def snapshot(self):
        return {
            "t": "state", "tick": self.tick,
            "players": [{"id": p.id, "name": p.name, "x": p.x, "y": p.y,
                         "color": list(p.color), "say": p.say,
                         "seeds": p.seeds, "lit": p.lit}
                        for p in self.players.values()],
            "plants": [{"x": x, "y": y, "stage": pl["stage"], "owner": pl["owner"],
                        "color": pl["color"],
                        "ring": -1 if pl["rung"] is None else self.tick - pl["rung"]}
                       for (x, y), pl in self.plants.items()],
            "plaques": [{"x": x, "y": y, "text": t}
                        for (x, y), t in self.plaques.items()],
            "glow": self.glow(), "goal": self.goal, "chapter": self.chapter,
            "night": self.night(),
            "wind": -1 if self.wind_tick is None else self.tick - self.wind_tick,
            "wind_at": list(self.wind_at) if self.wind_at else None,
        }


def _sign(v):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return 0
    return (v > 0) - (v < 0)


class Conn:
    def __init__(self, sock, player):
        self.sock = sock
        self.player = player
        self.buf = b""
        self.out = b""


def serve():
    port = int(os.environ.get("AAL_LAN_PORT", "18765"))
    world = World()
    try:
        with open(STATE_FILE) as f:
            world.load_dict(json.load(f))
        print("garden restored: %d plants" % len(world.plants), flush=True)
    except (OSError, ValueError, KeyError) as e:
        print("starting a fresh garden (%s)" % type(e).__name__, flush=True)

    def save():
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(world.to_dict(), f)
        os.replace(tmp, STATE_FILE)

    def on_term(_sig, _frm):
        save()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, on_term)
    sel = selectors.DefaultSelector()
    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind(("", port))
    lsock.listen(8)
    lsock.setblocking(False)
    sel.register(lsock, selectors.EVENT_READ, None)
    conns = {}
    print("Lantern Garden server listening", flush=True)

    def drop(c):
        try:
            sel.unregister(c.sock)
        except (KeyError, ValueError):
            pass
        c.sock.close()
        conns.pop(c.sock, None)
        world.remove_player(c.player.id)
        print("player %d left" % c.player.id, flush=True)

    def send(c, obj):
        c.out += (json.dumps(obj, separators=(",", ":")) + "\n").encode()
        try:
            n = c.sock.send(c.out)
            c.out = c.out[n:]
        except BlockingIOError:
            pass
        except OSError:
            drop(c)
            return
        if len(c.out) > 1 << 20:
            drop(c)

    period = 1.0 / TICK_HZ
    next_tick = time.monotonic() + period
    while True:
        timeout = max(0.0, next_tick - time.monotonic())
        for key, _ in sel.select(timeout):
            if key.data is None:
                sock, _addr = lsock.accept()
                sock.setblocking(False)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                c = Conn(sock, world.add_player())
                conns[sock] = c
                sel.register(sock, selectors.EVENT_READ, c)
                send(c, {"t": "welcome", "id": c.player.id, "w": W, "h": H,
                         "tick_hz": TICK_HZ})
                print("player %d joined" % c.player.id, flush=True)
            else:
                c = key.data
                try:
                    data = c.sock.recv(4096)
                except BlockingIOError:
                    continue
                except OSError:
                    data = b""
                if not data:
                    drop(c)
                    continue
                c.buf += data
                while b"\n" in c.buf:
                    line, c.buf = c.buf.split(b"\n", 1)
                    try:
                        msg = json.loads(line.decode("utf-8", "replace"))
                    except ValueError:
                        continue
                    if isinstance(msg, dict):
                        before = c.player.id
                        world.handle(c.player, msg)
                        if c.player.id != before:   # returning player got their old id
                            send(c, {"t": "welcome", "id": c.player.id, "w": W,
                                     "h": H, "tick_hz": TICK_HZ})
                if len(c.buf) > 65536:
                    drop(c)
        if time.monotonic() >= next_tick:
            next_tick += period
            world.step()
            if world.tick % (TICK_HZ * 5) == 0:
                save()
            snap = world.snapshot()
            for c in list(conns.values()):
                send(c, snap)


if __name__ == "__main__":
    serve()
