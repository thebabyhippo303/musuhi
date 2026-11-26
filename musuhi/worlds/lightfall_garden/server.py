"""Lightfall Garden (光降りの庭) — Authoritative server powered by musuhi.net."""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

from musuhi.net import JsonLineServer, PeerSession

W, H = 21, 10
TILES = [
    "TT.......~~~.......TT",
    "T........~~~........T",
    "...####...~...####...",
    "...#..#.......#..#...",
    "...####.......####...",
    ".........###.........",
    "..~~.....#.#.....~~..",
    "..~~.....###.....~~..",
    "T...................T",
    "TT.................TT",
]
BLOCK = set("~T")
HARMONY_GOAL = 8
DAWN_SECONDS = 600
DEFAULT_SAVE = Path(__file__).with_name("garden.json")
EMOTES = {"wave", "heart", "star", "laugh"}


class World:
    def __init__(self, save_path: Optional[Path | str] = DEFAULT_SAVE) -> None:
        self.save_path = Path(save_path) if save_path is not None else None
        self.lock = threading.Lock()
        self.players: dict[str, dict] = {}
        self.lamps: dict[tuple[int, int], bool] = {}
        self.flowers: dict[tuple[int, int], int] = {}
        self.notes: dict[tuple[int, int], tuple[str, str]] = {}
        self.aurora = False
        self.log = ["The garden awaits its keepers."]
        self.tick = 0
        self.next_id = 1
        self.lightfall = False
        self.heart_stones: set[tuple[int, int]] = set()
        self.dawn_start: Optional[float] = None
        self.load()

    def load(self) -> None:
        if not self.save_path:
            return
        try:
            d = json.loads(self.save_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.lamps = {(x, y): l for x, y, l in d.get("lamps", [])}
        self.flowers = {(x, y): c for x, y, c in d.get("flowers", [])}
        self.notes = {(x, y): (t, a) for x, y, t, a in d.get("notes", [])}
        self.aurora = bool(d.get("aurora", False))
        self.heart_stones = {tuple(h) for h in d.get("heart_stones", [])}
        self.dawn_start = d.get("dawn_start")
        self.update_lightfall()

    def save(self) -> None:
        if not self.save_path:
            return
        snap = self.snapshot()
        tmp = self.save_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({k: snap[k] for k in ("lamps", "flowers", "notes", "aurora", "heart_stones", "dawn_start")}),
            encoding="utf-8",
        )
        os.replace(tmp, self.save_path)

    def dawn(self) -> float:
        if not self.dawn_start:
            return 0.0
        return round(max(0.0, min(1.0, (time.time() - self.dawn_start) / DAWN_SECONDS)), 3)

    def harmony(self) -> int:
        n = 0
        for (x, y), lit in self.lamps.items():
            if lit and any(
                (x + dx, y + dy) in self.flowers
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
                if dx or dy
            ):
                n += 1
        return n

    def update_lightfall(self) -> None:
        on = self.harmony() >= HARMONY_GOAL
        if on and not self.lightfall:
            self.add_log("Harmony! LIGHTFALL — stars shower the garden!")
        self.lightfall = on

    def add_log(self, s: str) -> None:
        self.log.append(s)
        self.log = self.log[-6:]

    def spawn(self, name: str, role: str) -> str:
        pid = f"p{self.next_id}"
        self.next_id += 1
        x, y = (5, 8) if role == "lantern" else (15, 8)
        self.players[pid] = {
            "name": name[:16] or pid,
            "role": role,
            "x": x,
            "y": y,
            "emote": None,
            "emote_t": 0.0,
        }
        self.add_log(f"{self.players[pid]['name']} the {role} arrives.")
        return pid

    def handle(self, pid: str, m: dict) -> None:
        p = self.players.get(pid)
        if not p:
            return
        t = m.get("type")
        if t == "move":
            dx = max(-1, min(1, int(m.get("dx", 0))))
            dy = max(-1, min(1, int(m.get("dy", 0))))
            nx, ny = p["x"] + dx, p["y"] + dy
            if 0 <= nx < W and 0 <= ny < H and TILES[ny][nx] not in BLOCK:
                p["x"], p["y"] = nx, ny
                others = [q for qid, q in self.players.items() if qid != pid and (q["x"], q["y"]) == (nx, ny)]
                if others and (nx, ny) not in self.heart_stones:
                    self.heart_stones.add((nx, ny))
                    self.add_log(f"{p['name']} & {others[0]['name']} meet — a heart-stone appears!")
        elif t == "act":
            k = (p["x"], p["y"])
            if p["role"] == "lantern":
                lit = not self.lamps.get(k, False)
                self.lamps[k] = lit
                self.add_log(f"{p['name']} {'lights' if lit else 'dims'} a lamp.")
            else:
                c = (self.flowers.get(k, -1) + 1) % 6
                self.flowers[k] = c
                colors = ["red", "orange", "yellow", "green", "cyan", "violet"]
                self.add_log(f"{p['name']} paints a flower {colors[c]}.")
        elif t == "emote":
            e = m.get("emote")
            if e in EMOTES:
                p["emote"], p["emote_t"] = e, time.time()
        elif t == "note":
            txt = str(m.get("text", ""))[:60].strip()
            if txt:
                self.notes[(p["x"], p["y"])] = (txt, p["name"])
                self.add_log(f"{p['name']} leaves a note.")
        elif t == "chat":
            txt = str(m.get("text", ""))[:80].strip()
            if txt:
                self.add_log(f"{p['name']}: {txt}")
        elif t == "event" and m.get("name") == "aurora":
            self.aurora = not self.aurora
            self.add_log(f"{p['name']} {'summons' if self.aurora else 'calms'} the aurora!")

    def snapshot(self) -> dict:
        now = time.time()
        players = {}
        for pid, p in self.players.items():
            age = now - p["emote_t"]
            players[pid] = {
                "name": p["name"],
                "role": p["role"],
                "x": p["x"],
                "y": p["y"],
                "emote": p["emote"] if age < 4 else None,
                "emote_age": round(age, 1),
            }
        return {
            "type": "state",
            "w": W,
            "h": H,
            "tiles": TILES,
            "players": players,
            "lamps": [[x, y, l] for (x, y), l in self.lamps.items()],
            "flowers": [[x, y, c] for (x, y), c in self.flowers.items()],
            "notes": [[x, y, t, a] for (x, y), (t, a) in self.notes.items()],
            "aurora": self.aurora,
            "harmony": self.harmony(),
            "harmony_goal": HARMONY_GOAL,
            "lightfall": self.lightfall,
            "heart_stones": [[x, y] for x, y in sorted(self.heart_stones)],
            "dawn_start": self.dawn_start,
            "dawn": self.dawn(),
            "lit_count": sum(1 for l in self.lamps.values() if l),
            "bloom_count": len(self.flowers),
            "log": list(self.log),
            "tick": self.tick,
        }


def create_server(host: str = "", port: Optional[int] = None, save_path: Optional[Path | str] = DEFAULT_SAVE) -> JsonLineServer:
    world = World(save_path=save_path)
    srv: JsonLineServer

    def broadcast() -> None:
        with world.lock:
            snap = world.snapshot()
        srv.broadcast(snap)

    def on_message(peer: PeerSession, msg: dict) -> None:
        pid = peer.meta.get("pid")
        with world.lock:
            if msg.get("type") == "hello" and pid is None:
                role = msg.get("role") if msg.get("role") in ("lantern", "prism") else "prism"
                pid = world.spawn(str(msg.get("name", "")), role)
                peer.meta["pid"] = pid
                peer.send({"type": "welcome", "id": pid})
            elif pid:
                world.handle(pid, msg)
                world.update_lightfall()
        broadcast()

    def on_disconnect(peer: PeerSession) -> None:
        pid = peer.meta.get("pid")
        if pid:
            with world.lock:
                p = world.players.pop(pid, None)
                if p:
                    world.add_log(f"{p['name']} drifts away.")
            broadcast()

    def on_tick() -> None:
        with world.lock:
            world.tick += 1
            try:
                world.save()
            except OSError:
                pass
        broadcast()

    srv = JsonLineServer(
        host=host,
        port=port,
        on_message=on_message,
        on_disconnect=on_disconnect,
        tick_interval=1.0,
        on_tick=on_tick,
        banner="Lightfall Garden (光降りの庭) server ready.",
    )
    srv.world = world  # type: ignore[attr-defined]
    return srv


def main() -> None:
    ap = argparse.ArgumentParser(description="Lightfall Garden server")
    ap.add_argument("--host", default="")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()
    create_server(host=args.host, port=args.port, save_path=None if args.no_save else DEFAULT_SAVE).serve_forever()


if __name__ == "__main__":
    main()
