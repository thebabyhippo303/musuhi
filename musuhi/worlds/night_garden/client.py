#!/usr/bin/env python3
"""Lantern & Prism — Night Garden (854x480 GTK3 + PIL LAN Client)."""

import argparse
import json
import math
import os
import queue
import random
import socket
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from PIL import Image, ImageChops, ImageDraw, ImageFont

WIDTH = 854
HEIGHT = 480
HUD_TOP = 34
HUD_BOTTOM = 448

PLANT_BTN = (734, 449, 844, 475)


def _load_font(size):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _make_radial_glow(radius, rgb, max_alpha=180, power=2.2):
    size = radius * 2
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    r_c, g_c, b_c = rgb
    inv_r = 1.0 / max(1, radius)
    for y in range(size):
        dy = (y - radius + 0.5) * inv_r
        dy2 = dy * dy
        for x in range(size):
            dx = (x - radius + 0.5) * inv_r
            d2 = dx * dx + dy2
            if d2 < 1.0:
                a = int(max_alpha * ((1.0 - math.sqrt(d2)) ** power))
                if a > 0:
                    px[x, y] = (r_c, g_c, b_c, a)
    return img


def _parse_color(color_val, fallback=(255, 200, 110)):
    if isinstance(color_val, (list, tuple)) and len(color_val) >= 3:
        return (int(color_val[0]), int(color_val[1]), int(color_val[2]))
    if isinstance(color_val, str):
        s = color_val.strip().lstrip("#")
        if len(s) == 6:
            try:
                return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
            except ValueError:
                pass
    return fallback


class NetworkClient:
    def __init__(self, host, port, player_name):
        self.host = host
        self.port = port
        self.player_name = player_name
        self.sock = None
        self.lock = threading.Lock()
        self.connected = False
        self.player_id = None
        self.latest_state = None
        self.out_q = queue.Queue()
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def send_msg(self, obj):
        try:
            line = (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")
            self.out_q.put_nowait(line)
        except Exception:
            pass

    def stop(self):
        self.running = False
        with self.lock:
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None

    def _run(self):
        while self.running:
            s = None
            try:
                s = socket.create_connection((self.host, self.port), timeout=4.0)
                s.settimeout(0.05)
                try:
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except Exception:
                    pass
                with self.lock:
                    self.sock = s
                    self.connected = True
                # Drain stale queued messages and send hello
                while not self.out_q.empty():
                    try:
                        self.out_q.get_nowait()
                    except queue.Empty:
                        break
                hello = (
                    json.dumps({"t": "hello", "name": self.player_name}) + "\n"
                ).encode("utf-8")
                s.sendall(hello)

                buf = b""
                while self.running:
                    # Flush outgoing
                    while not self.out_q.empty():
                        try:
                            data = self.out_q.get_nowait()
                            s.sendall(data)
                        except queue.Empty:
                            break
                    try:
                        chunk = s.recv(65536)
                        if not chunk:
                            break
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                msg = json.loads(line.decode("utf-8"))
                            except Exception:
                                continue
                            mtype = msg.get("t")
                            if mtype == "welcome":
                                self.player_id = msg.get("id")
                            elif mtype == "state":
                                self.latest_state = msg
                    except socket.timeout:
                        continue
            except Exception:
                pass
            finally:
                with self.lock:
                    self.connected = False
                    if self.sock:
                        try:
                            self.sock.close()
                        except Exception:
                            pass
                        self.sock = None
            if self.running:
                time.sleep(0.8)


class NightGardenApp:
    def __init__(self, side, name):
        self.side = side
        self.name = name
        host = os.environ.get("AAL_LAN_HOST", "localhost")
        port = int(os.environ.get("AAL_LAN_PORT", "18765"))
        self.net = NetworkClient(host, port, name)

        self.px = 260.0 if side == "p1" else 590.0
        self.py = 240.0
        self.target_x = None
        self.target_y = None
        self.keys_down = set()
        self.last_move_sent = 0.0
        self.start_time = time.monotonic()
        self.trail = []
        self.trails = {}  # pid -> list of (x, y, t_mono)
        self.typing_chat = False
        self.chat_buf = ""
        self.local_flash = []  # (x, y, t0, color)

        self.font_sm = _load_font(12)
        self.font_md = _load_font(14)

        self.bg_base = self._build_background()
        self.glow_lantern = _make_radial_glow(105, (255, 185, 75), max_alpha=155, power=2.0)
        self.glow_lantern_core = _make_radial_glow(36, (255, 240, 180), max_alpha=210, power=1.8)
        self.glow_prism_a = _make_radial_glow(105, (90, 225, 255), max_alpha=145, power=2.0)
        self.glow_prism_b = _make_radial_glow(105, (185, 115, 255), max_alpha=145, power=2.0)
        self.glow_prism_c = _make_radial_glow(105, (110, 255, 200), max_alpha=145, power=2.0)
        self.glow_overlap = _make_radial_glow(75, (255, 250, 225), max_alpha=125, power=1.9)
        self.glow_bloom_gold = _make_radial_glow(44, (255, 215, 110), max_alpha=140, power=2.1)
        self.glow_bloom_cyan = _make_radial_glow(44, (110, 240, 255), max_alpha=140, power=2.1)
        self.glow_bloom_rose = _make_radial_glow(44, (255, 130, 215), max_alpha=140, power=2.1)
        self.glow_seed = _make_radial_glow(18, (170, 255, 195), max_alpha=120, power=2.0)
        self.glow_firefly = _make_radial_glow(12, (230, 255, 150), max_alpha=175, power=2.0)
        self.glow_moon = _make_radial_glow(88, (220, 238, 255), max_alpha=110, power=2.2)

        self.win = Gtk.Window(title=f"Lantern & Prism · Night Garden ({name})")
        self.win.set_default_size(WIDTH, HEIGHT)
        self.win.set_resizable(False)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.win.connect("destroy", self._on_destroy)
        self.win.connect("key-press-event", self._on_key_press)
        self.win.connect("key-release-event", self._on_key_release)

        self.event_box = Gtk.EventBox()
        self.event_box.set_events(
            Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.event_box.connect("button-press-event", self._on_click)

        self.image = Gtk.Image()
        self.image.set_size_request(WIDTH, HEIGHT)
        self.event_box.add(self.image)
        self.win.add(self.event_box)
        self.win.show_all()

        self._render_frame()
        GLib.timeout_add(50, self._tick)

    def _build_background(self):
        img = Image.new("RGB", (WIDTH, HEIGHT), (10, 16, 28))
        draw = ImageDraw.Draw(img)
        # Subtle twilight vertical gradient
        for y in range(HEIGHT):
            t = y / float(HEIGHT)
            r = int(9 + 11 * t)
            g = int(14 + 20 * t)
            b = int(28 + 18 * (1.0 - abs(t - 0.5) * 1.4))
            draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))

        rng = random.Random(42)
        # Soft garden moss patches
        for _ in range(36):
            cx = rng.randint(20, WIDTH - 20)
            cy = rng.randint(HUD_TOP + 15, HUD_BOTTOM - 15)
            rx = rng.randint(25, 85)
            ry = rng.randint(15, 48)
            col = (
                rng.randint(12, 22),
                rng.randint(26, 42),
                rng.randint(30, 46),
            )
            draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=col)

        # Garden stepping stones
        stones = [
            (170, 250, 18, 11),
            (225, 270, 15, 10),
            (285, 285, 19, 12),
            (350, 290, 16, 10),
            (535, 175, 17, 11),
            (590, 190, 15, 10),
            (645, 210, 18, 11),
        ]
        for sx, sy, rx, ry in stones:
            draw.ellipse(
                [sx - rx, sy - ry, sx + rx, sy + ry],
                fill=(34, 44, 58),
                outline=(52, 66, 84),
            )

        # Subtle grass blades & dew specks
        for _ in range(180):
            gx = rng.randint(10, WIDTH - 10)
            gy = rng.randint(HUD_TOP + 10, HUD_BOTTOM - 10)
            gh = rng.randint(4, 10)
            lean = rng.randint(-3, 3)
            draw.line([(gx, gy), (gx + lean, gy - gh)], fill=(22, 52, 46), width=1)
        for _ in range(70):
            sx = rng.randint(12, WIDTH - 12)
            sy = rng.randint(HUD_TOP + 8, HUD_BOTTOM - 8)
            c = rng.randint(55, 95)
            draw.point((sx, sy), fill=(c, c + 20, c + 35))

        return img

    def _on_destroy(self, *_args):
        self.net.stop()
        Gtk.main_quit()

    def _on_key_press(self, _widget, event):
        keyval = event.keyval
        name = (Gdk.keyval_name(keyval) or "").lower()
        if self.typing_chat:
            if name == "escape":
                self.typing_chat = False
                self.chat_buf = ""
            elif name in ("return", "kp_enter"):
                txt = self.chat_buf.strip()[:60]
                if txt:
                    self.net.send_msg({"t": "chat", "text": txt})
                self.typing_chat = False
                self.chat_buf = ""
            elif name == "backspace":
                self.chat_buf = self.chat_buf[:-1]
            else:
                uni = Gdk.keyval_to_unicode(keyval)
                if uni and 32 <= uni <= 126 and len(self.chat_buf) < 60:
                    self.chat_buf += chr(uni)
            return True

        if name == "t":
            self.typing_chat = True
            self.chat_buf = ""
            self.keys_down.clear()
            return True
        if name in ("w", "a", "s", "d", "up", "down", "left", "right"):
            self.keys_down.add(name)
            self.target_x = None
            self.target_y = None
        elif name in ("space", "e", "return", "p"):
            self._plant_at(self.px, self.py)
        return True

    def _on_key_release(self, _widget, event):
        name = (Gdk.keyval_name(event.keyval) or "").lower()
        self.keys_down.discard(name)
        return True

    def _on_click(self, _widget, event):
        x = float(event.x)
        y = float(event.y)
        # Check [Plant Seed] HUD button
        bx0, by0, bx1, by1 = PLANT_BTN
        if bx0 <= x <= bx1 and by0 <= y <= by1:
            self._plant_at(self.px, self.py)
            return True

        cx = max(16.0, min(WIDTH - 16.0, x))
        cy = max(HUD_TOP + 14.0, min(HUD_BOTTOM - 14.0, y))

        shift_held = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        if event.button == 3 or shift_held:
            self._plant_at(cx, cy)
        elif event.button == 1:
            self.target_x = cx
            self.target_y = cy
            self.net.send_msg({"t": "move", "x": round(cx, 1), "y": round(cy, 1)})
        return True

    def _plant_at(self, x, y):
        cx = max(16.0, min(WIDTH - 16.0, x))
        cy = max(HUD_TOP + 14.0, min(HUD_BOTTOM - 14.0, y))
        self.net.send_msg({"t": "plant", "x": round(cx, 1), "y": round(cy, 1)})
        self.local_flash.append((cx, cy, time.monotonic(), (180, 255, 220)))

    def _tick(self):
        now = time.monotonic()
        speed = 9.0
        dx = 0.0
        dy = 0.0
        if "a" in self.keys_down or "left" in self.keys_down:
            dx -= 1.0
        if "d" in self.keys_down or "right" in self.keys_down:
            dx += 1.0
        if "w" in self.keys_down or "up" in self.keys_down:
            dy -= 1.0
        if "s" in self.keys_down or "down" in self.keys_down:
            dy += 1.0

        moved = False
        if dx != 0.0 or dy != 0.0:
            mag = math.hypot(dx, dy)
            self.px = max(16.0, min(WIDTH - 16.0, self.px + (dx / mag) * speed))
            self.py = max(HUD_TOP + 14.0, min(HUD_BOTTOM - 14.0, self.py + (dy / mag) * speed))
            moved = True
        elif self.target_x is not None and self.target_y is not None:
            tx = self.target_x - self.px
            ty = self.target_y - self.py
            dist = math.hypot(tx, ty)
            if dist <= speed:
                self.px, self.py = self.target_x, self.target_y
                self.target_x = None
                self.target_y = None
                moved = True
            else:
                self.px += (tx / dist) * speed
                self.py += (ty / dist) * speed
                moved = True

        if moved and (now - self.last_move_sent) >= 0.06:
            self.net.send_msg({"t": "move", "x": round(self.px, 1), "y": round(self.py, 1)})
            self.last_move_sent = now

        # Keep local position synced if server has authoritative coordinates and we're idle
        st = self.net.latest_state
        if st and not moved and self.net.player_id is not None:
            for p in st.get("players", []):
                if p.get("id") == self.net.player_id:
                    sx, sy = float(p.get("x", self.px)), float(p.get("y", self.py))
                    if math.hypot(sx - self.px, sy - self.py) > 60:
                        self.px, self.py = sx, sy
                    break

        self._render_frame()
        return True

    def _paste_glow(self, canvas, glow_img, cx, cy):
        r = glow_img.width // 2
        x0 = int(cx - r)
        y0 = int(cy - r)
        canvas.alpha_composite(glow_img, (x0, y0))

    def _draw_flower(self, draw, x, y, stage, kind, t, glow=0.5):
        ix, iy = int(x), int(y)
        pulse = 0.85 + 0.15 * math.sin(t * 3.0 + x * 0.05) + 0.1 * float(glow or 0.0)
        if stage <= 0:
            draw.ellipse([ix - 4, iy - 4, ix + 4, iy + 4], fill=(160, 235, 180), outline=(235, 255, 235))
        elif stage == 1:
            draw.line([(ix, iy + 4), (ix, iy - 6)], fill=(105, 225, 145), width=2)
            draw.ellipse([ix - 6, iy - 8, ix, iy - 2], fill=(125, 245, 175))
            draw.ellipse([ix, iy - 9, ix + 6, iy - 3], fill=(140, 255, 200))
        elif stage == 2:
            draw.line([(ix, iy + 6), (ix, iy - 8)], fill=(95, 215, 155), width=2)
            draw.ellipse([ix - 7, iy - 13, ix + 7, iy - 1], fill=(175, 225, 255), outline=(240, 250, 255))
            draw.ellipse([ix - 3, iy - 10, ix + 3, iy - 4], fill=(255, 240, 175))
        else:
            # Stage 3: radiant bloom ("amber", "spectrum", "hybrid")
            k = str(kind or "").lower()
            if k == "amber":
                petal_cols = [(255, 210, 95), (255, 185, 75)]
                core_col = (255, 252, 215)
                petals = 6
            elif k == "spectrum":
                petal_cols = [(110, 240, 255), (185, 130, 255), (120, 255, 205)]
                core_col = (240, 255, 255)
                petals = 6
            else:
                # hybrid: lantern gold + prism iridescence!
                petal_cols = [(255, 215, 105), (110, 240, 255), (255, 145, 225), (150, 255, 195)]
                core_col = (255, 255, 235)
                petals = 8
            rad = int(12 * pulse)
            for i in range(petals):
                ang = (2.0 * math.pi * i / petals) + math.sin(t * 0.7 + x * 0.02) * 0.12
                px = ix + math.cos(ang) * rad
                py = iy + math.sin(ang) * rad
                pcol = petal_cols[i % len(petal_cols)]
                draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=pcol)
            draw.ellipse([ix - 6, iy - 6, ix + 6, iy + 6], fill=core_col)

    def _render_frame(self):
        t = time.monotonic() - self.start_time
        frame = self.bg_base.copy().convert("RGBA")
        draw = ImageDraw.Draw(frame, "RGBA")

        st = self.net.latest_state or {}
        players = st.get("players", [])
        seeds = st.get("seeds", [])
        fireflies = st.get("fireflies", [])
        ripples = st.get("ripples", [])
        pond = st.get("pond")

        # Rising Moon & Prism Moonbow driven purely by state.blooms (0 -> 30)
        raw_blooms = int(st.get("blooms", sum(1 for s in seeds if int(s.get("stage", 0)) >= 3)))
        moon_prog = max(0.0, min(1.0, raw_blooms / 30.0))
        moon_x = 427.0
        moon_y = 178.0 - moon_prog * 102.0  # rises from 178 up to 76 at 30 blooms
        if raw_blooms > 0:
            self._paste_glow(frame, self.glow_moon, moon_x, moon_y)
            draw = ImageDraw.Draw(frame, "RGBA")
            # Prism moonbow arc over the rising moon
            bow_alpha = int(28 + 115 * moon_prog)
            bow_colors = [
                (255, 130, 210, bow_alpha),
                (255, 210, 110, bow_alpha),
                (130, 255, 195, bow_alpha),
                (100, 225, 255, bow_alpha),
                (175, 130, 255, bow_alpha),
            ]
            for idx_b, bcol in enumerate(bow_colors):
                br = 54 + idx_b * 5
                draw.arc(
                    [moon_x - br, moon_y - br * 0.78, moon_x + br, moon_y + br * 0.78],
                    start=195,
                    end=345,
                    fill=bcol,
                    width=3,
                )
            # Luminous moon disc
            mr = 18 + int(6 * moon_prog)
            m_alpha = int(120 + 135 * moon_prog)
            draw.ellipse(
                [moon_x - mr, moon_y - mr, moon_x + mr, moon_y + mr],
                fill=(242, 248, 255, m_alpha),
                outline=(255, 252, 225, m_alpha),
                width=2,
            )
            # Subtle lunar craters
            draw.ellipse(
                [moon_x - mr * 0.45, moon_y - mr * 0.25, moon_x - mr * 0.1, moon_y + mr * 0.1],
                fill=(210, 222, 238, int(m_alpha * 0.55)),
            )
            draw.ellipse(
                [moon_x + mr * 0.12, moon_y + mr * 0.15, moon_x + mr * 0.42, moon_y + mr * 0.42],
                fill=(210, 222, 238, int(m_alpha * 0.45)),
            )

        # Draw moonlit pond
        if isinstance(pond, dict):
            pcx = float(pond.get("x", pond.get("cx", 427)))
            pcy = float(pond.get("y", pond.get("cy", 250)))
            prx = float(pond.get("rx", pond.get("r", 105)))
            pry = float(pond.get("ry", pond.get("r", 62)))
        else:
            pcx, pcy, prx, pry = 427.0, 255.0, 108.0, 62.0

        draw.ellipse(
            [pcx - prx - 4, pcy - pry - 4, pcx + prx + 4, pcy + pry + 4],
            fill=(24, 48, 66, 170),
        )
        draw.ellipse(
            [pcx - prx, pcy - pry, pcx + prx, pcy + pry],
            fill=(14, 38, 62, 225),
            outline=(70, 130, 170, 150),
            width=2,
        )
        # Moon + prism reflection in the pond
        if raw_blooms > 0:
            ref_a = int(45 + 115 * moon_prog)
            wobble = math.sin(t * 2.1) * 4.0
            rx_m = 16 + 10 * moon_prog
            ry_m = 7 + 5 * moon_prog
            draw.ellipse(
                [pcx - rx_m + wobble, pcy - ry_m, pcx + rx_m + wobble, pcy + ry_m],
                fill=(225, 242, 255, ref_a),
            )
            draw.arc(
                [pcx - rx_m * 1.5 - wobble, pcy - ry_m * 1.5, pcx + rx_m * 1.5 - wobble, pcy + ry_m * 1.5],
                start=20,
                end=160,
                fill=(150, 230, 255, int(ref_a * 0.7)),
                width=2,
            )
        # Gentle pond shimmer
        shimmer_dx = math.sin(t * 1.4) * 6.0
        draw.arc(
            [pcx - prx * 0.65 + shimmer_dx, pcy - pry * 0.45, pcx + prx * 0.25 + shimmer_dx, pcy + pry * 0.15],
            start=195,
            end=330,
            fill=(130, 200, 240, 65),
            width=2,
        )

        # Draw pond ripples
        for rip in ripples:
            rx = float(rip.get("x", pcx))
            ry = float(rip.get("y", pcy))
            rr = float(rip.get("r", 12))
            alpha = max(25, min(200, int(210 - rr * 2.2)))
            draw.ellipse(
                [rx - rr, ry - rr * 0.72, rx + rr, ry + rr * 0.72],
                outline=(140, 235, 255, alpha),
                width=2,
            )

        # Draw local plant feedback rings
        now = time.monotonic()
        self.local_flash = [f for f in self.local_flash if now - f[2] < 0.7]
        for fx, fy, ft0, fcol in self.local_flash:
            age = (now - ft0) / 0.7
            rr = 8 + age * 28
            a = int(190 * (1.0 - age))
            draw.ellipse([fx - rr, fy - rr, fx + rr, fy + rr], outline=(*fcol, a), width=2)

        # Fallback local player display if server hasn't sent state yet
        if not players:
            players = [
                {
                    "id": self.net.player_id or 0,
                    "name": self.name,
                    "x": self.px,
                    "y": self.py,
                    "color": "#ffbe55" if self.side == "p1" else "#78e6ff",
                }
            ]

        # Light halos for seeds/blooms
        for s in seeds:
            sx = float(s.get("x", 0))
            sy = float(s.get("y", 0))
            stage = int(s.get("stage", 0))
            kind = str(s.get("kind", "star"))
            if stage >= 3:
                h = abs(hash(kind)) % 3
                glow = (self.glow_bloom_gold, self.glow_bloom_cyan, self.glow_bloom_rose)[h]
                self._paste_glow(frame, glow, sx, sy)
            elif stage >= 1:
                self._paste_glow(frame, self.glow_seed, sx, sy)

        # Light halos for players
        for p in players:
            px = float(p.get("x", 0))
            py = float(p.get("y", 0))
            pname = str(p.get("name", "")).lower()
            if "lantern" in pname or p.get("id") == 1:
                self._paste_glow(frame, self.glow_lantern, px, py)
                self._paste_glow(frame, self.glow_lantern_core, px, py)
            else:
                phase = (t * 0.45) % 3.0
                if phase < 1.0:
                    self._paste_glow(frame, self.glow_prism_a, px, py)
                elif phase < 2.0:
                    self._paste_glow(frame, self.glow_prism_b, px, py)
                else:
                    self._paste_glow(frame, self.glow_prism_c, px, py)

        # Overlap magic glow when 2 players are near each other!
        if len(players) >= 2:
            p0, p1 = players[0], players[1]
            dx = float(p0.get("x", 0)) - float(p1.get("x", 0))
            dy = float(p0.get("y", 0)) - float(p1.get("y", 0))
            if math.hypot(dx, dy) < 170:
                mx = (float(p0.get("x", 0)) + float(p1.get("x", 0))) * 0.5
                my = (float(p0.get("y", 0)) + float(p1.get("y", 0))) * 0.5
                self._paste_glow(frame, self.glow_overlap, mx, my)

        # Re-create draw after alpha_composite
        draw = ImageDraw.Draw(frame, "RGBA")

        # Constellation threads linking nearby blooms
        bloom_pts = [
            (float(s.get("x", 0)), float(s.get("y", 0)))
            for s in seeds
            if int(s.get("stage", 0)) >= 3
        ]
        for i in range(len(bloom_pts)):
            x1, y1 = bloom_pts[i]
            for j in range(i + 1, len(bloom_pts)):
                x2, y2 = bloom_pts[j]
                d = math.hypot(x2 - x1, y2 - y1)
                if d < 105.0:
                    twinkle = 0.65 + 0.35 * math.sin(t * 2.2 + i * 0.7 + j * 0.3)
                    alpha_l = int((1.0 - d / 105.0) * 95 * twinkle)
                    if alpha_l > 8:
                        draw.line([(x1, y1), (x2, y2)], fill=(140, 235, 255, alpha_l), width=1)

        # Update & draw glowing light-painting trails for players
        now_m = time.monotonic()
        for p in players:
            pid = p.get("id", p.get("name", "0"))
            px = float(p.get("x", 0))
            py = float(p.get("y", 0))
            pname = str(p.get("name", "")).lower()
            pts = self.trails.setdefault(pid, [])
            if not pts or math.hypot(px - pts[-1][0], py - pts[-1][1]) >= 4.0:
                pts.append((px, py, now_m))
            # Keep last 7 seconds of trail
            pts[:] = [pt for pt in pts if now_m - pt[2] < 7.0][-90:]
            is_lan = "lantern" in pname
            for k in range(1, len(pts)):
                x0, y0, t0 = pts[k - 1]
                x1, y1, t1 = pts[k]
                age = (now_m - t1) / 7.0
                a = max(0, min(180, int(175 * (1.0 - age))))
                if is_lan:
                    tcol = (255, 200, 95, a)
                else:
                    hue_i = (k // 4) % 4
                    prism_cols = [(100, 235, 255), (185, 130, 255), (120, 255, 205), (255, 155, 225)]
                    tcol = (*prism_cols[hue_i], a)
                draw.line([(x0, y0), (x1, y1)], fill=tcol, width=3)

        # Draw seeds/plants
        bloom_count = 0
        for s in seeds:
            stage = int(s.get("stage", 0))
            if stage >= 3:
                bloom_count += 1
            self._draw_flower(
                draw,
                float(s.get("x", 0)),
                float(s.get("y", 0)),
                stage,
                s.get("kind", "hybrid"),
                t,
                s.get("glow", 0.5),
            )
        if "blooms" in st:
            bloom_count = int(st.get("blooms", bloom_count))

        # Draw fireflies
        for f in fireflies:
            fx = float(f.get("x", 0))
            fy = float(f.get("y", 0))
            self._paste_glow(frame, self.glow_firefly, fx, fy)
        draw = ImageDraw.Draw(frame, "RGBA")
        for f in fireflies:
            fx = float(f.get("x", 0))
            fy = float(f.get("y", 0))
            draw.ellipse([fx - 2, fy - 2, fx + 2, fy + 2], fill=(250, 255, 200, 255))

        # Draw players (Lantern vs Prism avatars!)
        for p in players:
            px = float(p.get("x", 0))
            py = float(p.get("y", 0))
            pname = str(p.get("name", "guest"))
            col = _parse_color(p.get("color"))
            is_lantern = "lantern" in pname.lower()
            if is_lantern:
                # Warm lantern icon
                draw.rounded_rectangle([px - 7, py - 9, px + 7, py + 9], radius=3, fill=(255, 220, 120, 255), outline=(255, 248, 215, 255), width=2)
                draw.line([(px - 5, py - 11), (px + 5, py - 11)], fill=(210, 175, 110, 255), width=2)
            else:
                # Rotating crystal prism diamond
                ang = t * 1.1
                pts = []
                for k in range(4):
                    a = ang + k * (math.pi / 2.0)
                    r_len = 11 if k % 2 == 0 else 8
                    pts.append((px + math.cos(a) * r_len, py + math.sin(a) * r_len))
                draw.polygon(pts, fill=(165, 240, 255, 245), outline=(255, 255, 255, 255))
                draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=(255, 220, 255, 255))
            # Name tag
            draw.text((px - 18, py + 13), pname, fill=(235, 245, 255, 220), font=self.font_sm)
            # Optional chat bubble above light (supports up to 60 chars)
            chat_txt = str(p.get("chat") or "").strip()[:60]
            if chat_txt:
                tw = min(440, max(72, len(chat_txt) * 7 + 20))
                bx0 = max(8, min(WIDTH - tw - 8, int(px - tw * 0.5)))
                by0 = max(HUD_TOP + 4, int(py - 40))
                draw.rounded_rectangle(
                    [bx0, by0, bx0 + tw, by0 + 22],
                    radius=7,
                    fill=(14, 24, 42, 232),
                    outline=(155, 225, 255, 225),
                    width=1,
                )
                draw.text((bx0 + 10, by0 + 4), chat_txt, fill=(245, 252, 255, 255), font=self.font_sm)

        # Top HUD Bar
        draw.rectangle([0, 0, WIDTH, HUD_TOP], fill=(8, 13, 24, 215))
        draw.line([(0, HUD_TOP), (WIDTH, HUD_TOP)], fill=(55, 85, 120, 160), width=1)
        draw.text((14, 9), "Lantern & Prism · Night Garden", fill=(235, 244, 255, 255), font=self.font_md)

        # Stats
        stats_txt = f"Blooms: {bloom_count}   Seeds: {len(seeds)}   Fireflies: {len(fireflies)}"
        draw.text((315, 10), stats_txt, fill=(185, 220, 245, 245), font=self.font_sm)

        # LAN Connected Badge (strictly no IPs!)
        if self.net.connected:
            badge_bg = (18, 72, 48, 235)
            badge_border = (80, 220, 145, 255)
            dot_col = (100, 255, 165, 255)
            badge_txt = "LAN Connected"
        else:
            badge_bg = (82, 54, 18, 235)
            badge_border = (240, 185, 80, 255)
            dot_col = (255, 200, 90, 255)
            badge_txt = "Connecting..."
        draw.rounded_rectangle([WIDTH - 142, 6, WIDTH - 10, 28], radius=10, fill=badge_bg, outline=badge_border, width=1)
        draw.ellipse([WIDTH - 132, 13, WIDTH - 124, 21], fill=dot_col)
        draw.text((WIDTH - 118, 10), badge_txt, fill=(240, 255, 245, 255), font=self.font_sm)

        # Bottom Controls Bar
        draw.rectangle([0, HUD_BOTTOM, WIDTH, HEIGHT], fill=(8, 13, 24, 215))
        draw.line([(0, HUD_BOTTOM), (WIDTH, HUD_BOTTOM)], fill=(55, 85, 120, 160), width=1)
        if self.typing_chat:
            draw.text(
                (14, HUD_BOTTOM + 8),
                f"Haiku / Note (Enter to send, Esc to cancel):  {self.chat_buf}_",
                fill=(255, 240, 165, 255),
                font=self.font_sm,
            )
        else:
            draw.text(
                (14, HUD_BOTTOM + 8),
                "Click/WASD: Move  |  Right-Click/Space: Plant  |  T: Type Note/Haiku",
                fill=(175, 205, 230, 235),
                font=self.font_sm,
            )
        # Clickable Plant Seed button
        bx0, by0, bx1, by1 = PLANT_BTN
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=6, fill=(32, 84, 96, 240), outline=(120, 235, 255, 240), width=1)
        draw.text((bx0 + 18, by0 + 6), "Plant Seed", fill=(240, 255, 255, 255), font=self.font_sm)

        rgb = frame.convert("RGB")
        data = rgb.tobytes()
        pb = GdkPixbuf.Pixbuf.new_from_data(
            data, GdkPixbuf.Colorspace.RGB, False, 8, WIDTH, HEIGHT, WIDTH * 3
        )
        self.image.set_from_pixbuf(pb)


def main():
    parser = argparse.ArgumentParser(description="Lantern & Prism Night Garden Client")
    parser.add_argument("--side", choices=["p1", "p2"], default="p2")
    parser.add_argument("--name", default=None)
    args = parser.parse_args()
    name = args.name or ("lantern" if args.side == "p1" else "prism")
    NightGardenApp(args.side, name)
    Gtk.main()


if __name__ == "__main__":
    main()
