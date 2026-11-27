#!/usr/bin/env python3
"""Lantern Isle — 854x480 GTK3 + PIL LAN GUI Client."""

import argparse
import json
import math
import os
import queue
import socket
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

WIN_W = 854
WIN_H = 480
TOP_H = 32
BOT_H = 32
MAP_X = 11
MAP_Y = 32
TILE = 32
DEFAULT_COLS = 26
DEFAULT_ROWS = 13


def load_font(size: int, bold: bool = False):
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    )
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def hex_to_rgb(hex_str: str, fallback=(120, 210, 255)):
    try:
        s = hex_str.lstrip("#")
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        pass
    return fallback


class LanConnection:
    """Background TCP newline-JSON client strictly using AAL_LAN_HOST / AAL_LAN_PORT."""

    def __init__(self, player_name: str):
        self.host = os.environ.get("AAL_LAN_HOST", "localhost")
        self.port = int(os.environ.get("AAL_LAN_PORT", "18765"))
        self.player_name = player_name
        self.inbox: queue.Queue = queue.Queue()
        self.outbox: queue.Queue = queue.Queue()
        self.connected = False
        self.stop_event = threading.Event()
        self._sock = None
        self._sock_lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def send(self, obj: dict):
        self.outbox.put(obj)

    def close(self):
        self.stop_event.set()
        with self._sock_lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None

    def _run(self):
        while not self.stop_event.is_set():
            sock = None
            try:
                sock = socket.create_connection((self.host, self.port), timeout=3.0)
                sock.settimeout(0.1)
                with self._sock_lock:
                    self._sock = sock
                self.connected = True
                self.inbox.put({"_evt": "connected"})

                # Drain stale outbound messages and send hello first
                while not self.outbox.empty():
                    try:
                        self.outbox.get_nowait()
                    except queue.Empty:
                        break
                hello_line = (
                    json.dumps({"t": "hello", "name": self.player_name}) + "\n"
                ).encode("utf-8")
                sock.sendall(hello_line)

                buf = b""
                while not self.stop_event.is_set():
                    # Flush outbound queue
                    while not self.outbox.empty():
                        try:
                            msg = self.outbox.get_nowait()
                            data = (json.dumps(msg) + "\n").encode("utf-8")
                            sock.sendall(data)
                        except queue.Empty:
                            break

                    # Read inbound lines
                    try:
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                obj = json.loads(line.decode("utf-8"))
                                self.inbox.put(obj)
                            except Exception:
                                pass
                    except socket.timeout:
                        continue
            except Exception:
                pass
            finally:
                self.connected = False
                self.inbox.put({"_evt": "disconnected"})
                with self._sock_lock:
                    if sock is not None:
                        try:
                            sock.close()
                        except Exception:
                            pass
                    self._sock = None
            if not self.stop_event.is_set():
                time.sleep(0.8)


class LanternIsleWindow(Gtk.Window):
    def __init__(self, side: str, name: str):
        super().__init__(title="Lantern Isle")
        self.set_default_size(WIN_W, WIN_H)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.side = side
        self.player_name = name
        self.conn = LanConnection(name)

        self.my_id = None
        self.cols = DEFAULT_COLS
        self.rows = DEFAULT_ROWS
        self.map_rows = []
        self.base_map_img = None

        self.players = []
        self.lanterns = []
        self.shells = []
        self.boats = []
        self.fireflies = []
        self.bursts = []
        self._local_bursts = []  # [(x, y, start_time)]
        self._prev_jars = {}
        self.phase = "night"
        self.beacon = 0.0
        self.lighthouse_pos = None
        self.campfire_pos = None
        self.star = None
        self.chat = []
        self.lit = 0
        self.goal = 20
        self.tick = 0
        self.lan_connected = False

        self.input_mode = None  # None, "chat", or "wish"
        self.chat_buf = ""
        self.walk_target = None
        self.last_walk_step = 0.0
        self.start_time = time.monotonic()

        # Fonts
        self.f_title = load_font(15, bold=True)
        self.f_ui = load_font(12, bold=True)
        self.f_small = load_font(11, bold=False)
        self.f_tiny = load_font(10, bold=True)
        self.f_emote = load_font(13, bold=True)

        # Bottom clickable button rectangles: (name, x1, y1, x2, y2, label)
        self.buttons = [
            ("act", 450, 453, 498, 475, "Act"),
            ("wish", 504, 453, 554, 475, "Wish"),
            ("release", 560, 453, 610, 475, "Jar"),
            ("wave", 616, 453, 668, 475, "Wave"),
            ("heart", 674, 453, 730, 475, "Heart"),
            ("dance", 736, 453, 792, 475, "Dance"),
            ("chat", 798, 453, 846, 475, "Chat"),
        ]

        # GTK widget hierarchy: Gtk.EventBox -> Gtk.Image
        self.image = Gtk.Image()
        self.image.set_size_request(WIN_W, WIN_H)
        self.event_box = Gtk.EventBox()
        self.event_box.set_can_focus(True)
        self.event_box.add(self.image)
        self.event_box.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.KEY_PRESS_MASK
        )
        self.event_box.connect("button-press-event", self.on_click)
        self.connect("key-press-event", self.on_key_press)
        self.connect("destroy", self.on_destroy)
        self.add(self.event_box)

        self._render_frame()
        GLib.timeout_add(50, self._on_tick)

    def on_destroy(self, *_args):
        self.conn.close()
        Gtk.main_quit()

    def _get_me(self):
        for p in self.players:
            if p.get("id") == self.my_id:
                return p
        return None

    def _is_walkable(self, tx: int, ty: int) -> bool:
        if not self.map_rows:
            return True
        if ty < 0 or ty >= len(self.map_rows):
            return False
        row = self.map_rows[ty]
        if tx < 0 or tx >= len(row):
            return False
        if row[tx] in ("~", "^", "L", "F"):
            return False
        return True

    def _build_base_map(self):
        w = self.cols * TILE
        h = self.rows * TILE
        img = Image.new("RGB", (w, h), (16, 36, 62))
        draw = ImageDraw.Draw(img)

        self.lighthouse_pos = None
        self.campfire_pos = None
        for r in range(self.rows):
            row = self.map_rows[r] if r < len(self.map_rows) else "~" * self.cols
            for c in range(self.cols):
                ch = row[c] if c < len(row) else "~"
                x0 = c * TILE
                y0 = r * TILE
                x1 = x0 + TILE - 1
                y1 = y0 + TILE - 1
                seed = (c * 73 + r * 137) & 0xFF

                if ch == "~":
                    # Deep moonlit ocean
                    base = (18 + (seed % 7), 44 + (seed % 9), 78 + (seed % 11))
                    draw.rectangle([x0, y0, x1, y1], fill=base)
                    draw.arc(
                        [x0 + 4, y0 + 10, x0 + 26, y0 + 22],
                        15,
                        165,
                        fill=(32, 70, 112),
                        width=1,
                    )
                elif ch == "D":
                    # Wooden dock planks over water
                    draw.rectangle([x0, y0, x1, y1], fill=(18, 44, 78))
                    # Pier pilings
                    draw.rectangle([x0 + 3, y0 + 2, x0 + 7, y1 - 2], fill=(78, 52, 32))
                    draw.rectangle([x1 - 7, y0 + 2, x1 - 3, y1 - 2], fill=(78, 52, 32))
                    # Horizontal weathered wooden planks
                    for py in range(y0 + 2, y1 - 2, 6):
                        draw.rectangle(
                            [x0 + 4, py, x1 - 4, py + 4],
                            fill=(146, 104, 66),
                            outline=(96, 66, 40),
                        )
                    # Bollard posts on edges
                    draw.ellipse([x0 + 3, y0 + 12, x0 + 8, y0 + 17], fill=(104, 72, 46))
                    draw.ellipse([x1 - 8, y0 + 12, x1 - 3, y0 + 17], fill=(104, 72, 46))
                elif ch == "L":
                    # Coastal lighthouse on rocky sand base
                    self.lighthouse_pos = (c, r)
                    draw.rectangle([x0, y0, x1, y1], fill=(186, 166, 120))
                    # Stone foundation
                    draw.ellipse([x0 + 4, y0 + 20, x1 - 4, y1 - 1], fill=(108, 112, 120), outline=(60, 64, 72))
                    # Red & white striped tower
                    draw.polygon([(x0 + 9, y0 + 26), (x0 + 23, y0 + 26), (x0 + 20, y0 + 7), (x0 + 12, y0 + 7)], fill=(242, 240, 232), outline=(72, 76, 86))
                    draw.polygon([(x0 + 10, y0 + 21), (x0 + 22, y0 + 21), (x0 + 21, y0 + 15), (x0 + 11, y0 + 15)], fill=(205, 62, 56))
                    # Lantern room & dome
                    draw.rectangle([x0 + 11, y0 + 4, x0 + 21, y0 + 9], fill=(255, 235, 130), outline=(65, 58, 50))
                    draw.pieslice([x0 + 10, y0 + 1, x0 + 22, y0 + 7], 180, 360, fill=(195, 56, 52), outline=(65, 50, 50))
                elif ch == "F":
                    # Cozy stone campfire ring on beach sand
                    self.campfire_pos = (c, r)
                    draw.rectangle([x0, y0, x1, y1], fill=(192, 170, 122))
                    # Ash pit
                    draw.ellipse([x0 + 5, y0 + 9, x1 - 5, y1 - 5], fill=(58, 46, 40))
                    # Ring of stones
                    for ang_i in range(8):
                        ang = (ang_i / 8.0) * math.tau
                        sx = x0 + 16 + int(math.cos(ang) * 10)
                        sy = y0 + 18 + int(math.sin(ang) * 8)
                        draw.ellipse([sx - 3, sy - 2, sx + 3, sy + 2], fill=(118, 114, 110), outline=(64, 62, 60))
                    # Crossed wooden logs
                    draw.line([(x0 + 9, y0 + 22), (x0 + 23, y0 + 14)], fill=(116, 74, 42), width=3)
                    draw.line([(x0 + 9, y0 + 14), (x0 + 23, y0 + 22)], fill=(96, 60, 34), width=3)
                elif ch == ".":
                    # Warm sand beach
                    base = (196 - (seed % 10), 174 - (seed % 9), 126 - (seed % 8))
                    draw.rectangle([x0, y0, x1, y1], fill=base)
                    # Subtle speckles
                    for i in range(4):
                        sx = x0 + ((seed * (i + 3) * 11) % (TILE - 4)) + 2
                        sy = y0 + ((seed * (i + 5) * 7) % (TILE - 4)) + 2
                        draw.point((sx, sy), fill=(172, 148, 102))
                elif ch == ",":
                    # Lush island meadow
                    base = (48 + (seed % 10), 108 + (seed % 14), 66 + (seed % 10))
                    draw.rectangle([x0, y0, x1, y1], fill=base)
                    # Grass tufts
                    gx = x0 + 6 + (seed % 14)
                    gy = y0 + 10 + ((seed * 3) % 14)
                    draw.line([(gx, gy), (gx - 2, gy - 5)], fill=(68, 138, 84), width=1)
                    draw.line([(gx, gy), (gx + 2, gy - 4)], fill=(68, 138, 84), width=1)
                    if seed % 11 == 0:
                        draw.ellipse(
                            [gx + 3, gy - 2, gx + 6, gy + 1], fill=(220, 200, 255)
                        )
                elif ch == "^":
                    # Sea/island boulder on sand/grass base
                    draw.rectangle([x0, y0, x1, y1], fill=(56, 98, 70))
                    draw.ellipse(
                        [x0 + 3, y0 + 7, x1 - 2, y1 - 2],
                        fill=(74, 82, 92),
                        outline=(44, 50, 58),
                    )
                    draw.ellipse(
                        [x0 + 6, y0 + 9, x0 + 21, y0 + 18], fill=(104, 114, 126)
                    )
                elif ch == "T":
                    # Decorative walkable tree over grass
                    draw.rectangle([x0, y0, x1, y1], fill=(46, 104, 62))
                    # Shadow
                    draw.ellipse([x0 + 6, y0 + 20, x0 + 27, y0 + 30], fill=(32, 74, 46))
                    # Trunk
                    draw.rectangle([x0 + 13, y0 + 17, x0 + 18, y0 + 26], fill=(104, 72, 48))
                    # Layered foliage
                    draw.ellipse(
                        [x0 + 5, y0 + 6, x0 + 27, y0 + 22],
                        fill=(30, 88, 56),
                        outline=(22, 66, 42),
                    )
                    draw.ellipse([x0 + 8, y0 + 3, x0 + 24, y0 + 16], fill=(44, 118, 74))
                    draw.ellipse([x0 + 11, y0 + 5, x0 + 20, y0 + 11], fill=(64, 144, 92))
                else:
                    draw.rectangle([x0, y0, x1, y1], fill=(44, 96, 62))

        self.base_map_img = img

    def _drain_network(self):
        while True:
            try:
                msg = self.conn.inbox.get_nowait()
            except queue.Empty:
                break

            evt = msg.get("_evt")
            if evt == "connected":
                self.lan_connected = True
                continue
            elif evt == "disconnected":
                self.lan_connected = False
                continue

            t = msg.get("t")
            if t == "welcome":
                self.my_id = msg.get("id")
                self.cols = int(msg.get("cols", DEFAULT_COLS))
                self.rows = int(msg.get("rows", DEFAULT_ROWS))
                self.map_rows = msg.get("map", [])
                self.lan_connected = True
                self._build_base_map()
            elif t == "state":
                self.tick = msg.get("tick", self.tick)
                new_players = msg.get("players", [])
                now_t = time.monotonic() - self.start_time
                for pl in new_players:
                    pid = pl.get("id")
                    jar_now = int(pl.get("jar", 0))
                    jar_prev = self._prev_jars.get(pid, 0)
                    if jar_prev >= 3 and jar_now < jar_prev:
                        self._local_bursts.append((float(pl.get("x", 0)), float(pl.get("y", 0)), now_t))
                    self._prev_jars[pid] = jar_now
                self.players = new_players
                self.lanterns = msg.get("lanterns", [])
                self.shells = msg.get("shells", [])
                self.boats = msg.get("boats", [])
                self.fireflies = msg.get("fireflies", [])
                self.bursts = msg.get("bursts", [])
                self.phase = str(msg.get("phase", "night"))
                if "beacon" in msg:
                    self.beacon = float(msg.get("beacon", 0.0))
                self.star = msg.get("star")
                self.chat = msg.get("chat", [])
                self.lit = int(msg.get("lit", len(self.lanterns)))
                self.goal = int(msg.get("goal", 20))
                self.lan_connected = True

    def _step_walk_target(self, now: float):
        if self.walk_target is None or now - self.last_walk_step < 0.14:
            return
        me = self._get_me()
        if me is None:
            self.walk_target = None
            return
        mx, my = int(me.get("x", 0)), int(me.get("y", 0))
        tx, ty = self.walk_target
        if mx == tx and my == ty:
            self.walk_target = None
            return

        dx = 0 if tx == mx else (1 if tx > mx else -1)
        dy = 0 if ty == my else (1 if ty > my else -1)

        # Prefer axis with larger remaining distance, fallback to other axis if blocked
        candidates = []
        if abs(tx - mx) >= abs(ty - my):
            if dx != 0:
                candidates.append((dx, 0))
            if dy != 0:
                candidates.append((0, dy))
        else:
            if dy != 0:
                candidates.append((0, dy))
            if dx != 0:
                candidates.append((dx, 0))

        moved = False
        for cdx, cdy in candidates:
            if self._is_walkable(mx + cdx, my + cdy):
                self.conn.send({"t": "move", "dx": cdx, "dy": cdy})
                self.last_walk_step = now
                moved = True
                break
        if not moved:
            self.walk_target = None

    def _on_tick(self):
        self._drain_network()
        self._step_walk_target(time.monotonic())
        self._render_frame()
        return True

    def on_key_press(self, _widget, event):
        keyname = Gdk.keyval_name(event.keyval) or ""

        if self.input_mode is not None:
            if keyname == "Escape":
                self.input_mode = None
                self.chat_buf = ""
                return True
            elif keyname in ("Return", "KP_Enter"):
                max_len = 40 if self.input_mode == "wish" else 60
                text = self.chat_buf.strip()[:max_len]
                if text:
                    if self.input_mode == "wish":
                        self.conn.send({"t": "wish", "text": text})
                    else:
                        self.conn.send({"t": "say", "text": text})
                self.input_mode = None
                self.chat_buf = ""
                return True
            elif keyname == "BackSpace":
                self.chat_buf = self.chat_buf[:-1]
                return True
            else:
                ch = event.string
                max_len = 40 if self.input_mode == "wish" else 60
                if ch and ch.isprintable() and len(self.chat_buf) < max_len:
                    self.chat_buf += ch
                return True

        # Movement cancels click-walk target
        if keyname in ("Up", "w", "W"):
            self.walk_target = None
            self.conn.send({"t": "move", "dx": 0, "dy": -1})
            return True
        if keyname in ("Down", "s", "S"):
            self.walk_target = None
            self.conn.send({"t": "move", "dx": 0, "dy": 1})
            return True
        if keyname in ("Left", "a", "A"):
            self.walk_target = None
            self.conn.send({"t": "move", "dx": -1, "dy": 0})
            return True
        if keyname in ("Right", "d", "D"):
            self.walk_target = None
            self.conn.send({"t": "move", "dx": 1, "dy": 0})
            return True
        if keyname in ("space", "Return", "KP_Enter"):
            self.walk_target = None
            self.conn.send({"t": "act"})
            return True
        if keyname == "1":
            self.conn.send({"t": "emote", "e": "wave"})
            return True
        if keyname == "2":
            self.conn.send({"t": "emote", "e": "heart"})
            return True
        if keyname == "3":
            self.conn.send({"t": "emote", "e": "dance"})
            return True
        if keyname in ("b", "B"):
            self.input_mode = "wish"
            self.chat_buf = ""
            return True
        if keyname in ("r", "R"):
            self.conn.send({"t": "release"})
            return True
        if keyname in ("t", "T"):
            self.input_mode = "chat"
            self.chat_buf = ""
            return True

        return False

    def on_click(self, _widget, event):
        self.event_box.grab_focus()
        x, y = int(event.x), int(event.y)

        # Check bottom bar buttons first
        for btn_id, x1, y1, x2, y2, _label in self.buttons:
            if x1 <= x <= x2 and y1 <= y <= y2:
                if btn_id == "act":
                    self.walk_target = None
                    self.conn.send({"t": "act"})
                elif btn_id == "release":
                    self.conn.send({"t": "release"})
                elif btn_id in ("wave", "heart", "dance"):
                    self.conn.send({"t": "emote", "e": btn_id})
                elif btn_id == "wish":
                    self.input_mode = None if self.input_mode == "wish" else "wish"
                    self.chat_buf = ""
                elif btn_id == "chat":
                    self.input_mode = None if self.input_mode == "chat" else "chat"
                    self.chat_buf = ""
                return True

        # Check map click
        map_w = self.cols * TILE
        map_h = self.rows * TILE
        if MAP_X <= x < MAP_X + map_w and MAP_Y <= y < MAP_Y + map_h:
            tx = (x - MAP_X) // TILE
            ty = (y - MAP_Y) // TILE
            me = self._get_me()
            if me is not None and int(me.get("x", -1)) == tx and int(me.get("y", -1)) == ty:
                self.walk_target = None
                self.conn.send({"t": "act"})
            else:
                self.walk_target = (tx, ty)
                self.last_walk_step = 0.0
            return True

        return True

    def _render_frame(self):
        now = time.monotonic() - self.start_time
        frame = Image.new("RGB", (WIN_W, WIN_H), (12, 20, 36))
        draw = ImageDraw.Draw(frame)

        map_w = self.cols * TILE
        map_h = self.rows * TILE

        # 1. Base map layer
        if self.base_map_img is not None:
            map_img = self.base_map_img.copy()
        else:
            map_img = Image.new("RGB", (map_w, map_h), (16, 36, 62))
            md = ImageDraw.Draw(map_img)
            md.text(
                (map_w // 2 - 120, map_h // 2 - 10),
                "Waiting for Lantern Isle host...",
                fill=(180, 210, 240),
                font=self.f_title,
            )

        mdraw = ImageDraw.Draw(map_img, "RGBA")

        # Animated water sparkles
        if self.map_rows:
            for r in range(self.rows):
                row = self.map_rows[r]
                for c in range(self.cols):
                    if c < len(row) and row[c] == "~":
                        phase = math.sin(now * 2.2 + c * 0.9 + r * 1.3)
                        if phase > 0.72:
                            wx = c * TILE + 8 + ((c * 13 + r * 7) % 14)
                            wy = r * TILE + 8 + ((c * 5 + r * 11) % 16)
                            mdraw.line(
                                [(wx, wy), (wx + 6, wy)],
                                fill=(120, 185, 235, 110),
                                width=1,
                            )

        # Draw walk target indicator if active
        if self.walk_target is not None:
            wx, wy = self.walk_target
            cx = wx * TILE + TILE // 2
            cy = wy * TILE + TILE // 2
            pulse = int(3 + 2 * math.sin(now * 6.0))
            mdraw.ellipse(
                [cx - 8 - pulse // 2, cy - 8 - pulse // 2, cx + 8 + pulse // 2, cy + 8 + pulse // 2],
                outline=(180, 240, 255, 160),
                width=2,
            )

        # 2. Glowing shells
        for sh in self.shells:
            sx = int(sh.get("x", 0)) * TILE + TILE // 2
            sy = int(sh.get("y", 0)) * TILE + TILE // 2
            glow = 0.65 + 0.35 * math.sin(now * 3.8 + sx * 0.1 + sy * 0.1)
            r_outer = int(10 + 3 * glow)
            mdraw.ellipse(
                [sx - r_outer, sy - r_outer, sx + r_outer, sy + r_outer],
                fill=(110, 245, 240, int(65 * glow)),
            )
            # Shell body
            mdraw.pieslice(
                [sx - 7, sy - 6, sx + 7, sy + 7],
                200,
                340,
                fill=(235, 250, 255, 255),
                outline=(95, 195, 210, 255),
            )
            mdraw.ellipse(
                [sx - 4, sy - 2, sx + 4, sy + 5],
                fill=(255, 215, 240, 255),
                outline=(140, 215, 230, 255),
            )

        # 3. Planted lanterns
        player_colors = {p.get("id"): p.get("color", "#ffd166") for p in self.players}
        for i, ln in enumerate(self.lanterns):
            lx = int(ln.get("x", 0)) * TILE + TILE // 2
            ly = int(ln.get("y", 0)) * TILE + TILE // 2
            flicker = 0.85 + 0.15 * math.sin(now * 5.2 + i * 1.7)
            owner_rgb = hex_to_rgb(player_colors.get(ln.get("owner"), "#ffd166"), (255, 209, 102))

            # Warm immediate halo
            mdraw.ellipse(
                [lx - 15, ly - 15, lx + 15, ly + 15],
                fill=(255, 200, 90, int(72 * flicker)),
            )
            # Wooden post
            mdraw.rectangle([lx - 2, ly + 2, lx + 2, ly + 12], fill=(112, 74, 44, 255))
            # Paper lantern body
            mdraw.rounded_rectangle(
                [lx - 6, ly - 10, lx + 6, ly + 4],
                radius=3,
                fill=(255, 224, 128, 255),
                outline=(210, 128, 42, 255),
                width=1,
            )
            # Inner bright flame
            mdraw.ellipse([lx - 3, ly - 6, lx + 3, ly], fill=(255, 250, 215, 255))
            # Cap & owner tassel
            mdraw.rectangle([lx - 5, ly - 11, lx + 5, ly - 9], fill=(70, 48, 36, 255))
            mdraw.rectangle(
                [lx - 2, ly + 4, lx + 2, ly + 7],
                fill=(owner_rgb[0], owner_rgb[1], owner_rgb[2], 255),
            )

            # Tiny orbiting firefly
            fx = lx + int(11 * math.cos(now * 1.9 + i * 2.3))
            fy = ly - 4 + int(7 * math.sin(now * 2.5 + i * 1.9))
            mdraw.ellipse([fx - 1, fy - 1, fx + 2, fy + 2], fill=(255, 245, 160, 210))

        # 4. Night darkness & radial light mask (fast low-res upscale)
        if self.map_rows:
            celebrating = self.lit >= self.goal and self.goal > 0
            # Light grid at 2x tile resolution for smooth gradients
            gw = self.cols * 2
            gh = self.rows * 2
            # Light sources: (gx, gy, radius_in_grid, is_lantern)
            sources = []
            if self.lighthouse_pos is not None:
                lc, lr = self.lighthouse_pos
                sources.append((lc * 2 + 1, lr * 2 + 1, 9.0, True))
            if self.campfire_pos is not None:
                fc, fr = self.campfire_pos
                cf_rad = 8.0 + 0.6 * math.sin(now * 7.5)
                sources.append((fc * 2 + 1, fr * 2 + 1, cf_rad, True))
            for ln in self.lanterns:
                sources.append((ln.get("x", 0) * 2 + 1, ln.get("y", 0) * 2 + 1, 6.6, True))
            for bt in self.boats:
                sources.append((float(bt.get("x", 0)) * 2 + 1, float(bt.get("y", 0)) * 2 + 1, 4.4, True))
            for pl in self.players:
                sources.append((pl.get("x", 0) * 2 + 1, pl.get("y", 0) * 2 + 1, 5.8, False))

            mask = Image.new("RGBA", (gw, gh))
            px = mask.load()
            if self.phase == "dawn":
                max_dark = 68 if celebrating else 110
                sky_rgb = (64, 34, 52)
            elif self.phase == "aurora":
                max_dark = 92 if celebrating else 155
                sky_rgb = (14, 36, 52)
            else:
                max_dark = 95 if celebrating else 192
                sky_rgb = (22, 18, 54) if celebrating else (8, 14, 30)

            for gy in range(gh):
                for gx in range(gw):
                    light = 0.0
                    warmth = 0.0
                    for sx, sy, rad, is_lantern in sources:
                        dx = gx - sx
                        dy = gy - sy
                        d2 = dx * dx + dy * dy
                        r2 = rad * rad
                        if d2 < r2:
                            val = 1.0 - (math.sqrt(d2) / rad)
                            val = val * val * (3.0 - 2.0 * val)  # smoothstep
                            if val > light:
                                light = val
                            if is_lantern and val > warmth:
                                warmth = val
                    alpha = int(max_dark * (1.0 - min(1.0, light)))
                    if warmth > 0.25 and alpha < 90:
                        # Subtle warm golden tint right around lanterns
                        wa = int(warmth * 38)
                        px[gx, gy] = (255, 196, 92, wa)
                    else:
                        if self.phase == "aurora":
                            # Shimmering teal-violet northern lights wave
                            wave = 0.5 + 0.5 * math.sin(gx * 0.22 + now * 1.1 + math.sin(gy * 0.18))
                            ar = int(16 + 74 * (1.0 - wave))
                            ag = int(42 + 128 * wave)
                            ab = int(78 + 72 * (1.0 - wave * 0.5))
                            px[gx, gy] = (ar, ag, ab, max(35, alpha))
                        elif self.phase == "dawn":
                            # Warm rose-amber horizon gradient
                            t_y = gy / max(1, gh - 1)
                            dr = int(120 + 70 * (1.0 - t_y))
                            dg = int(58 + 55 * (1.0 - t_y))
                            db = int(72 + 25 * t_y)
                            px[gx, gy] = (dr, dg, db, max(28, alpha))
                        else:
                            px[gx, gy] = (sky_rgb[0], sky_rgb[1], sky_rgb[2], alpha)

            mask_full = mask.resize((map_w, map_h), Image.Resampling.BILINEAR)
            map_img = Image.alpha_composite(map_img.convert("RGBA"), mask_full)
            mdraw = ImageDraw.Draw(map_img, "RGBA")

            # Sweeping Lighthouse Beacon Beam (true translucent alpha composite)
            if self.lighthouse_pos is not None:
                lc, lr = self.lighthouse_pos
                ox = lc * TILE + TILE // 2
                oy = lr * TILE + 7
                beam_len = 270
                half_spread = 0.20
                a1 = self.beacon - half_spread
                a2 = self.beacon + half_spread
                beam_layer = Image.new("RGBA", (map_w, map_h), (0, 0, 0, 0))
                bdraw = ImageDraw.Draw(beam_layer, "RGBA")
                cone_outer = [
                    (ox, oy),
                    (ox + int(math.cos(a1) * beam_len), oy + int(math.sin(a1) * beam_len)),
                    (ox + int(math.cos(self.beacon) * (beam_len + 16)), oy + int(math.sin(self.beacon) * (beam_len + 16))),
                    (ox + int(math.cos(a2) * beam_len), oy + int(math.sin(a2) * beam_len)),
                ]
                bdraw.polygon(cone_outer, fill=(255, 238, 150, 44))
                a1i = self.beacon - half_spread * 0.45
                a2i = self.beacon + half_spread * 0.45
                cone_inner = [
                    (ox, oy),
                    (ox + int(math.cos(a1i) * (beam_len * 0.70)), oy + int(math.sin(a1i) * (beam_len * 0.70))),
                    (ox + int(math.cos(a2i) * (beam_len * 0.70)), oy + int(math.sin(a2i) * (beam_len * 0.70))),
                ]
                bdraw.polygon(cone_inner, fill=(255, 248, 195, 58))
                bdraw.ellipse([ox - 7, oy - 7, ox + 7, oy + 7], fill=(255, 245, 175, 165))
                bdraw.ellipse([ox - 3, oy - 3, ox + 3, oy + 3], fill=(255, 255, 235, 255))
                map_img = Image.alpha_composite(map_img, beam_layer)
                mdraw = ImageDraw.Draw(map_img, "RGBA")

            # Animated Campfire Flames & Rising Embers
            if self.campfire_pos is not None:
                fc, fr = self.campfire_pos
                fx = fc * TILE + TILE // 2
                fy = fr * TILE + 17
                flick = math.sin(now * 11.0)
                flick2 = math.cos(now * 14.5)
                # Outer orange flame
                mdraw.polygon(
                    [
                        (fx - 7, fy + 2),
                        (fx - 2 + int(flick * 2), fy - 11 - int(abs(flick2) * 3)),
                        (fx + 2 + int(flick2 * 2), fy - 9 - int(abs(flick) * 2)),
                        (fx + 7, fy + 2),
                    ],
                    fill=(255, 118, 32, 235),
                )
                # Inner golden-yellow flame
                mdraw.polygon(
                    [
                        (fx - 4, fy + 2),
                        (fx + int(flick * 1.5), fy - 7 - int(abs(flick) * 2)),
                        (fx + 4, fy + 2),
                    ],
                    fill=(255, 224, 92, 245),
                )
                # Rising embers
                for e_i in range(4):
                    ep = (now * 0.85 + e_i * 0.25) % 1.0
                    ex = fx + int(math.sin(now * 4.0 + e_i * 2.1) * 6)
                    ey = fy - 4 - int(ep * 22)
                    ea = int(220 * (1.0 - ep))
                    mdraw.ellipse([ex - 1, ey - 1, ex + 1, ey + 1], fill=(255, 195, 85, ea))

            # Shooting Star streaking across the sky!
            if isinstance(self.star, dict):
                age = float(self.star.get("age", 9.9))
                dur = 1.5
                if 0.0 <= age <= dur:
                    t_s = age / dur
                    x0_s = float(self.star.get("x0", 0.0)) * TILE
                    y0_s = float(self.star.get("y0", 0.0)) * TILE
                    x1_s = float(self.star.get("x1", 0.0)) * TILE
                    y1_s = float(self.star.get("y1", 0.0)) * TILE
                    hx = x0_s + (x1_s - x0_s) * t_s
                    hy = y0_s + (y1_s - y0_s) * t_s
                    t_tail = max(0.0, t_s - 0.28)
                    tx = x0_s + (x1_s - x0_s) * t_tail
                    ty = y0_s + (y1_s - y0_s) * t_tail
                    alpha_s = int(255 * math.sin(min(1.0, t_s) * math.pi))
                    star_layer = Image.new("RGBA", (map_w, map_h), (0, 0, 0, 0))
                    sdraw = ImageDraw.Draw(star_layer, "RGBA")
                    sdraw.line([(tx, ty), (hx, hy)], fill=(200, 235, 255, alpha_s // 2), width=4)
                    sdraw.line([(tx, ty), (hx, hy)], fill=(255, 252, 225, alpha_s), width=2)
                    sdraw.ellipse([hx - 5, hy - 5, hx + 5, hy + 5], fill=(255, 248, 195, alpha_s // 2))
                    sdraw.ellipse([hx - 2, hy - 2, hx + 2, hy + 2], fill=(255, 255, 255, alpha_s))
                    map_img = Image.alpha_composite(map_img, star_layer)
                    mdraw = ImageDraw.Draw(map_img, "RGBA")

            # Celebration sparkles when island is fully lit!
            if celebrating:
                for i in range(18):
                    sx = int((i * 97 + now * (22 + (i % 5) * 6)) % map_w)
                    sy = int((i * 53 + math.sin(now * 2.0 + i) * 28) % map_h)
                    mdraw.ellipse(
                        [sx - 2, sy - 2, sx + 2, sy + 2],
                        fill=(255, 240, 150, 210),
                    )
        else:
            map_img = map_img.convert("RGBA")
            mdraw = ImageDraw.Draw(map_img, "RGBA")

        # 5. Players (drawn above night mask so names & sprites stay crisp)
        for p in self.players:
            px_i = int(p.get("x", 0)) * TILE + TILE // 2
            py_i = int(p.get("y", 0)) * TILE + TILE // 2
            emote = p.get("emote")
            bounce = int(abs(math.sin(now * 9.0)) * 5) if emote == "dance" else 0
            py_draw = py_i - bounce

            rgb = hex_to_rgb(p.get("color", "#70d6ff"))
            is_me = p.get("id") == self.my_id

            # Ground shadow
            mdraw.ellipse([px_i - 9, py_i + 6, px_i + 9, py_i + 13], fill=(0, 0, 0, 110))

            # Highlight ring for self
            if is_me:
                mdraw.ellipse(
                    [px_i - 12, py_i + 3, px_i + 12, py_i + 14],
                    outline=(255, 245, 160, 190),
                    width=2,
                )

            # Cloak / body
            mdraw.rounded_rectangle(
                [px_i - 8, py_draw - 3, px_i + 8, py_draw + 10],
                radius=4,
                fill=(rgb[0], rgb[1], rgb[2], 255),
                outline=(25, 30, 45, 255),
                width=1,
            )
            # Head
            mdraw.ellipse(
                [px_i - 6, py_draw - 13, px_i + 6, py_draw - 1],
                fill=(255, 232, 206, 255),
                outline=(45, 35, 35, 255),
                width=1,
            )
            # Eyes
            mdraw.point((px_i - 2, py_draw - 7), fill=(25, 25, 35, 255))
            mdraw.point((px_i + 2, py_draw - 7), fill=(25, 25, 35, 255))
            # Little handheld lantern dot
            mdraw.ellipse(
                [px_i + 7, py_draw, px_i + 12, py_draw + 5],
                fill=(255, 228, 125, 255),
            )

            # Name tag
            pname = str(p.get("name", "Player"))[:14]
            tb = mdraw.textbbox((0, 0), pname, font=self.f_tiny)
            tw = tb[2] - tb[0]
            tx = px_i - tw // 2
            ty = py_i + 13
            mdraw.rounded_rectangle(
                [tx - 3, ty - 1, tx + tw + 3, ty + 11],
                radius=3,
                fill=(10, 16, 30, 185),
            )
            mdraw.text((tx, ty), pname, fill=(240, 248, 255, 255), font=self.f_tiny)

            # Floating emote bubble
            if emote:
                emap = {
                    "wave": ("WAVE!", (120, 225, 255)),
                    "heart": ("<3", (255, 115, 160)),
                    "dance": ("DANCE!", (255, 225, 105)),
                }
                etext, ecolor = emap.get(emote, (str(emote), (255, 255, 255)))
                eb = mdraw.textbbox((0, 0), etext, font=self.f_tiny)
                ew = eb[2] - eb[0]
                ex = px_i - ew // 2
                ey = py_draw - 29 - int(2 * math.sin(now * 6.0))
                mdraw.rounded_rectangle(
                    [ex - 5, ey - 2, ex + ew + 5, ey + 12],
                    radius=5,
                    fill=(18, 26, 46, 230),
                    outline=(ecolor[0], ecolor[1], ecolor[2], 255),
                    width=1,
                )
                mdraw.text((ex, ey), etext, fill=(ecolor[0], ecolor[1], ecolor[2], 255), font=self.f_tiny)

        # 5b. Drifting Wishing Boats
        for idx, bt in enumerate(self.boats):
            bx = int(float(bt.get("x", 0.0)) * TILE + TILE // 2)
            by = int(float(bt.get("y", 0.0)) * TILE + TILE // 2)
            bob = int(round(math.sin(now * 3.4 + idx * 1.3) * 2.0))
            by_b = by + bob
            owner_rgb = hex_to_rgb(player_colors.get(bt.get("owner"), "#ffe8a3"), (255, 232, 163))

            # Gentle ocean ripple rings
            rip = 10 + int(3 * math.sin(now * 2.6 + idx))
            mdraw.ellipse(
                [bx - rip - 4, by + 2, bx + rip + 4, by + 10],
                outline=(150, 215, 255, 110),
                width=1,
            )
            # Warm candle glow around boat
            mdraw.ellipse(
                [bx - 14, by_b - 12, bx + 14, by_b + 10],
                fill=(255, 210, 110, 62),
            )
            # Origami paper boat hull
            hull = [
                (bx - 10, by_b),
                (bx + 10, by_b),
                (bx + 6, by_b + 6),
                (bx - 6, by_b + 6),
            ]
            mdraw.polygon(hull, fill=(246, 242, 230, 255), outline=(170, 160, 145, 255))
            # Paper sail / center fold
            sail = [
                (bx - 5, by_b),
                (bx, by_b - 8),
                (bx + 5, by_b),
            ]
            mdraw.polygon(
                sail,
                fill=(
                    min(255, (owner_rgb[0] + 255) // 2),
                    min(255, (owner_rgb[1] + 255) // 2),
                    min(255, (owner_rgb[2] + 255) // 2),
                    245,
                ),
                outline=(180, 170, 155, 255),
            )
            # Tiny candle flame
            mdraw.ellipse([bx - 2, by_b - 4, bx + 2, by_b], fill=(255, 245, 170, 255))

            # Floating wish banner
            wtext = str(bt.get("text", "")).strip()[:28]
            if wtext:
                wb = mdraw.textbbox((0, 0), wtext, font=self.f_tiny)
                ww = wb[2] - wb[0]
                wx = max(4, min(map_w - ww - 8, bx - ww // 2))
                wy = max(4, by_b - 24)
                mdraw.rounded_rectangle(
                    [wx - 4, wy - 1, wx + ww + 4, wy + 11],
                    radius=4,
                    fill=(18, 24, 46, 200),
                    outline=(255, 224, 130, 190),
                    width=1,
                )
                mdraw.text((wx, wy), wtext, fill=(255, 244, 195, 255), font=self.f_tiny)

        # 5c. Catchable drifting Fireflies
        for idx, ff in enumerate(self.fireflies):
            fx = int(float(ff.get("x", 0.0)) * TILE + TILE // 2)
            fy = int(float(ff.get("y", 0.0)) * TILE + TILE // 2)
            pulse = 0.65 + 0.35 * math.sin(now * 6.5 + idx * 1.9)
            fx_j = fx + int(round(math.cos(now * 3.1 + idx) * 2.5))
            fy_j = fy + int(round(math.sin(now * 4.2 + idx * 1.4) * 2.5))
            r_glow = int(8 + 4 * pulse)
            mdraw.ellipse(
                [fx_j - r_glow, fy_j - r_glow, fx_j + r_glow, fy_j + r_glow],
                fill=(210, 255, 110, int(90 * pulse)),
            )
            mdraw.ellipse(
                [fx_j - 3, fy_j - 3, fx_j + 3, fy_j + 3],
                fill=(255, 255, 185, 255),
                outline=(180, 245, 95, 255),
            )

        # 5d. Firefly Jar Sparkle Bursts (server + local fallback)
        active_bursts = []
        for b in self.bursts:
            age = float(b.get("age", 0.0))
            if 0.0 <= age < 2.2:
                active_bursts.append((float(b.get("x", 0.0)), float(b.get("y", 0.0)), age))
        kept_local = []
        for lx_b, ly_b, st in self._local_bursts:
            age = now - st
            if 0.0 <= age < 2.2:
                kept_local.append((lx_b, ly_b, st))
                if not self.bursts:
                    active_bursts.append((lx_b, ly_b, age))
        self._local_bursts = kept_local

        for bx_t, by_t, age in active_bursts:
            cx = int(bx_t * TILE + TILE // 2)
            cy = int(by_t * TILE + TILE // 2)
            prog = age / 2.2
            fade = max(0, int(255 * (1.0 - prog)))
            ring_r = int(12 + prog * 68)
            mdraw.ellipse(
                [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
                outline=(255, 240, 140, fade // 2),
                width=2,
            )
            spark_colors = [
                (255, 245, 130),
                (170, 255, 140),
                (140, 245, 255),
                (255, 185, 225),
            ]
            for s_i in range(16):
                ang = (s_i / 16.0) * math.tau + prog * 1.4
                dist = 8 + prog * (42 + (s_i % 3) * 18)
                sx = cx + int(math.cos(ang) * dist)
                sy = cy + int(math.sin(ang) * dist) - int(prog * 14)
                sc = spark_colors[s_i % len(spark_colors)]
                sz = 3 if (s_i % 2 == 0) else 2
                mdraw.ellipse(
                    [sx - sz, sy - sz, sx + sz, sy + sz],
                    fill=(sc[0], sc[1], sc[2], fade),
                )

        # 6. Chat overlay (top-left ocean corner, never covers the south dock)
        if self.chat:
            recent = self.chat[-3:]
            box_h = len(recent) * 15 + 8
            box_w = 290
            bx0 = 6
            by0 = 6
            chat_layer = Image.new("RGBA", (map_w, map_h), (0, 0, 0, 0))
            cdraw = ImageDraw.Draw(chat_layer, "RGBA")
            cdraw.rounded_rectangle(
                [bx0, by0, bx0 + box_w, by0 + box_h],
                radius=6,
                fill=(10, 16, 30, 155),
                outline=(60, 88, 128, 130),
                width=1,
            )
            cy = by0 + 4
            for item in recent:
                cname = str(item.get("name", "?"))[:10]
                ctext = str(item.get("text", ""))[:36]
                line = f"{cname}: {ctext}"
                cdraw.text((bx0 + 7, cy), line, fill=(235, 242, 252, 240), font=self.f_small)
                cy += 15
            map_img = Image.alpha_composite(map_img, chat_layer)
            mdraw = ImageDraw.Draw(map_img, "RGBA")

        # Celebration banner
        if self.lit >= self.goal and self.goal > 0:
            banner = "ISLAND FULLY LIT! Lantern Festival!"
            bb = mdraw.textbbox((0, 0), banner, font=self.f_title)
            bw = bb[2] - bb[0]
            bx = (map_w - bw) // 2
            mdraw.rounded_rectangle(
                [bx - 14, 8, bx + bw + 14, 34],
                radius=8,
                fill=(45, 32, 10, 215),
                outline=(255, 215, 95, 255),
                width=2,
            )
            mdraw.text((bx, 11), banner, fill=(255, 238, 150, 255), font=self.f_title)

        # Paste map onto main 854x480 frame
        frame.paste(map_img.convert("RGB"), (MAP_X, MAP_Y))

        # Subtle border around map
        draw.rectangle(
            [MAP_X - 1, MAP_Y - 1, MAP_X + map_w, MAP_Y + map_h],
            outline=(42, 62, 92),
            width=1,
        )

        # 7. Top Bar (32 px)
        draw.rectangle([0, 0, WIN_W, TOP_H - 1], fill=(16, 24, 42))
        draw.line([(0, TOP_H - 1), (WIN_W, TOP_H - 1)], fill=(44, 66, 98), width=1)

        # Lantern icon + title
        draw.ellipse([12, 8, 24, 22], fill=(255, 215, 105), outline=(215, 135, 45))
        draw.text((30, 7), "Lantern Isle", fill=(255, 238, 180), font=self.f_title)

        # Progress, Shells, Firefly Jar & Sky Phase
        me = self._get_me()
        my_shells = int(me.get("shells", 0)) if me else 0
        my_jar = int(me.get("jar", 0)) if me else 0
        prog_text = f"Lanterns: {self.lit}/{self.goal}"
        draw.text((196, 9), prog_text, fill=(255, 224, 130), font=self.f_ui)

        # Mini progress bar
        bar_x, bar_y, bar_w, bar_h = 310, 11, 96, 10
        draw.rounded_rectangle(
            [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
            radius=4,
            fill=(28, 40, 64),
            outline=(68, 90, 126),
        )
        frac = min(1.0, self.lit / max(1, self.goal))
        if frac > 0:
            fill_w = max(6, int(bar_w * frac))
            draw.rounded_rectangle(
                [bar_x, bar_y, bar_x + fill_w, bar_y + bar_h],
                radius=4,
                fill=(255, 205, 85),
            )

        draw.text((422, 9), f"Shells: {my_shells}", fill=(140, 245, 240), font=self.f_ui)
        jar_col = (255, 248, 120) if my_jar >= 5 else (195, 245, 135)
        draw.text((506, 9), f"Jar: {my_jar}/5", fill=jar_col, font=self.f_ui)
        phase_colors = {
            "night": (155, 185, 245),
            "aurora": (110, 245, 205),
            "dawn": (255, 190, 145),
        }
        pcol = phase_colors.get(self.phase, (200, 218, 240))
        draw.text(
            (590, 9),
            f"Sky: {self.phase.capitalize()}",
            fill=pcol,
            font=self.f_ui,
        )

        # "LAN Connected" badge
        badge_x1, badge_y1, badge_x2, badge_y2 = 716, 5, 844, 26
        if self.lan_connected:
            draw.rounded_rectangle(
                [badge_x1, badge_y1, badge_x2, badge_y2],
                radius=9,
                fill=(20, 68, 48),
                outline=(68, 212, 138),
                width=1,
            )
            draw.ellipse([badge_x1 + 8, badge_y1 + 7, badge_x1 + 15, badge_y1 + 14], fill=(82, 240, 156))
            draw.text((badge_x1 + 22, badge_y1 + 3), "LAN Connected", fill=(225, 255, 238), font=self.f_ui)
        else:
            draw.rounded_rectangle(
                [badge_x1, badge_y1, badge_x2, badge_y2],
                radius=9,
                fill=(74, 54, 22),
                outline=(235, 178, 72),
                width=1,
            )
            draw.ellipse([badge_x1 + 8, badge_y1 + 7, badge_x1 + 15, badge_y1 + 14], fill=(245, 195, 85))
            draw.text((badge_x1 + 22, badge_y1 + 3), "Connecting...", fill=(255, 242, 205), font=self.f_ui)

        # 8. Bottom Bar (32 px)
        by = WIN_H - BOT_H
        draw.rectangle([0, by, WIN_W, WIN_H], fill=(16, 24, 42))
        draw.line([(0, by), (WIN_W, by)], fill=(44, 66, 98), width=1)

        if self.input_mode is not None:
            is_wish = self.input_mode == "wish"
            border_col = (255, 215, 110) if is_wish else (110, 185, 255)
            prefix = "Wish (shore): " if is_wish else "Say: "
            draw.rounded_rectangle(
                [10, by + 4, 442, WIN_H - 4],
                radius=5,
                fill=(26, 38, 64),
                outline=border_col,
                width=1,
            )
            cursor = "_" if int(now * 2.5) % 2 == 0 else ""
            draw.text(
                (18, by + 9),
                f"{prefix}{self.chat_buf}{cursor}",
                fill=(255, 246, 215) if is_wish else (245, 250, 255),
                font=self.f_ui,
            )
        else:
            hint = "WASD/Click: Move · Space: Act · B: Wish · R: Release Jar · T: Chat"
            draw.text((12, by + 9), hint, fill=(175, 198, 228), font=self.f_small)

        # Clickable bottom buttons
        for btn_id, x1, y1, x2, y2, label in self.buttons:
            active = (btn_id == "chat" and self.input_mode == "chat") or (
                btn_id == "wish" and self.input_mode == "wish"
            )
            bg = (52, 84, 132) if active else (28, 42, 70)
            border = (255, 215, 110) if (active and btn_id == "wish") else (
                (130, 200, 255) if active else (74, 102, 146)
            )
            draw.rounded_rectangle([x1, y1, x2, y2], radius=5, fill=bg, outline=border, width=1)
            lb = draw.textbbox((0, 0), label, font=self.f_tiny)
            lw = lb[2] - lb[0]
            draw.text((x1 + (x2 - x1 - lw) // 2, y1 + 5), label, fill=(235, 245, 255), font=self.f_tiny)

        # Convert PIL RGB image to GdkPixbuf
        data = frame.tobytes()
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(data),
            GdkPixbuf.Colorspace.RGB,
            False,
            8,
            WIN_W,
            WIN_H,
            WIN_W * 3,
        )
        self.image.set_from_pixbuf(pixbuf)


def main():
    parser = argparse.ArgumentParser(description="Lantern Isle LAN Client")
    parser.add_argument("--side", default="p2", choices=["p1", "p2"])
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    name = args.name or ("Laptop" if args.side == "p1" else "Mini PC")
    win = LanternIsleWindow(side=args.side, name=name)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
