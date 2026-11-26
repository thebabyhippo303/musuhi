#!/usr/bin/env python3
"""Authoritative LAN server for Twilight Garden-Island.

Strict privacy guarantee: Never inspects, logs, prints, or transmits any
network addresses, subnets, MACs, or interface names.
"""

import json
import math
import os
import socket
import threading
import time

WORLD_W = 640
WORLD_H = 360

KIND_COLORS = {
    "moonlily": "#7ef9ff",
    "starbloom": "#ff9cee",
    "lantern": "#ffc857",
    "emberfern": "#ff7b54",
    "starlight": "#9bf6ff",
    "prismrose": "#c8b6ff",
}

SHRINES = [
    {"name": "Memory Pool", "x": 155, "y": 110},
    {"name": "Lantern Hearth", "x": 320, "y": 180},
    {"name": "Star Observatory", "x": 490, "y": 115},
    {"name": "Echo Dock", "x": 320, "y": 292},
]


def clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def color_for_kind(kind: str) -> str:
    k = (kind or "moonlily").strip().lower()
    if k in KIND_COLORS:
        return KIND_COLORS[k]
    palette = ["#7ef9ff", "#ff9cee", "#ffc857", "#a8ff9e", "#c8b6ff", "#ffd166"]
    return palette[sum(ord(c) for c in k) % len(palette)]


class GardenWorldServer:
    def __init__(self, host: str = "", port: int | None = None):
        self.host = host
        self.port = int(port if port is not None else os.environ.get("AAL_LAN_PORT", "18765"))
        self.lock = threading.Lock()
        self.running = False
        self.server_sock: socket.socket | None = None
        self.start_time = time.monotonic()

        self.tick = 0
        self.sky = "twilight"
        self.next_item_id = 1
        self.next_slot = 1

        self.players: dict[str, dict] = {}
        self.flowers: list[dict] = []
        self.notes: list[dict] = []
        self.events: list[str] = ["Twilight settles gently over Lantern Isle."]

        # Map socket -> session metadata {"slot": int, "pid": str | None}
        self.clients: dict[socket.socket, dict] = {}

    def _log(self, msg: str) -> None:
        elapsed = time.monotonic() - self.start_time
        print(f"[{elapsed:7.2f}s] {msg}", flush=True)

    def _record_event(self, text: str) -> None:
        self.events.append(text[:120])
        if len(self.events) > 16:
            self.events = self.events[-16:]

    def _ensure_player_locked(self, pid: str, msg: dict | None = None) -> dict:
        msg = msg or {}
        now = time.monotonic()
        if pid not in self.players:
            is_p2 = ("2" in pid) or ("luma" in str(msg.get("name", "")).lower())
            default_name = "Luma" if is_p2 else "Solen"
            default_color = "#3ee6d0" if is_p2 else "#ffb347"
            default_role = "Teal Lantern-Spirit" if is_p2 else "Amber Star-Lantern"
            default_x = 410.0 if is_p2 else 230.0
            self.players[pid] = {
                "id": pid,
                "name": str(msg.get("name") or default_name)[:28],
                "color": str(msg.get("color") or default_color)[:16],
                "role": str(msg.get("role") or default_role)[:36],
                "x": clamp(float(msg.get("x", default_x)), 24.0, WORLD_W - 24.0),
                "y": clamp(float(msg.get("y", 185.0)), 24.0, WORLD_H - 24.0),
                "emote": "",
                "emote_until": 0.0,
                "speech": "",
                "speech_until": 0.0,
                "updated_at": now,
            }
            self._record_event(f"{self.players[pid]['name']} stepped onto Lantern Isle.")
        else:
            p = self.players[pid]
            if msg.get("name"):
                p["name"] = str(msg["name"])[:28]
            if msg.get("color"):
                p["color"] = str(msg["color"])[:16]
            if msg.get("role"):
                p["role"] = str(msg["role"])[:36]
            p["updated_at"] = now
        return self.players[pid]

    def _compute_harmony_locked(self) -> bool:
        plist = list(self.players.values())
        if len(plist) < 2:
            return False
        for i in range(len(plist)):
            for j in range(i + 1, len(plist)):
                dx = plist[i]["x"] - plist[j]["x"]
                dy = plist[i]["y"] - plist[j]["y"]
                if math.hypot(dx, dy) <= 115.0:
                    return True
        return False

    def build_state_locked(self) -> dict:
        now = time.monotonic()
        pub_players = {}
        for pid, p in self.players.items():
            emote = p["emote"] if now < p.get("emote_until", 0.0) else ""
            speech = p["speech"] if now < p.get("speech_until", 0.0) else ""
            pub_players[pid] = {
                "id": pid,
                "name": p["name"],
                "color": p["color"],
                "role": p.get("role", ""),
                "x": round(p["x"], 1),
                "y": round(p["y"], 1),
                "emote": emote,
                "speech": speech,
            }
        return {
            "type": "state",
            "tick": self.tick,
            "world_w": WORLD_W,
            "world_h": WORLD_H,
            "sky": self.sky,
            "harmony": self._compute_harmony_locked(),
            "players": pub_players,
            "players_list": list(pub_players.values()),
            "flowers": list(self.flowers),
            "notes": list(self.notes),
            "shrines": SHRINES,
            "events": list(self.events[-6:]),
        }

    def process_message(self, session: dict, msg: dict) -> tuple[dict | None, bool]:
        """Process one parsed dict message. Returns (direct_reply, should_broadcast)."""
        if not isinstance(msg, dict):
            return None, False

        mtype = str(msg.get("type") or msg.get("action") or msg.get("cmd") or "").strip().lower()
        now = time.monotonic()

        with self.lock:
            explicit_id = msg.get("id") or msg.get("player_id") or msg.get("you")
            if explicit_id:
                pid = str(explicit_id)[:24]
            elif session.get("pid"):
                pid = session["pid"]
            else:
                raw_name = str(msg.get("name") or "").strip().lower()
                if "luma" in raw_name or "2" in raw_name:
                    pid = "p2"
                elif "solen" in raw_name or "1" in raw_name:
                    pid = "p1"
                else:
                    pid = f"keeper_{session['slot']}"

            old_pid = session.get("pid")
            if old_pid and old_pid != pid and old_pid in self.players and old_pid.startswith("keeper_"):
                del self.players[old_pid]
            session["pid"] = pid

            if mtype in ("hello", "join", "init", "register"):
                p = self._ensure_player_locked(pid, msg)
                if "x" in msg:
                    p["x"] = clamp(float(msg["x"]), 24.0, WORLD_W - 24.0)
                if "y" in msg:
                    p["y"] = clamp(float(msg["y"]), 24.0, WORLD_H - 24.0)
                welcome = {
                    "type": "welcome",
                    "you": pid,
                    "world_w": WORLD_W,
                    "world_h": WORLD_H,
                }
                return welcome, True

            p = self._ensure_player_locked(pid, msg)

            if mtype in ("move", "pos", "position", "step", "update", "sync"):
                if "dx" in msg or "dy" in msg:
                    p["x"] = clamp(p["x"] + float(msg.get("dx", 0.0)), 24.0, WORLD_W - 24.0)
                    p["y"] = clamp(p["y"] + float(msg.get("dy", 0.0)), 24.0, WORLD_H - 24.0)
                elif "x" in msg or "y" in msg:
                    p["x"] = clamp(float(msg.get("x", p["x"])), 24.0, WORLD_W - 24.0)
                    p["y"] = clamp(float(msg.get("y", p["y"])), 24.0, WORLD_H - 24.0)
                if msg.get("emote"):
                    p["emote"] = str(msg["emote"])[:24]
                    p["emote_until"] = now + 4.0
                return None, True

            if mtype in ("plant", "flower", "place", "build", "bloom"):
                kind = str(msg.get("kind") or msg.get("flower") or msg.get("item") or "moonlily").strip()[:24]
                fx = clamp(float(msg.get("x", p["x"])), 20.0, WORLD_W - 20.0)
                fy = clamp(float(msg.get("y", p["y"])), 20.0, WORLD_H - 20.0)
                item = {
                    "id": self.next_item_id,
                    "x": round(fx, 1),
                    "y": round(fy, 1),
                    "kind": kind,
                    "color": str(msg.get("color") or color_for_kind(kind))[:16],
                    "by": p["name"],
                    "t": round(now - self.start_time, 1),
                }
                self.next_item_id += 1
                self.flowers.append(item)
                if len(self.flowers) > 140:
                    self.flowers = self.flowers[-140:]
                self._record_event(f"{p['name']} planted {kind}.")
                return None, True

            if mtype in ("note", "message", "say", "chat", "mark", "scroll"):
                text = str(
                    msg.get("text")
                    or msg.get("note")
                    or msg.get("message")
                    or msg.get("content")
                    or ""
                ).strip()[:140]
                if text:
                    nx = clamp(float(msg.get("x", p["x"])), 24.0, WORLD_W - 24.0)
                    ny = clamp(float(msg.get("y", p["y"])), 24.0, WORLD_H - 24.0)
                    note_obj = {
                        "id": self.next_item_id,
                        "x": round(nx, 1),
                        "y": round(ny, 1),
                        "text": text,
                        "by": p["name"],
                        "t": round(now - self.start_time, 1),
                    }
                    self.next_item_id += 1
                    self.notes.append(note_obj)
                    if len(self.notes) > 60:
                        self.notes = self.notes[-60:]
                    p["speech"] = text
                    p["speech_until"] = now + 8.0
                    self._record_event(f"{p['name']} carved a note: \"{text[:42]}\"")
                    return None, True
                return None, False

            if mtype in ("emote", "pulse", "wave", "chime", "sparkle"):
                em = str(msg.get("emote") or msg.get("kind") or mtype or "chime").strip()[:24]
                p["emote"] = em
                p["emote_until"] = now + 4.5
                self._record_event(f"{p['name']} shared a {em} pulse.")
                return None, True

            if mtype in ("sky", "weather", "world_event", "event"):
                new_sky = str(msg.get("sky") or msg.get("mode") or msg.get("weather") or "aurora").strip().lower()[:20]
                if new_sky:
                    self.sky = new_sky
                    self._record_event(f"{p['name']} shifted the sky to {new_sky}.")
                    return None, True

            if mtype == "ping":
                return {"type": "pong", "tick": self.tick}, False

            return None, False


def create_server(host: str = "", port=None, **_kwargs):
    from musuhi.net import JsonLineServer, PeerSession
    core = GardenWorldServer(host=host, port=port if port is not None else 0)
    srv: JsonLineServer

    def broadcast():
        with core.lock:
            core.tick += 1
            snap = core.build_state_locked()
        srv.broadcast(snap)

    def on_connect(peer: PeerSession):
        with core.lock:
            slot = core.next_slot
            core.next_slot += 1
            peer.meta["session"] = {"slot": slot, "pid": None}
            init_state = core.build_state_locked()
        peer.send({"type": "welcome", "you": f"keeper_{slot}", "world_w": WORLD_W, "world_h": WORLD_H})
        peer.send(init_state)

    def on_message(peer: PeerSession, msg: dict):
        session = peer.meta.get("session")
        if session is None:
            return
        reply, do_bcast = core.process_message(session, msg)
        if reply is not None:
            peer.send(reply)
        if do_bcast:
            broadcast()

    def on_disconnect(peer: PeerSession):
        session = peer.meta.get("session")
        if session and session.get("pid"):
            pid = session["pid"]
            with core.lock:
                still = any(
                    p.meta.get("session", {}).get("pid") == pid
                    for p in srv.peers() if p is not peer
                )
                if not still and pid in core.players:
                    pname = core.players[pid]["name"]
                    del core.players[pid]
                    core._record_event(f"{pname}'s lantern drifted quiet.")
            broadcast()

    srv = JsonLineServer(
        host=host,
        port=port,
        on_connect=on_connect,
        on_message=on_message,
        on_disconnect=on_disconnect,
        tick_interval=0.1,
        on_tick=broadcast,
        banner="Twilight Garden-Island (黄昏の灯島) server ready.",
    )
    srv.core = core
    return srv


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Twilight Garden-Island server")
    ap.add_argument("--host", default="")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()
    create_server(host=args.host, port=args.port).serve_forever()
