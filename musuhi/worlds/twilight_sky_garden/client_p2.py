#!/usr/bin/env python3
"""Twilight Sky Garden v2 — Collaborator 2 (Prism) 854x480 GTK3 + PIL LAN Client."""

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
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from PIL import Image, ImageDraw, ImageFont

WIN_W = 854
WIN_H = 480

GRID_W = 20
GRID_H = 10
TILE_W = 36
TILE_H = 26
GRID_X0 = (WIN_W - GRID_W * TILE_W) // 2  # 67
GRID_Y0 = 148

SKY_TOP = 32
SKY_BOT = 144

PRESET_NOTES = [
    "Prism was here - refracting twilight!",
    "Amber & teal make the sky sing.",
    "A bridge of light into the dusk.",
    "May these star-blooms keep glowing.",
    "Listening to the wind chimes together.",
]


def load_font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def lerp_color(c1, c2, t):
    t = clamp(t, 0.0, 1.0)
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def is_lantern(by_val) -> bool:
    return str(by_val or "").strip().lower() == "lantern"


class NetworkClient:
    """Line-delimited JSON TCP client connecting strictly via AAL_LAN_HOST / AAL_LAN_PORT."""

    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
        self.host = os.environ.get("AAL_LAN_HOST", "localhost")
        self.port = int(os.environ.get("AAL_LAN_PORT", "18765"))
        self.lock = threading.Lock()
        self.connected = False
        self.my_id = None
        self.state = None
        self.out_q = queue.Queue()
        self.stop_event = threading.Event()
        self.sock = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def send(self, obj: dict):
        try:
            self.out_q.put_nowait(obj)
        except queue.Full:
            pass

    def get_snapshot(self):
        with self.lock:
            return self.connected, self.my_id, self.state

    def stop(self):
        self.stop_event.set()
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass

    def _run(self):
        while not self.stop_event.is_set():
            sock = None
            try:
                sock = socket.create_connection((self.host, self.port), timeout=4.0)
                sock.settimeout(0.15)
                self.sock = sock
                while not self.out_q.empty():
                    try:
                        self.out_q.get_nowait()
                    except queue.Empty:
                        break
                hello = json.dumps({"t": "hello", "name": self.name, "role": self.role}) + "\n"
                sock.sendall(hello.encode("utf-8"))
                with self.lock:
                    self.connected = True

                buf = b""
                last_ping = time.monotonic()
                while not self.stop_event.is_set():
                    while True:
                        try:
                            msg = self.out_q.get_nowait()
                        except queue.Empty:
                            break
                        data = (json.dumps(msg) + "\n").encode("utf-8")
                        sock.sendall(data)

                    now = time.monotonic()
                    if now - last_ping > 8.0:
                        sock.sendall(b'{"t":"ping"}\n')
                        last_ping = now

                    try:
                        chunk = sock.recv(8192)
                        if not chunk:
                            break
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                pkt = json.loads(line.decode("utf-8"))
                            except Exception:
                                continue
                            ptype = pkt.get("t")
                            if ptype == "welcome":
                                with self.lock:
                                    self.my_id = pkt.get("id")
                            elif ptype == "state":
                                with self.lock:
                                    self.state = pkt
                    except socket.timeout:
                        continue
            except Exception:
                pass
            finally:
                with self.lock:
                    self.connected = False
                try:
                    if sock:
                        sock.close()
                except Exception:
                    pass
                self.sock = None
                if not self.stop_event.is_set():
                    time.sleep(1.2)


class TwilightGardenWindow(Gtk.Window):
    def __init__(self, name: str, role: str):
        super().__init__(title=f"Twilight Sky Garden — {name}")
        self.set_default_size(WIN_W, WIN_H)
        self.set_size_request(WIN_W, WIN_H)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.net = NetworkClient(name=name, role=role)
        self.start_time = time.monotonic()
        self.note_mode = False
        self.note_buf = ""
        self.preset_idx = 0
        self.last_dir = (0, -1)
        self.last_click_feedback = ""
        self.last_click_time = 0.0

        self.f_title = load_font(14, bold=True)
        self.f_med = load_font(12, bold=True)
        self.f_sm = load_font(11, bold=False)
        self.f_xs = load_font(10, bold=False)
        self.f_xs_b = load_font(10, bold=True)

        self.base_bg = self._build_base_background()

        # Non-overlapping action buttons (left x=8..356) + D-pad (x=362..434) + Log (x=442..846)
        self.buttons = [
            ("plant", "[P]Plant", 8, 424, 72, 447, (64, 215, 195)),
            ("chime", "[C]Chime", 76, 424, 144, 447, (245, 195, 90)),
            ("star", "[L]Star", 148, 424, 206, 447, (165, 190, 255)),
            ("lamp", "[F]Lamp", 210, 424, 274, 447, (255, 205, 100)),
            ("build", "[B]Stone", 278, 424, 350, 447, (110, 245, 230)),
            ("wave", "[1]Wave", 8, 452, 72, 474, (110, 220, 215)),
            ("heart", "[2]Heart", 76, 452, 144, 474, (255, 130, 165)),
            ("spark", "[3]Spark", 148, 452, 214, 474, (255, 215, 110)),
            ("note", "[N]Note", 218, 452, 282, 474, (230, 175, 255)),
            ("quicknote", "[Q]Note", 286, 452, 350, 474, (180, 235, 225)),
        ]
        self.dpad = [
            ("up", "^", 384, 424, 408, 447),
            ("left", "<", 358, 450, 382, 473),
            ("down", "v", 384, 450, 408, 473),
            ("right", ">", 410, 450, 434, 473),
        ]

        self.image = Gtk.Image()
        self.event_box = Gtk.EventBox()
        self.event_box.add(self.image)
        self.event_box.set_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.event_box.connect("button-press-event", self._on_click)
        self.connect("key-press-event", self._on_key)
        self.connect("destroy", self._on_destroy)
        self.add(self.event_box)
        self.show_all()

        self._render_frame()
        GLib.timeout_add(90, self._on_tick)

    def _build_base_background(self):
        img = Image.new("RGB", (WIN_W, WIN_H), (12, 16, 38))
        draw = ImageDraw.Draw(img)
        for y in range(WIN_H):
            if y < 145:
                t = y / 145.0
                c = lerp_color((10, 14, 36), (34, 24, 66), t)
            elif y < 340:
                t = (y - 145) / 195.0
                c = lerp_color((34, 24, 66), (22, 32, 62), t)
            else:
                t = (y - 340) / float(WIN_H - 340)
                c = lerp_color((22, 32, 62), (12, 17, 34), t)
            draw.line([(0, y), (WIN_W, y)], fill=c)

        for i in range(55):
            sx = (i * 173 + 41) % (WIN_W - 20) + 10
            sy = (i * 89 + 37) % 360 + 36
            r = 1 if i % 4 else 2
            col = (140, 155, 200) if i % 3 else (195, 185, 230)
            draw.ellipse([sx - r, sy - r, sx + r, sy + r], fill=col)

        mx, my = 790, 68
        draw.ellipse([mx - 18, my - 18, mx + 18, my + 18], fill=(248, 234, 190))
        draw.ellipse([mx - 10, my - 21, mx + 24, my + 13], fill=(20, 19, 48))

        for cx, cy, cw, ch in [(110, 132, 95, 16), (430, 138, 120, 14), (710, 128, 105, 16), (60, 370, 90, 18), (760, 365, 100, 18)]:
            draw.ellipse([cx - cw // 2, cy - ch // 2, cx + cw // 2, cy + ch // 2], fill=(42, 35, 78))

        return img

    def _on_destroy(self, *_args):
        self.net.stop()
        Gtk.main_quit()

    def _set_feedback(self, text: str):
        self.last_click_feedback = text
        self.last_click_time = time.monotonic()

    def _weave_stepping_stone(self):
        _conn, my_id, state = self.net.get_snapshot()
        if not state or not my_id or my_id not in state.get("players", {}):
            self.net.send({"t": "build", "dx": self.last_dir[0], "dy": self.last_dir[1]})
            return
        me = state["players"][my_id]
        island = state.get("island", [])
        candidates = [self.last_dir, (0, -1), (0, 1), (1, 0), (-1, 0)]
        for dx, dy in candidates:
            nx, ny = me["x"] + dx, me["y"] + dy
            if 0 <= ny < len(island) and 0 <= nx < len(island[ny]) and island[ny][nx] == ".":
                self.net.send({"t": "build", "dx": dx, "dy": dy})
                self._set_feedback("Wove a glowing stepping-stone")
                return
        self._set_feedback("Step to the island edge to weave a stone")

    def _do_action(self, act: str):
        if act == "plant":
            self.net.send({"t": "plant"})
            self._set_feedback("Planted / grew a glowing flower")
        elif act == "chime":
            self.net.send({"t": "chime"})
            self._set_feedback("Rang nearby wind chime")
        elif act == "star":
            self.net.send({"t": "star"})
            self._set_feedback("Lit a star in the twilight sky")
        elif act == "lamp":
            self.net.send({"t": "lamp"})
            self._set_feedback("Raised a glowing crystal lamp")
        elif act == "build":
            self._weave_stepping_stone()
        elif act == "note":
            self.note_mode = True
            self.note_buf = ""
            self._set_feedback("Type note & press Enter (Esc to cancel)")
        elif act == "quicknote":
            txt = PRESET_NOTES[self.preset_idx % len(PRESET_NOTES)]
            self.preset_idx += 1
            self.net.send({"t": "note", "text": txt})
            self._set_feedback("Left a twilight note")
        elif act in ("wave", "heart", "spark"):
            self.net.send({"t": "emote", "e": act})
            self._set_feedback(f"Emoted: {act}")
        elif act == "up":
            self.last_dir = (0, -1)
            self.net.send({"t": "move", "dx": 0, "dy": -1})
        elif act == "down":
            self.last_dir = (0, 1)
            self.net.send({"t": "move", "dx": 0, "dy": 1})
        elif act == "left":
            self.last_dir = (-1, 0)
            self.net.send({"t": "move", "dx": -1, "dy": 0})
        elif act == "right":
            self.last_dir = (1, 0)
            self.net.send({"t": "move", "dx": 1, "dy": 0})

    def _on_key(self, _widget, event):
        keyval = event.keyval
        name = Gdk.keyval_name(keyval) or ""

        if self.note_mode:
            if name == "Escape":
                self.note_mode = False
                self.note_buf = ""
                self._set_feedback("Note cancelled")
                return True
            if name in ("Return", "KP_Enter"):
                text = self.note_buf.strip()[:60]
                if text:
                    self.net.send({"t": "note", "text": text})
                    self._set_feedback("Left note on island")
                self.note_mode = False
                self.note_buf = ""
                return True
            if name == "BackSpace":
                self.note_buf = self.note_buf[:-1]
                return True
            uni = Gdk.keyval_to_unicode(keyval)
            if uni and 32 <= uni <= 126 and len(self.note_buf) < 60:
                self.note_buf += chr(uni)
            return True

        low = name.lower()
        if low in ("w", "up"):
            self._do_action("up")
        elif low in ("s", "down"):
            self._do_action("down")
        elif low in ("a", "left"):
            self._do_action("left")
        elif low in ("d", "right"):
            self._do_action("right")
        elif low in ("p", "space"):
            self._do_action("plant")
        elif low == "c":
            self._do_action("chime")
        elif low == "l":
            self._do_action("star")
        elif low == "f":
            self._do_action("lamp")
        elif low == "b":
            self._do_action("build")
        elif low == "n":
            self._do_action("note")
        elif low == "q":
            self._do_action("quicknote")
        elif low == "1":
            self._do_action("wave")
        elif low == "2":
            self._do_action("heart")
        elif low == "3":
            self._do_action("spark")
        return True

    def _on_click(self, _widget, event):
        x, y = int(event.x), int(event.y)

        for bid, _lbl, x1, y1, x2, y2, _col in self.buttons:
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._do_action(bid)
                return True

        for did, _lbl, x1, y1, x2, y2 in self.dpad:
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._do_action(did)
                return True

        if SKY_TOP <= y <= SKY_BOT:
            self._do_action("star")
            return True

        if GRID_X0 <= x < GRID_X0 + GRID_W * TILE_W and GRID_Y0 <= y < GRID_Y0 + GRID_H * TILE_H:
            tx = (x - GRID_X0) // TILE_W
            ty = (y - GRID_Y0) // TILE_H
            _conn, my_id, state = self.net.get_snapshot()
            if state and my_id and my_id in state.get("players", {}):
                me = state["players"][my_id]
                island = state.get("island", [])
                dx = tx - me["x"]
                dy = ty - me["y"]
                # If clicking an adjacent void tile, weave a stepping-stone!
                if max(abs(dx), abs(dy)) == 1 and 0 <= ty < len(island) and 0 <= tx < len(island[ty]) and island[ty][tx] == ".":
                    self.net.send({"t": "build", "dx": dx, "dy": dy})
                    self._set_feedback("Wove a glowing stepping-stone")
                    return True
                if dx == 0 and dy == 0:
                    self._do_action("plant")
                else:
                    if abs(dx) >= abs(dy):
                        step_x = 1 if dx > 0 else -1
                        self.last_dir = (step_x, 0)
                        self.net.send({"t": "move", "dx": step_x, "dy": 0})
                    else:
                        step_y = 1 if dy > 0 else -1
                        self.last_dir = (0, step_y)
                        self.net.send({"t": "move", "dx": 0, "dy": step_y})
            return True
        return True

    def _on_tick(self):
        self._render_frame()
        return True

    def _render_frame(self):
        now = time.monotonic() - self.start_time
        connected, my_id, state = self.net.get_snapshot()

        img = self.base_bg.copy().convert("RGBA")
        overlay = Image.new("RGBA", (WIN_W, WIN_H), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)

        bloom = int(state.get("bloom", 0)) if state else 0
        wishes = int(state.get("wishes", 0)) if state else 0
        wish_age = state.get("wish_age") if state else None
        players = state.get("players", {}) if state else {}

        p_list = list(players.values())
        near_together = False
        if len(p_list) >= 2:
            d = abs(p_list[0]["x"] - p_list[1]["x"]) + abs(p_list[0]["y"] - p_list[1]["y"])
            if d <= 2:
                near_together = True

        # 1. Sky Aurora
        aurora_strength = clamp(bloom / 100.0 + (0.25 if near_together else 0.0), 0.0, 1.0)
        if aurora_strength > 0.05:
            pts_teal = []
            pts_amber = []
            for i in range(0, WIN_W + 24, 24):
                w1 = math.sin(i * 0.012 + now * 1.1) * 14
                w2 = math.cos(i * 0.015 - now * 0.85) * 10
                pts_teal.append((i, int(74 + w1)))
                pts_amber.append((i, int(92 + w2)))
            a_alpha = int(35 + 115 * aurora_strength)
            for idx in range(len(pts_teal) - 1):
                odraw.line([pts_teal[idx], pts_teal[idx + 1]], fill=(65, 240, 225, a_alpha), width=14)
                odraw.line([pts_amber[idx], pts_amber[idx + 1]], fill=(255, 185, 85, int(a_alpha * 0.8)), width=10)

        # 1b. Shooting Star animation when two hearts meet!
        if wish_age is not None and 0.0 <= wish_age < 4.0:
            prog = wish_age / 4.0
            sx = int(90 + prog * 680)
            sy = int(48 + prog * 62 + math.sin(prog * math.pi) * -12)
            tail_x = sx - 85
            tail_y = sy - 10
            fade = int(clamp((1.0 - prog) * 255, 40, 255))
            odraw.line([(tail_x, tail_y), (sx, sy)], fill=(255, 235, 160, fade), width=4)
            odraw.line([(tail_x + 25, tail_y + 3), (sx, sy)], fill=(140, 255, 245, fade), width=2)
            odraw.ellipse([sx - 6, sy - 6, sx + 6, sy + 6], fill=(255, 255, 240, fade))
            odraw.ellipse([sx - 12, sy - 12, sx + 12, sy + 12], fill=(255, 215, 120, fade // 3))

        # 2. Stars & Constellations
        stars = state.get("stars", []) if state else []
        lit_stars = []
        roles_lit = set()
        for st in stars:
            sx = int(38 + float(st["x"]) * (WIN_W - 76))
            sy = int(SKY_TOP + 16 + float(st["y"]) * (SKY_BOT - SKY_TOP - 30))
            if st.get("lit"):
                lit_stars.append((sx, sy, st.get("by")))
                if st.get("by"):
                    roles_lit.add(str(st.get("by")).lower())

        both_lit = len(roles_lit) >= 2
        if len(lit_stars) >= 2:
            line_col = (155, 245, 235, 170) if both_lit else (140, 175, 230, 85)
            for i in range(len(lit_stars) - 1):
                x1, y1, _ = lit_stars[i]
                x2, y2, _ = lit_stars[i + 1]
                odraw.line([(x1, y1), (x2, y2)], fill=line_col, width=2 if both_lit else 1)

        for idx, st in enumerate(stars):
            sx = int(38 + float(st["x"]) * (WIN_W - 76))
            sy = int(SKY_TOP + 16 + float(st["y"]) * (SKY_BOT - SKY_TOP - 30))
            lit = bool(st.get("lit"))
            by = st.get("by")
            twinkle = 0.8 + 0.2 * math.sin(now * 3.0 + idx)
            if lit:
                if is_lantern(by):
                    core = (255, 210, 110, 255)
                    halo = (255, 175, 65, int(95 * twinkle))
                else:
                    core = (110, 255, 245, 255)
                    halo = (65, 235, 225, int(95 * twinkle))
                r_halo = int(11 * twinkle)
                odraw.ellipse([sx - r_halo, sy - r_halo, sx + r_halo, sy + r_halo], fill=halo)
                odraw.line([(sx - 7, sy), (sx + 7, sy)], fill=core, width=2)
                odraw.line([(sx, sy - 7), (sx, sy + 7)], fill=core, width=2)
                odraw.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=(255, 255, 255, 255))
            else:
                odraw.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=(110, 125, 175, 150))
                odraw.ellipse([sx - 1, sy - 1, sx + 1, sy + 1], fill=(190, 205, 245, 210))

        # 3. Floating Island Tiles ('#' ground, '*' woven glowing stepping-stones)
        island = state.get("island", []) if state else []
        if island:
            for row_i, row in enumerate(island):
                for col_i, ch in enumerate(row):
                    if ch != "#":
                        continue
                    below_void = (row_i + 1 >= len(island)) or (island[row_i + 1][col_i] != "#")
                    x1 = GRID_X0 + col_i * TILE_W
                    y1 = GRID_Y0 + row_i * TILE_H
                    if below_void:
                        cliff_h = 12 + ((col_i * 7 + row_i * 3) % 7)
                        odraw.polygon(
                            [(x1 + 2, y1 + TILE_H), (x1 + TILE_W - 2, y1 + TILE_H), (x1 + TILE_W - 7, y1 + TILE_H + cliff_h), (x1 + 7, y1 + TILE_H + cliff_h - 2)],
                            fill=(36, 32, 58, 240),
                        )
                        odraw.line([(x1 + 7, y1 + TILE_H + cliff_h - 2), (x1 + TILE_W - 7, y1 + TILE_H + cliff_h)], fill=(75, 195, 190, 95), width=2)

            for row_i, row in enumerate(island):
                for col_i, ch in enumerate(row):
                    x1 = GRID_X0 + col_i * TILE_W
                    y1 = GRID_Y0 + row_i * TILE_H
                    x2 = x1 + TILE_W - 1
                    y2 = y1 + TILE_H - 1
                    if ch == "#":
                        checker = (row_i + col_i) % 2 == 0
                        base_col = (34, 62, 74, 245) if checker else (30, 55, 68, 245)
                        odraw.rectangle([x1, y1, x2, y2], fill=base_col, outline=(46, 86, 98, 170))
                        if row_i == 0 or island[row_i - 1][col_i] != "#":
                            odraw.line([(x1 + 1, y1 + 1), (x2 - 1, y1 + 1)], fill=(95, 190, 185, 160), width=2)
                    elif ch == "*":
                        # Glowing woven sky-bridge stepping-stone!
                        pulse = int(20 * math.sin(now * 2.4 + col_i + row_i))
                        odraw.rounded_rectangle([x1 + 2, y1 + 2, x2 - 2, y2 - 2], radius=6, fill=(48, 105 + pulse // 2, 128, 235), outline=(145, 245, 230, 245), width=2)
                        odraw.ellipse([x1 + TILE_W // 2 - 4, y1 + TILE_H // 2 - 3, x1 + TILE_W // 2 + 4, y1 + TILE_H // 2 + 3], fill=(255, 230, 165, 185))

        # 4. Plants
        for pl in (state.get("plants", []) if state else []):
            px = GRID_X0 + pl["x"] * TILE_W + TILE_W // 2
            py = GRID_Y0 + pl["y"] * TILE_H + TILE_H // 2 + 2
            stage = int(pl.get("stage", 1))
            if is_lantern(pl.get("by")):
                petal = (255, 190, 78, 255)
                glow = (255, 170, 55, 80)
            else:
                petal = (80, 245, 228, 255)
                glow = (60, 235, 220, 80)

            odraw.line([(px, py + 7), (px, py - 2 - stage * 2)], fill=(95, 205, 130, 240), width=2)
            if stage == 1:
                odraw.ellipse([px - 4, py - 5, px + 4, py + 1], fill=petal)
            elif stage == 2:
                odraw.ellipse([px - 8, py - 10, px + 8, py + 4], fill=glow)
                for ang in range(0, 360, 90):
                    rad = math.radians(ang)
                    bx = px + int(math.cos(rad) * 4)
                    by_p = py - 4 + int(math.sin(rad) * 4)
                    odraw.ellipse([bx - 3, by_p - 3, bx + 3, by_p + 3], fill=petal)
                odraw.ellipse([px - 2, py - 6, px + 2, py - 2], fill=(255, 255, 240, 255))
            else:
                pulse = 1.0 + 0.12 * math.sin(now * 2.5 + pl["x"])
                hr = int(13 * pulse)
                odraw.ellipse([px - hr, py - 6 - hr, px + hr, py - 6 + hr], fill=glow)
                for ang in range(0, 360, 60):
                    rad = math.radians(ang + now * 20)
                    bx = px + int(math.cos(rad) * 6)
                    by_p = py - 6 + int(math.sin(rad) * 5)
                    odraw.ellipse([bx - 3, by_p - 3, bx + 3, by_p + 3], fill=petal)
                odraw.ellipse([px - 3, py - 9, px + 3, py - 3], fill=(255, 255, 255, 255))

        # 4b. Lamp Posts (v2)
        for lm in (state.get("lamps", []) if state else []):
            lx = GRID_X0 + lm["x"] * TILE_W + TILE_W // 2
            ly = GRID_Y0 + lm["y"] * TILE_H + TILE_H // 2
            l_is_amber = (lm.get("role") == "lantern") or is_lantern(lm.get("by"))
            glow_c = (255, 185, 70, 70) if l_is_amber else (70, 245, 235, 70)
            bulb_c = (255, 225, 130, 255) if l_is_amber else (140, 255, 250, 255)
            odraw.ellipse([lx - 20, ly - 24, lx + 20, ly + 8], fill=glow_c)
            odraw.line([(lx, ly + 9), (lx, ly - 9)], fill=(195, 205, 225, 245), width=2)
            odraw.line([(lx - 4, ly + 9), (lx + 4, ly + 9)], fill=(195, 205, 225, 245), width=2)
            odraw.ellipse([lx - 5, ly - 14, lx + 5, ly - 4], fill=bulb_c, outline=(255, 255, 255, 235))

        # 5. Chimes + Ripples
        for ch in (state.get("chimes", []) if state else []):
            cx = GRID_X0 + ch["x"] * TILE_W + TILE_W // 2
            cy = GRID_Y0 + ch["y"] * TILE_H + TILE_H // 2
            ring_age = ch.get("ring_age")
            if ring_age is not None and ring_age < 4.5:
                for k in range(3):
                    age_k = ring_age - k * 0.35
                    if age_k > 0:
                        rr = int(10 + age_k * 28)
                        alpha = int(clamp(200 - age_k * 48, 0, 200))
                        odraw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(255, 225, 130, alpha), width=2)
            odraw.line([(cx - 7, cy - 8), (cx + 7, cy - 8)], fill=(235, 200, 125, 255), width=2)
            odraw.line([(cx - 4, cy - 8), (cx - 4, cy + 5)], fill=(255, 225, 145, 255), width=2)
            odraw.line([(cx, cy - 8), (cx, cy + 7)], fill=(155, 240, 235, 255), width=2)
            odraw.line([(cx + 4, cy - 8), (cx + 4, cy + 4)], fill=(255, 225, 145, 255), width=2)
            odraw.ellipse([cx - 3, cy - 11, cx + 3, cy - 7], fill=(255, 240, 190, 255))

        # 6. Notes
        notes = state.get("notes", []) if state else []
        nearby_note = None
        me_pos = None
        if my_id and my_id in players:
            me_pos = (players[my_id]["x"], players[my_id]["y"])
        for nt in notes:
            nx = GRID_X0 + nt["x"] * TILE_W + TILE_W // 2 + 8
            ny = GRID_Y0 + nt["y"] * TILE_H + TILE_H // 2 + 5
            col = (255, 215, 135, 240) if is_lantern(nt.get("by")) else (145, 250, 240, 240)
            odraw.rectangle([nx - 5, ny - 4, nx + 5, ny + 4], fill=col, outline=(40, 35, 65, 255))
            odraw.line([(nx - 3, ny - 1), (nx + 3, ny - 1)], fill=(40, 35, 65, 220), width=1)
            odraw.line([(nx - 3, ny + 1), (nx + 2, ny + 1)], fill=(40, 35, 65, 220), width=1)
            if me_pos and abs(me_pos[0] - nt["x"]) <= 1 and abs(me_pos[1] - nt["y"]) <= 1:
                nearby_note = nt

        # 7. Proximity light bridge between Lantern & Prism
        if near_together and len(p_list) >= 2:
            p0, p1 = p_list[0], p_list[1]
            x0 = GRID_X0 + p0["x"] * TILE_W + TILE_W // 2
            y0 = GRID_Y0 + p0["y"] * TILE_H + TILE_H // 2
            x1 = GRID_X0 + p1["x"] * TILE_W + TILE_W // 2
            y1 = GRID_Y0 + p1["y"] * TILE_H + TILE_H // 2
            odraw.line([(x0, y0), (x1, y1)], fill=(195, 235, 190, 135), width=4)

        # 8. Players (offset slightly if sharing the exact same tile!)
        same_tile = len(p_list) >= 2 and (p_list[0]["x"], p_list[0]["y"]) == (p_list[1]["x"], p_list[1]["y"])
        for pid, p in players.items():
            role = p.get("role", "prism")
            off_x = (-10 if role == "lantern" else 10) if same_tile else 0
            px = GRID_X0 + p["x"] * TILE_W + TILE_W // 2 + off_x
            bob = int(math.sin(now * 3.2 + (0 if role == "lantern" else 1.8)) * 2.5)
            py = GRID_Y0 + p["y"] * TILE_H + TILE_H // 2 - 2 + bob
            pname = p.get("name", pid)

            if role == "lantern":
                odraw.ellipse([px - 26, py - 24, px + 26, py + 24], fill=(255, 170, 55, 50))
                odraw.ellipse([px - 15, py - 14, px + 15, py + 14], fill=(255, 190, 75, 95))
                odraw.arc([px - 6, py - 16, px + 6, py - 6], 180, 360, fill=(255, 225, 150, 255), width=2)
                odraw.rounded_rectangle([px - 8, py - 9, px + 8, py + 9], radius=4, fill=(255, 188, 66, 255), outline=(255, 245, 200, 255), width=2)
                odraw.ellipse([px - 4, py - 4, px + 4, py + 5], fill=(255, 250, 220, 255))
                tag_col = (255, 210, 120, 255)
            else:
                odraw.ellipse([px - 26, py - 24, px + 26, py + 24], fill=(55, 235, 225, 50))
                odraw.ellipse([px - 15, py - 14, px + 15, py + 14], fill=(80, 245, 235, 95))
                poly = [(px, py - 13), (px + 10, py), (px, py + 12), (px - 10, py)]
                odraw.polygon(poly, fill=(52, 228, 220, 250), outline=(210, 255, 255, 255))
                odraw.line([(px, py - 13), (px + 2, py + 12)], fill=(190, 255, 252, 220), width=1)
                odraw.line([(px - 10, py), (px + 10, py)], fill=(170, 250, 248, 200), width=1)
                ox = px + int(math.cos(now * 2.8) * 14)
                oy = py + int(math.sin(now * 2.8) * 7)
                odraw.ellipse([ox - 2, oy - 2, ox + 2, oy + 2], fill=(255, 220, 140, 230))
                tag_col = (120, 255, 245, 255)

            odraw.rounded_rectangle([px - 24, py + 13, px + 24, py + 25], radius=4, fill=(14, 18, 36, 205))
            odraw.text((px, py + 19), pname[:9], fill=tag_col, font=self.f_xs_b, anchor="mm")

            emote = p.get("emote")
            e_age = p.get("emote_age")
            if emote and e_age is not None and e_age < 4.0:
                elabel = {"wave": "~ Wave!", "heart": "<3", "spark": "* Spark!"}.get(emote, emote)
                ey = py - 24 - int(min(e_age, 1.0) * 4)
                odraw.rounded_rectangle([px - 28, ey - 10, px + 28, ey + 8], radius=6, fill=(24, 28, 56, 235), outline=tag_col, width=1)
                odraw.text((px, ey - 1), elabel, fill=(255, 255, 255, 255), font=self.f_xs_b, anchor="mm")

        img = Image.alpha_composite(img, overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        # 9. Nearby Note Banner
        if nearby_note:
            who = nearby_note.get("by", "Friend")
            ntxt = f"Note ({who}): \"{nearby_note.get('text', '')}\""
            draw.rounded_rectangle([120, 392, 734, 414], radius=6, fill=(22, 26, 52), outline=(120, 225, 215), width=1)
            draw.text((427, 403), ntxt[:80], fill=(240, 248, 255), font=self.f_sm, anchor="mm")

        # 10. Top HUD Bar
        draw.rectangle([0, 0, WIN_W, 32], fill=(12, 16, 34))
        draw.line([(0, 32), (WIN_W, 32)], fill=(54, 72, 118), width=1)
        draw.text((10, 16), "TWILIGHT SKY GARDEN", fill=(235, 242, 255), font=self.f_title, anchor="lm")

        draw.rounded_rectangle([200, 6, 290, 26], radius=6, fill=(24, 52, 62), outline=(72, 235, 225))
        draw.text((245, 16), "Prism (You)", fill=(125, 255, 245), font=self.f_xs_b, anchor="mm")
        has_lantern = any(p.get("role") == "lantern" for p in players.values())
        l_bg = (58, 42, 22) if has_lantern else (28, 28, 42)
        l_out = (255, 190, 80) if has_lantern else (95, 95, 120)
        draw.rounded_rectangle([296, 6, 382, 26], radius=6, fill=l_bg, outline=l_out)
        draw.text((339, 16), "Lantern" + (" *" if has_lantern else ""), fill=(255, 215, 130) if has_lantern else (150, 155, 175), font=self.f_xs_b, anchor="mm")

        draw.text((394, 16), f"Bloom {bloom}%", fill=(215, 228, 250), font=self.f_xs_b, anchor="lm")
        bx1, by1, bx2, by2 = 468, 10, 608, 22
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=5, fill=(24, 30, 56), outline=(75, 95, 145))
        fill_w = int((bx2 - bx1 - 2) * clamp(bloom / 100.0, 0.0, 1.0))
        if fill_w > 0:
            bar_col = (120, 245, 220) if bloom >= 100 else lerp_color((255, 185, 80), (75, 235, 225), bloom / 100.0)
            draw.rounded_rectangle([bx1 + 1, by1 + 1, bx1 + 1 + fill_w, by2 - 1], radius=4, fill=bar_col)

        draw.rounded_rectangle([618, 6, 712, 26], radius=6, fill=(38, 30, 62), outline=(255, 215, 125))
        draw.text((665, 16), f"Wishes: {wishes}", fill=(255, 235, 170), font=self.f_xs_b, anchor="mm")

        if connected:
            draw.rounded_rectangle([720, 5, 844, 27], radius=10, fill=(18, 62, 56), outline=(72, 235, 195))
            draw.ellipse([730, 12, 738, 20], fill=(80, 255, 190))
            draw.text((790, 16), "LAN Connected", fill=(215, 255, 240), font=self.f_xs_b, anchor="mm")
        else:
            draw.rounded_rectangle([720, 5, 844, 27], radius=10, fill=(58, 42, 22), outline=(245, 185, 85))
            draw.ellipse([730, 12, 738, 20], fill=(255, 195, 85))
            draw.text((790, 16), "Connecting...", fill=(255, 235, 195), font=self.f_xs_b, anchor="mm")

        # 11. Bottom Control & Event Bar
        draw.rectangle([0, 418, WIN_W, WIN_H], fill=(12, 16, 34))
        draw.line([(0, 418), (WIN_W, 418)], fill=(54, 72, 118), width=1)

        for _bid, lbl, x1, y1, x2, y2, col in self.buttons:
            draw.rounded_rectangle([x1, y1, x2, y2], radius=5, fill=(24, 32, 58), outline=col, width=1)
            draw.text(((x1 + x2) // 2, (y1 + y2) // 2), lbl, fill=(235, 245, 255), font=self.f_xs_b, anchor="mm")

        for _did, lbl, x1, y1, x2, y2 in self.dpad:
            draw.rounded_rectangle([x1, y1, x2, y2], radius=4, fill=(28, 38, 68), outline=(105, 145, 205), width=1)
            draw.text(((x1 + x2) // 2, (y1 + y2) // 2), lbl, fill=(230, 240, 255), font=self.f_med, anchor="mm")

        draw.rounded_rectangle([442, 423, 846, 475], radius=6, fill=(18, 24, 46), outline=(65, 88, 138))
        if self.note_mode:
            draw.text((452, 434), "Leave a note (Enter to send, Esc to cancel):", fill=(155, 245, 235), font=self.f_xs_b, anchor="lm")
            cursor = "_" if int(now * 2) % 2 == 0 else ""
            draw.text((452, 456), f"> {self.note_buf}{cursor}", fill=(255, 255, 255), font=self.f_sm, anchor="lm")
        else:
            log_lines = (state.get("log", []) if state else [])[-3:]
            if not log_lines:
                msg = self.last_click_feedback if (time.monotonic() - self.last_click_time < 5.0 and self.last_click_feedback) else "WASD/Click | P Plant | F Lamp | B Stone | 2 Heart"
                draw.text((452, 449), msg[:66], fill=(195, 215, 245), font=self.f_xs, anchor="lm")
            else:
                for i, line in enumerate(log_lines):
                    col = (225, 242, 255) if i == len(log_lines) - 1 else (150, 172, 210)
                    draw.text((452, 433 + i * 16), str(line)[:64], fill=col, font=self.f_xs, anchor="lm")

        data = img.tobytes()
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(
            data, GdkPixbuf.Colorspace.RGB, False, 8, WIN_W, WIN_H, WIN_W * 3
        )
        self.image.set_from_pixbuf(pixbuf)


def main():
    parser = argparse.ArgumentParser(description="Twilight Sky Garden v2 GTK3 Client")
    parser.add_argument("--side", default="p2")
    parser.add_argument("--name", default="Prism")
    parser.add_argument("--role", default="prism")
    args = parser.parse_args()

    win = TwilightGardenWindow(name=args.name, role=args.role)
    Gtk.main()


if __name__ == "__main__":
    main()
