"""The Afterlight Garden (残光の庭) — Authoritative server powered by musuhi.net."""
from __future__ import annotations

import argparse
from threading import RLock
from typing import Optional

from musuhi.net import JsonLineServer, PeerSession

WIDTH, HEIGHT = 20, 12
HEART = (10, 6)
SPAWNS = {"wick": (4, 6), "mote": (15, 6)}
MARKS = {"wick": "an amber lantern", "mote": "a teal starflower"}
SIGNALS = {
    "wick": "Wick flashed a warm hello.",
    "mote": "Mote sent up a spray of teal sparks.",
}


class Garden:
    def __init__(self) -> None:
        self.position = dict(SPAWNS)
        self.marks: set[tuple[str, int, int]] = set()
        self.tended: set[str] = set()
        self.bloom = False
        self.event = "The Heartseed is dreaming."

    def snapshot(self, connected, revision: int) -> dict:
        return {
            "type": "state",
            "players": {
                role: dict(zip(("x", "y"), self.position[role]))
                for role in connected
            },
            "marks": [
                {"role": role, "x": x, "y": y}
                for role, x, y in sorted(self.marks)
            ],
            "event": self.event,
            "bloom": self.bloom,
            "tended": sorted(self.tended),
            "revision": revision,
        }

    def act(self, role: str, message: dict) -> bool:
        x, y = self.position[role]
        name = role.capitalize()
        kind = message.get("type")
        if kind == "move":
            dx, dy = message.get("dx"), message.get("dy")
            if any(type(d) is not int or abs(d) > 1 for d in (dx, dy)):
                return False
            nx, ny = x + dx, y + dy
            if (nx, ny) == (x, y) or not (0 <= nx < WIDTH and 0 <= ny < HEIGHT):
                return False
            self.position[role] = (nx, ny)
        elif kind == "place":
            mark = (role, x, y)
            if mark in self.marks:
                self.event = f"{name}'s mark is already here."
            else:
                self.marks.add(mark)
                self.event = f"{name} placed {MARKS[role]}."
                self.check_bloom()
        elif kind == "signal":
            self.event = SIGNALS[role]
        elif kind == "tend":
            if max(abs(x - HEART[0]), abs(y - HEART[1])) > 1:
                self.event = f"{name}: Come closer to the Heartseed to tend it."
            elif self.bloom:
                self.event = f"{name} renewed the Heartseed's light."
            else:
                self.tended.add(role)
                self.event = f"{name} offered care. The Heartseed waits for both kinds of light."
                self.check_bloom()
        else:
            return False
        return True

    def check_bloom(self) -> None:
        if not self.bloom and self.tended == SPAWNS.keys() and {
            role for role, _, _ in self.marks
        } == SPAWNS.keys():
            self.bloom = True
            self.event = "Heartseed in bloom! The garden remembers you both."


def create_server(host: str = "", port: Optional[int] = None, **_kwargs) -> JsonLineServer:
    garden = Garden()
    roles: dict[str, PeerSession] = {}
    lock = RLock()
    revision = [0]
    srv: JsonLineServer

    def broadcast_locked() -> None:
        revision[0] += 1
        snap = garden.snapshot(roles, revision[0])
        srv.broadcast(snap)

    def on_message(peer: PeerSession, msg: dict) -> None:
        with lock:
            role = peer.meta.get("role")
            if role is None:
                candidate = msg.get("role")
                if msg.get("type") != "join" or not isinstance(candidate, str) or candidate not in SPAWNS:
                    peer.send({"type": "error", "message": "Choose Wick or Mote."})
                    peer.close()
                    return
                if candidate in roles:
                    peer.send({"type": "error", "message": "That gardener is already here."})
                    peer.close()
                    return
                peer.meta["role"] = candidate
                roles[candidate] = peer
                garden.event = f"{candidate.capitalize()} arrived in the garden."
                broadcast_locked()
            elif roles.get(role) is peer and garden.act(role, msg):
                broadcast_locked()

    def on_disconnect(peer: PeerSession) -> None:
        with lock:
            role = peer.meta.get("role")
            if role and roles.get(role) is peer:
                del roles[role]
                garden.event = f"{role.capitalize()} stepped away. Their marks remain."
                broadcast_locked()

    srv = JsonLineServer(
        host=host,
        port=port,
        on_message=on_message,
        on_disconnect=on_disconnect,
        banner="The Afterlight Garden (残光の庭) server ready.",
    )
    srv.garden = garden  # type: ignore[attr-defined]
    return srv


def main() -> None:
    ap = argparse.ArgumentParser(description="The Afterlight Garden server")
    ap.add_argument("--host", default="")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()
    create_server(host=args.host, port=args.port).serve_forever()


if __name__ == "__main__":
    main()
