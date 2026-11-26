"""Afterlight (残光と庭師の日記 · Unknown Entity Edition) — Server powered by musuhi.net."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from threading import Lock
from typing import Optional

from musuhi.net import JsonLineServer, PeerSession

BOUNDS = (24, 92, 830, 380)
STEP = 18
WEAVE_RANGE = 96
ISLANDS = (
    (1, "Hearth at Rest", 427, 236, 110, 56),
    (2, "Silverbell", 198, 159, 80, 43),
    (3, "Kite's Perch", 651, 147, 83, 40),
    (4, "Inkspill", 130, 320, 78, 40),
    (5, "Low Moon", 337, 338, 78, 35),
    (6, "Far Harbor", 694, 308, 95, 47),
)
SCARS_SNAPSHOT = Path(__file__).with_name("final_state.json")


class World:
    def __init__(self, scars: bool = False) -> None:
        self.players = {
            1: dict(name="Lumen", x=350, y=236, online=False, waves=0),
            2: dict(name="Vela", x=504, y=236, online=False, waves=0),
        }
        self.islands = [
            dict(id=i, name=name, x=x, y=y, rx=rx, ry=ry, lantern=False, bloom=False, woven=False)
            for i, name, x, y, rx, ry in ISLANDS
        ]
        self.revision = 0
        self.message = "Welcome to Afterlight. Meet at the Hearth at Rest."
        if scars and SCARS_SNAPSHOT.exists():
            try:
                snap = json.loads(SCARS_SNAPSHOT.read_text(encoding="utf-8"))
                self.islands = [dict(i) for i in snap.get("islands", self.islands)]
                self.message = "Hearth · All Three Welcomed & Guest's Lantern shine above honest history."
            except (OSError, ValueError):
                pass

    def state(self) -> dict:
        return {
            "type": "state",
            "players": {str(i): p.copy() for i, p in self.players.items()},
            "islands": [island.copy() for island in self.islands],
            "message": self.message,
            "revision": self.revision,
        }

    def set_online(self, seat: int, online: bool) -> None:
        player = self.players[seat]
        player["online"] = online
        self.message = f"{player['name']} {'arrived in' if online else 'stepped out of'} Afterlight."
        self.revision += 1

    def island_at(self, player: dict) -> Optional[dict]:
        for island in self.islands:
            rx = max(1, island["rx"])
            ry = max(1, island["ry"])
            if (((player["x"] - island["x"]) / rx) ** 2 + ((player["y"] - island["y"]) / ry) ** 2) <= 1:
                return island
        return None

    def act(self, seat: int, data: dict) -> bool:
        player = self.players[seat]
        name = player["name"]
        kind = data.get("type")
        if kind in ("move", "goto"):
            if kind == "move":
                dx, dy = data.get("dx"), data.get("dy")
                if any(type(d) is not int or d not in (-1, 0, 1) for d in (dx, dy)):
                    return False
                scale = STEP / math.sqrt(2) if dx and dy else STEP
                x, y = player["x"] + round(dx * scale), player["y"] + round(dy * scale)
            else:
                x, y = data.get("x"), data.get("y")
                if type(x) is not int or type(y) is not int:
                    return False
            left, top, right, bottom = BOUNDS
            player["x"], player["y"] = min(right, max(left, x)), min(bottom, max(top, y))
        elif kind == "wave":
            player["waves"] += 1
            self.message = f"{name} sends a little hello into the dark."
        elif kind == "tend":
            island = self.island_at(player)
            if island is None:
                self.message = f"{name}, step onto an island to tend it."
            else:
                key, noun = ("lantern", "lantern") if seat == 1 else ("bloom", "starbloom")
                place = island["name"]
                if island[key]:
                    self.message = f"{place} already has {name}'s {noun}."
                else:
                    island[key] = True
                    self.message = f"{name} {'lit a' if seat == 1 else 'woke a'} {noun} at {place}."
        elif kind == "weave":
            self.weave(seat)
        else:
            return False
        self.revision += 1
        return True

    def weave(self, seat: int) -> None:
        player, partner = self.players[seat], self.players[3 - seat]
        island = self.island_at(player)
        if island is None:
            self.message = "Step onto an island to weave its aurora."
        elif island["woven"]:
            self.message = f"{island['name']} is already singing with aurora."
        elif not (island["lantern"] and island["bloom"]):
            self.message = "An aurora needs both a lantern and a starbloom."
        elif (
            not partner["online"]
            or self.island_at(partner) is not island
            or math.hypot(player["x"] - partner["x"], player["y"] - partner["y"]) > WEAVE_RANGE
        ):
            self.message = "Both gardeners need to stand close together on this island."
        else:
            island["woven"] = True
            count = sum(i["woven"] for i in self.islands)
            self.message = (
                f"{island['name']} is woven! {count}/{len(self.islands)} islands."
                if count < len(self.islands)
                else "All six islands are woven. The sky remembers both of you."
            )


def create_server(host: str = "", port: Optional[int] = None, scars: bool = False, **_kwargs) -> JsonLineServer:
    world = World(scars=scars)
    seats: dict[int, PeerSession] = {}
    lock = Lock()
    srv: JsonLineServer

    def broadcast_locked() -> None:
        srv.broadcast(world.state())

    def on_message(peer: PeerSession, msg: dict) -> None:
        with lock:
            seat = peer.meta.get("seat")
            if seat is None:
                requested = msg.get("seat")
                if msg.get("type") != "join" or type(requested) is not int or requested not in (1, 2):
                    peer.send({"type": "error", "message": "Choose seat 1 or 2."})
                    peer.close()
                    return
                if requested in seats:
                    peer.send({"type": "error", "message": "That seat is already open."})
                    peer.close()
                    return
                peer.meta["seat"] = requested
                seats[requested] = peer
                world.set_online(requested, True)
                broadcast_locked()
            elif seats.get(seat) is peer and world.act(seat, msg):
                broadcast_locked()

    def on_disconnect(peer: PeerSession) -> None:
        with lock:
            seat = peer.meta.get("seat")
            if seat is not None and seats.get(seat) is peer:
                del seats[seat]
                world.set_online(seat, False)
                broadcast_locked()

    srv = JsonLineServer(
        host=host,
        port=port,
        on_message=on_message,
        on_disconnect=on_disconnect,
        banner="Afterlight (残光と庭師の日記) server ready.",
    )
    srv.world = world  # type: ignore[attr-defined]
    return srv


def main() -> None:
    ap = argparse.ArgumentParser(description="Afterlight server")
    ap.add_argument("--host", default="")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--scars", action="store_true", help="Load final Unknown Entity scarred world state")
    args = ap.parse_args()
    create_server(host=args.host, port=args.port, scars=args.scars).serve_forever()


if __name__ == "__main__":
    main()
