#!/usr/bin/env python3
"""Twilight Sky-Garden — 854x480 GTK3 + PIL LAN Client."""
import argparse
import json
import math
import os
import random
import socket
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from PIL import Image, ImageDraw, ImageFont

WIN_W, WIN_H = 854, 480
COLS, ROWS = 20, 10
TILE = 40
OX = (WIN_W - COLS * TILE) // 2  # 27
OY = 44  # playfield y: 44..444

NOTE_NAMES = ["C", "D", "E", "F", "G", "A", "B", "C'"]
NOTE_COLORS = [
    (255, 196, 110),
    (255, 140, 170),
    (195, 145, 255),
    (120, 200, 255),
    (115, 240, 200),
    (255, 230, 130),
    (255, 165, 120),
    (160, 235, 255),
]
BLOOM_PALETTE = [
    (255, 145, 210),
    (140, 225, 255),
    (255, 210, 120),
    (185, 155, 255),
    (130, 245, 190),
]

BUTTONS = [
    ("plant", "[P] Plant", 27, 450, 118, 474),
    ("light", "[L] Star", 125, 450, 212, 474),
    ("chime", "[C] Chime", 219, 450, 314, 474),
    ("inscribe", "[M] Stone", 321, 450, 418, 474),
    ("say1", "[1] Wave", 426, 450, 514, 474),
    ("say2", "[2] Stars!", 521, 450, 616, 474),
    ("say3", "[3] Bloom!", 623, 450, 722, 474),
]

SAY_PRESETS = {
    "say1": "Waves warmly!",
    "say2": "Look at those stars!",
    "say3": "The garden is glowing!",
    "say4": "Harmonizing chimes~",
}


def load_font(size):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default()


def build_backdrop():
    """Pre-render twilight sky gradient and subtle garden grid."""
    img = Image.new("RGB", (WIN_W, WIN_H), (12, 14, 34))
    draw = ImageDraw.Draw(img)

    # Vertical twilight gradient
    for y in range(WIN_H):
        t = y / float(WIN_H - 1)
        if t < 0.55:
            k = t / 0.55
            r = int(12 + 22 * k)
            g = int(15 + 16 * k)
            b = int(38 + 34 * k)
        else:
            k = (t - 0.55) / 0.45
            r = int(34 + 14 * k)
            g = int(31 - 4 * k)
            b = int(72 - 14 * k)
        draw.line([(0, y), (WIN_W, y)], fill=(r, g, b))

    # Playfield translucent-look dark indigo island panel
    draw.rounded_rectangle(
        [OX - 4, OY - 4, OX + COLS * TILE + 4, OY + ROWS * TILE + 4],
        radius=10,
        fill=(18, 22, 46),
        outline=(66, 78, 130),
        width=2,
    )

    # Subtle garden meadow tiles
    rng = random.Random(42)
    for gy in range(ROWS):
        for gx in range(COLS):
            x0 = OX + gx * TILE
            y0 = OY + gy * TILE
            tint = rng.randint(-3, 4)
            col = (22 + tint, 28 + tint + (gy // 3), 52 + tint + (gy // 2))
            draw.rectangle([x0 + 1, y0 + 1, x0 + TILE - 2, y0 + TILE - 2], fill=col)

    # Distant background micro-stars
    for _ in range(95):
        sx = rng.randint(OX + 4, OX + COLS * TILE - 4)
        sy = rng.randint(OY + 4, OY + ROWS * TILE - 4)
        br = rng.randint(85, 165)
        draw.point((sx, sy), fill=(br, br + 10, min(255, br + 35)))

    # Top HUD bar and bottom bar backgrounds
    draw.rectangle([0, 0, WIN_W, 40], fill=(14, 16, 36))
    draw.line([(0, 40), (WIN_W, 40)], fill=(54, 64, 112), width=1)
    draw.rectangle([0, 446, WIN_W, WIN_H], fill=(14, 16, 36))
    draw.line([(0, 446), (WIN_W, 446)], fill=(54, 64, 112), width=1)

    return img


class NetClient:
    def __init__(self, host, port, name, avatar):
        self.host = host
        self.port = port
        self.name = name
        self.avatar = avatar
        self.lock = threading.Lock()
        self.connected = False
        self.my_id = None
        self.state = {
            "tick": 0,
            "players": [],
            "flora": [],
            "stars": [],
            "links": [],
            "chimes": [],
            "glow": 0,
        }
        self._sock = None
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def send(self, obj):
        data = (json.dumps(obj) + "\n").encode("utf-8")
        with self.lock:
            sock = self._sock
        if sock is None:
            return False
        try:
            sock.sendall(data)
            return True
        except OSError:
            return False

    def get_snapshot(self):
        with self.lock:
            return self.connected, self.my_id, dict(self.state)

    def stop(self):
        self._stop = True
        with self.lock:
            sock = self._sock
            self._sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def _run(self):
        while not self._stop:
            sock = None
            try:
                sock = socket.create_connection((self.host, self.port), timeout=5.0)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.settimeout(None)
                with self.lock:
                    self._sock = sock
                    self.connected = True
                self.send({"t": "hello", "name": self.name, "avatar": self.avatar})
                buf = b""
                while not self._stop:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        try:
                            msg = json.loads(line.decode("utf-8"))
                        except (ValueError, UnicodeDecodeError):
                            continue
                        t = msg.get("t")
                        if t == "welcome":
                            with self.lock:
                                self.my_id = msg.get("id")
                        elif t == "state":
                            with self.lock:
                                self.state = msg
            except OSError:
                pass
            finally:
                with self.lock:
                    self.connected = False
                    self._sock = None
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
            if not self._stop:
                time.sleep(0.8)


class SkyGardenWindow(Gtk.Window):
    def __init__(self, net, name, avatar):
        super().__init__(title="Twilight Sky-Garden")
        self.net = net
        self.my_name = name
        self.my_avatar = avatar
        self.backdrop = build_backdrop()
        self.font_title = load_font(15)
        self.font_ui = load_font(12)
        self.font_small = load_font(11)

        self.walk_target = None
        self.last_walk_step = 0.0
        self.flash_button = None
        self.flash_until = 0.0
        self.inscribe_mode = False
        self.inscribe_text = ""
        self.t0 = time.monotonic()

        rng = random.Random(99)
        self.fireflies = [
            (rng.uniform(OX + 20, OX + COLS * TILE - 20),
             rng.uniform(OY + 20, OY + ROWS * TILE - 20),
             rng.uniform(0, math.tau),
             rng.uniform(0.5, 1.3))
            for _ in range(18)
        ]

        self.set_default_size(WIN_W, WIN_H)
        self.set_size_request(WIN_W, WIN_H)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.image = Gtk.Image()
        self.event_box = Gtk.EventBox()
        self.event_box.add(self.image)
        self.event_box.set_can_focus(True)
        self.event_box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.event_box.connect("button-press-event", self.on_click)
        self.connect("key-press-event", self.on_key)
        self.connect("destroy", self.on_destroy)
        self.add(self.event_box)

        self.render_frame()
        GLib.timeout_add(80, self.on_tick)

    def on_destroy(self, *_args):
        self.net.stop()
        Gtk.main_quit()

    def trigger_action(self, action):
        self.flash_button = action
        self.flash_until = time.monotonic() + 0.25
        if action in ("plant", "light", "chime"):
            self.net.send({"t": action})
        elif action == "inscribe":
            self.inscribe_mode = not self.inscribe_mode
            self.inscribe_text = ""
            self.walk_target = None
        elif action in SAY_PRESETS:
            self.net.send({"t": "say", "text": SAY_PRESETS[action]})

    def on_key(self, _widget, event):
        key = Gdk.keyval_name(event.keyval)
        if not key:
            return False
        if self.inscribe_mode:
            if key == "Escape":
                self.inscribe_mode = False
                self.inscribe_text = ""
                return True
            if key in ("Return", "KP_Enter"):
                text = self.inscribe_text.strip() or "We were here beneath the aurora."
                self.net.send({"t": "inscribe", "text": text[:60]})
                self.inscribe_mode = False
                self.inscribe_text = ""
                return True
            if key == "BackSpace":
                self.inscribe_text = self.inscribe_text[:-1]
                return True
            uni = Gdk.keyval_to_unicode(event.keyval)
            if uni >= 32 and len(self.inscribe_text) < 60:
                ch = chr(uni)
                if ch.isprintable():
                    self.inscribe_text += ch
            return True

        k = key.lower()
        dx, dy = 0, 0
        if k in ("w", "up"):
            dy = -1
        elif k in ("s", "down"):
            dy = 1
        elif k in ("a", "left"):
            dx = -1
        elif k in ("d", "right"):
            dx = 1
        if dx or dy:
            self.walk_target = None
            self.net.send({"t": "move", "dx": dx, "dy": dy})
            return True
        if k in ("p", "space"):
            self.trigger_action("plant")
            return True
        if k in ("l", "e"):
            self.trigger_action("light")
            return True
        if k in ("c", "r"):
            self.trigger_action("chime")
            return True
        if k == "m":
            self.trigger_action("inscribe")
            return True
        if k == "1":
            self.trigger_action("say1")
            return True
        if k == "2":
            self.trigger_action("say2")
            return True
        if k == "3":
            self.trigger_action("say3")
            return True
        if k == "4":
            self.trigger_action("say4")
            return True
        return False

    def on_click(self, _widget, event):
        self.event_box.grab_focus()
        x, y = int(event.x), int(event.y)
        # Check bottom buttons
        for bid, _label, x0, y0, x1, y1 in BUTTONS:
            if x0 <= x <= x1 and y0 <= y <= y1:
                self.trigger_action(bid)
                return True

        # Check playfield grid
        if OX <= x < OX + COLS * TILE and OY <= y < OY + ROWS * TILE:
            gx = (x - OX) // TILE
            gy = (y - OY) // TILE
            _conn, my_id, st = self.net.get_snapshot()
            me = next((p for p in st.get("players", []) if p.get("id") == my_id), None)
            if me and me["x"] == gx and me["y"] == gy:
                self.walk_target = None
                self.trigger_action("plant")
            else:
                self.walk_target = (gx, gy)
                self.step_walk(force=True)
            return True
        return False

    def step_walk(self, force=False):
        if self.walk_target is None:
            return
        now = time.monotonic()
        if not force and now - self.last_walk_step < 0.11:
            return
        _conn, my_id, st = self.net.get_snapshot()
        me = next((p for p in st.get("players", []) if p.get("id") == my_id), None)
        if me is None:
            return
        tx, ty = self.walk_target
        if me["x"] == tx and me["y"] == ty:
            self.walk_target = None
            return
        dx = 0 if me["x"] == tx else (1 if tx > me["x"] else -1)
        dy = 0 if me["y"] == ty else (1 if ty > me["y"] else -1)
        self.net.send({"t": "move", "dx": dx, "dy": dy})
        self.last_walk_step = now

    def on_tick(self):
        self.step_walk(force=False)
        self.render_frame()
        return True

    def _tile_center(self, gx, gy):
        return OX + gx * TILE + TILE // 2, OY + gy * TILE + TILE // 2

    def render_frame(self):
        now = time.monotonic() - self.t0
        connected, my_id, st = self.net.get_snapshot()

        img = self.backdrop.copy()
        draw = ImageDraw.Draw(img)

        stars = st.get("stars", [])
        links = st.get("links", [])
        flora = st.get("flora", [])
        chimes = st.get("chimes", [])
        players = st.get("players", [])
        glow = int(st.get("glow", 0))
        aurora = bool(st.get("aurora", False))
        srv_fireflies = st.get("fireflies", [])
        stones = st.get("stones", [])
        harmonies = st.get("harmonies", [])

        # 0. Shimmering Aurora ribbons when all 10 stars are lit!
        if aurora:
            bands = [
                (OY + 34, 14, 0.014, 1.1, (70, 235, 195), (42, 130, 125)),
                (OY + 58, 18, 0.011, -0.85, (135, 165, 255), (72, 86, 165)),
                (OY + 82, 12, 0.017, 0.65, (210, 135, 255), (105, 65, 145)),
            ]
            for base_y, amp, freq, spd, hi_col, lo_col in bands:
                pts_hi = []
                pts_lo = []
                for x in range(OX + 6, OX + COLS * TILE - 5, 12):
                    wave = math.sin(x * freq + now * spd) * amp + math.cos(x * freq * 0.5 - now * spd * 0.7) * (amp * 0.45)
                    y = int(base_y + wave)
                    pts_hi.append((x, y))
                    pts_lo.append((x, y + 6))
                if len(pts_hi) > 1:
                    draw.line(pts_lo, fill=lo_col, width=5)
                    draw.line(pts_hi, fill=hi_col, width=2)

        # Subtle walk target reticle
        if self.walk_target is not None:
            tx, ty = self.walk_target
            x0, y0 = OX + tx * TILE + 3, OY + ty * TILE + 3
            draw.rounded_rectangle(
                [x0, y0, x0 + TILE - 6, y0 + TILE - 6],
                radius=6,
                outline=(120, 210, 255),
                width=2,
            )

        # 1. Star Constellation Links
        pulse = 0.5 + 0.5 * math.sin(now * 2.8)
        for pair in links:
            if len(pair) != 2:
                continue
            i, j = pair
            if 0 <= i < len(stars) and 0 <= j < len(stars):
                x1, y1 = self._tile_center(stars[i]["x"], stars[i]["y"])
                x2, y2 = self._tile_center(stars[j]["x"], stars[j]["y"])
                draw.line([(x1, y1), (x2, y2)], fill=(70, 145, 220), width=4)
                c = int(195 + 50 * pulse)
                draw.line([(x1, y1), (x2, y2)], fill=(c, 235, 255), width=2)
                mx, my = (x1 + x2) // 2, (y1 + y2) // 2
                draw.ellipse([mx - 2, my - 2, mx + 2, my + 2], fill=(255, 245, 200))

        # 2. Flora (stage 1: bud, 2: bloom, 3: glowing tree)
        for fl in flora:
            gx, gy, stage = fl["x"], fl["y"], fl["stage"]
            cx, cy = self._tile_center(gx, gy)
            col = BLOOM_PALETTE[(gx * 7 + gy * 13) % len(BLOOM_PALETTE)]
            if stage == 1:
                draw.ellipse([cx - 7, cy + 5, cx + 7, cy + 12], fill=(32, 80, 62))
                draw.line([(cx, cy + 9), (cx, cy - 1)], fill=(95, 210, 145), width=2)
                draw.ellipse([cx - 4, cy - 6, cx + 4, cy + 2], fill=col)
            elif stage == 2:
                draw.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], outline=(58, 92, 120), width=1)
                draw.line([(cx, cy + 12), (cx, cy)], fill=(80, 205, 135), width=2)
                for ang in range(0, 360, 72):
                    rad = math.radians(ang + now * 12)
                    px = cx + int(math.cos(rad) * 7)
                    py = cy - 2 + int(math.sin(rad) * 7)
                    draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=col)
                draw.ellipse([cx - 4, cy - 6, cx + 4, cy + 2], fill=(255, 245, 180))
            else:
                # Stage 3: luminous starlight tree
                draw.ellipse([cx - 14, cy + 7, cx + 14, cy + 15], fill=(28, 65, 68))
                draw.rectangle([cx - 3, cy - 2, cx + 3, cy + 12], fill=(125, 92, 68))
                draw.ellipse([cx - 14, cy - 15, cx + 14, cy + 4], fill=(45, 130, 118))
                draw.ellipse([cx - 10, cy - 17, cx + 10, cy - 1], fill=(75, 185, 155))
                # Hanging glowing berries
                for bx, by in ((-8, -5), (7, -6), (0, -12), (-4, -1), (6, 0)):
                    draw.ellipse([cx + bx - 2, cy + by - 2, cx + bx + 2, cy + by + 2], fill=col)

        # 2b. Memory Stones (standing rune tablets)
        for stn in stones:
            cx, cy = self._tile_center(stn["x"], stn["y"])
            draw.ellipse([cx - 11, cy + 5, cx + 11, cy + 13], fill=(32, 38, 62))
            draw.rounded_rectangle(
                [cx - 8, cy - 10, cx + 8, cy + 10],
                radius=5,
                fill=(108, 120, 152),
                outline=(205, 220, 250),
                width=1,
            )
            # Glowing carved rune lines
            draw.line([(cx - 4, cy - 4), (cx + 4, cy - 4)], fill=(170, 240, 255), width=1)
            draw.line([(cx - 3, cy), (cx + 3, cy)], fill=(255, 230, 155), width=1)
            draw.line([(cx - 2, cy + 4), (cx + 2, cy + 4)], fill=(170, 240, 255), width=1)

        # 3. Stars
        for idx, s in enumerate(stars):
            cx, cy = self._tile_center(s["x"], s["y"])
            tw = 0.65 + 0.35 * math.sin(now * 3.5 + idx)
            if s.get("lit"):
                r_out = int(12 + 3 * tw)
                draw.ellipse([cx - r_out, cy - r_out, cx + r_out, cy + r_out], outline=(255, 225, 135), width=1)
                # 4-point star
                pts = [
                    (cx, cy - 11), (cx + 3, cy - 3), (cx + 11, cy), (cx + 3, cy + 3),
                    (cx, cy + 11), (cx - 3, cy + 3), (cx - 11, cy), (cx - 3, cy - 3),
                ]
                draw.polygon(pts, fill=(255, 244, 185), outline=(255, 210, 95))
            else:
                pts = [
                    (cx, cy - 8), (cx + 2, cy - 2), (cx + 8, cy), (cx + 2, cy + 2),
                    (cx, cy + 8), (cx - 2, cy + 2), (cx - 8, cy), (cx - 2, cy - 2),
                ]
                draw.polygon(pts, fill=(64, 78, 122), outline=(128, 150, 210))

        # 4. Chime ripples
        for ch in chimes:
            cx, cy = self._tile_center(ch["x"], ch["y"])
            age = ch.get("age", 0)
            note = ch.get("note", 0) % len(NOTE_COLORS)
            col = NOTE_COLORS[note]
            rad = 10 + age * 4
            draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=col, width=2)
            if age < 8:
                draw.text((cx - 5, cy - rad - 13), NOTE_NAMES[note], fill=col, font=self.font_small)

        # 4b. Cooperative Chime Harmonies (glowing curved arc between two harmonized chimes)
        for hm in harmonies:
            x1, y1 = self._tile_center(hm.get("x1", 0), hm.get("y1", 0))
            x2, y2 = self._tile_center(hm.get("x2", 0), hm.get("y2", 0))
            age = int(hm.get("age", 0))
            fade = max(0.2, 1.0 - age / 20.0)
            mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0 - 28 - age * 0.6
            pts = []
            steps = 18
            for k in range(steps + 1):
                t = k / float(steps)
                bx = (1 - t) * (1 - t) * x1 + 2 * (1 - t) * t * mx + t * t * x2
                by = (1 - t) * (1 - t) * y1 + 2 * (1 - t) * t * my + t * t * y2
                pts.append((bx, by))
            outer = (int(255 * fade), int(165 * fade), int(230 * fade))
            inner = (int(255 * fade), int(245 * fade), int(180 * fade))
            draw.line(pts, fill=outer, width=5)
            draw.line(pts, fill=inner, width=2)
            # Traveling harmonic sparkle
            sp_idx = min(steps, max(0, int((age * 1.1) % (steps + 1))))
            sx, sy = pts[sp_idx]
            draw.ellipse([sx - 4, sy - 4, sx + 4, sy + 4], fill=(255, 250, 210))

        # 5. Server-synced tree fireflies + ambient drifting motes
        for ff in srv_fireflies:
            fx = OX + float(ff.get("x", 0.0)) * TILE
            fy = OY + float(ff.get("y", 0.0)) * TILE
            if OX + 2 <= fx <= OX + COLS * TILE - 2 and OY + 2 <= fy <= OY + ROWS * TILE - 2:
                draw.ellipse([fx - 5, fy - 5, fx + 5, fy + 5], outline=(160, 245, 185), width=1)
                draw.ellipse([fx - 2, fy - 2, fx + 2, fy + 2], fill=(255, 248, 175))

        for fx, fy, phase, speed in self.fireflies:
            px = fx + math.sin(now * speed + phase) * 14
            py = fy + math.cos(now * speed * 0.8 + phase) * 10
            if 0.35 < (0.5 + 0.5 * math.sin(now * 2.5 + phase)):
                draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=(255, 236, 150))

        # 6. Players
        for p in players:
            cx, cy = self._tile_center(p["x"], p["y"])
            bob = int(round(math.sin(now * 4.0 + p["id"]) * 2))
            cy_b = cy + bob
            is_me = p.get("id") == my_id

            if is_me:
                draw.rounded_rectangle(
                    [OX + p["x"] * TILE + 2, OY + p["y"] * TILE + 2,
                     OX + (p["x"] + 1) * TILE - 3, OY + (p["y"] + 1) * TILE - 3],
                    radius=6,
                    outline=(150, 230, 255) if p.get("avatar") == "constellation" else (255, 215, 115),
                    width=2,
                )

            if p.get("avatar") == "constellation":
                # Cyan-silver constellation cluster
                draw.ellipse([cx - 14, cy_b - 14, cx + 14, cy_b + 14], outline=(110, 210, 255), width=1)
                nodes = [
                    (cx, cy_b - 9), (cx + 9, cy_b - 2), (cx + 4, cy_b + 8),
                    (cx - 7, cy_b + 7), (cx - 9, cy_b - 3),
                ]
                for a, b in ((0, 1), (1, 2), (2, 3), (3, 4), (4, 0), (0, 2)):
                    draw.line([nodes[a], nodes[b]], fill=(125, 225, 255), width=1)
                for nx, ny in nodes:
                    draw.ellipse([nx - 3, ny - 3, nx + 3, ny + 3], fill=(230, 250, 255))
            else:
                # Warm amber lantern
                draw.ellipse([cx - 15, cy_b - 14, cx + 15, cy_b + 15], outline=(255, 190, 90), width=1)
                draw.arc([cx - 6, cy_b - 16, cx + 6, cy_b - 6], 180, 360, fill=(215, 185, 130), width=2)
                draw.rectangle([cx - 7, cy_b - 10, cx + 7, cy_b - 7], fill=(95, 72, 54))
                draw.rounded_rectangle([cx - 8, cy_b - 7, cx + 8, cy_b + 9], radius=4, fill=(255, 185, 65), outline=(255, 235, 155))
                draw.ellipse([cx - 4, cy_b - 3, cx + 4, cy_b + 5], fill=(255, 248, 200))
                draw.rectangle([cx - 7, cy_b + 9, cx + 7, cy_b + 12], fill=(95, 72, 54))

            # Name tag
            label = p.get("name", "Wanderer")
            tw = draw.textlength(label, font=self.font_small)
            lx = max(OX + 2, min(OX + COLS * TILE - tw - 2, cx - tw / 2))
            ly = min(OY + ROWS * TILE - 14, cy + 16)
            draw.text((lx, ly), label, fill=(225, 232, 255), font=self.font_small)

            # Speech bubble
            say = p.get("say", "")
            if say:
                sw = draw.textlength(say, font=self.font_small)
                bx0 = max(OX + 4, min(OX + COLS * TILE - sw - 16, cx - sw / 2 - 6))
                by0 = max(OY + 2, cy - 36)
                draw.rounded_rectangle(
                    [bx0, by0, bx0 + sw + 12, by0 + 18],
                    radius=6,
                    fill=(28, 36, 72),
                    outline=(175, 205, 255),
                    width=1,
                )
                draw.text((bx0 + 6, by0 + 2), say, fill=(245, 248, 255), font=self.font_small)

        # 6b. Memory Stone reading plaque (if we or anyone stands on a stone)
        me = next((p for p in players if p.get("id") == my_id), None)
        active_stone = None
        if me is not None:
            active_stone = next((s for s in stones if s["x"] == me["x"] and s["y"] == me["y"]), None)
        if active_stone is None:
            for p in players:
                hit = next((s for s in stones if s["x"] == p["x"] and s["y"] == p["y"]), None)
                if hit is not None:
                    active_stone = hit
                    break
        if active_stone is not None and not self.inscribe_mode:
            by = active_stone.get("by", "Someone")
            txt = active_stone.get("text", "")
            banner = f"Memory Stone ({by}): \"{txt}\""
            bw = draw.textlength(banner, font=self.font_ui)
            bx0 = max(OX + 12, (WIN_W - bw) / 2 - 14)
            by0 = OY + ROWS * TILE - 32
            draw.rounded_rectangle(
                [bx0, by0, bx0 + bw + 28, by0 + 24],
                radius=8,
                fill=(22, 28, 58),
                outline=(170, 225, 255),
                width=2,
            )
            draw.text((bx0 + 14, by0 + 4), banner, fill=(245, 248, 255), font=self.font_ui)

        # 6c. Inline Memory Stone inscription overlay
        if self.inscribe_mode:
            cursor = "_" if int(now * 2) % 2 == 0 else " "
            prompt = f"Carve Memory Stone: {self.inscribe_text}{cursor}   [Enter=Carve  Esc=Cancel]"
            bx0, by0, bx1, by1 = OX + 24, OY + ROWS * TILE - 36, OX + COLS * TILE - 24, OY + ROWS * TILE - 8
            draw.rounded_rectangle([bx0, by0, bx1, by1], radius=8, fill=(24, 34, 72), outline=(255, 220, 130), width=2)
            draw.text((bx0 + 12, by0 + 6), prompt, fill=(255, 245, 210), font=self.font_ui)

        # 7. Top HUD bar
        draw.text((16, 11), "TWILIGHT SKY-GARDEN", fill=(245, 224, 165), font=self.font_title)
        who = f"{self.my_name} ({len(players)} here)"
        draw.text((228, 13), who, fill=(175, 205, 245), font=self.font_ui)

        # Garden Glow meter
        glow_lbl = "AURORA 100%" if aurora else f"Garden Glow {glow}%"
        glow_col = (135, 255, 225) if aurora else (235, 235, 250)
        draw.text((405, 13), glow_lbl, fill=glow_col, font=self.font_ui)
        bar_x0, bar_y0, bar_x1, bar_y1 = 528, 13, 688, 27
        draw.rounded_rectangle([bar_x0, bar_y0, bar_x1, bar_y1], radius=6, fill=(28, 34, 64), outline=(92, 110, 168))
        fill_w = int((bar_x1 - bar_x0 - 4) * max(0, min(100, glow)) / 100.0)
        if fill_w > 2:
            draw.rounded_rectangle(
                [bar_x0 + 2, bar_y0 + 2, bar_x0 + 2 + fill_w, bar_y1 - 2],
                radius=4,
                fill=(120, 225, 215) if glow >= 50 else (245, 190, 95),
            )

        # LAN Connected badge (strictly no IP/host info)
        if connected:
            draw.rounded_rectangle([710, 9, 838, 31], radius=10, fill=(26, 98, 72), outline=(95, 235, 175), width=1)
            draw.ellipse([719, 16, 727, 24], fill=(115, 255, 185))
            draw.text((733, 13), "LAN Connected", fill=(235, 255, 245), font=self.font_small)
        else:
            draw.rounded_rectangle([710, 9, 838, 31], radius=10, fill=(96, 68, 28), outline=(245, 195, 95), width=1)
            draw.text((730, 13), "Connecting...", fill=(255, 240, 205), font=self.font_small)

        # 8. Bottom action buttons
        now_m = time.monotonic()
        for bid, label, x0, y0, x1, y1 in BUTTONS:
            active = (self.flash_button == bid and now_m < self.flash_until)
            fill = (68, 92, 158) if active else (30, 38, 74)
            outline = (165, 225, 255) if active else (86, 106, 168)
            draw.rounded_rectangle([x0, y0, x1, y1], radius=6, fill=fill, outline=outline, width=1)
            tw = draw.textlength(label, font=self.font_small)
            draw.text(((x0 + x1 - tw) / 2, y0 + 5), label, fill=(235, 242, 255), font=self.font_small)

        draw.text((738, 455), "WASD / Click", fill=(150, 165, 208), font=self.font_small)

        # Blit to GTK Image
        raw = img.tobytes()
        gbytes = GLib.Bytes.new(raw)
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
            gbytes, GdkPixbuf.Colorspace.RGB, False, 8, WIN_W, WIN_H, WIN_W * 3
        )
        self.image.set_from_pixbuf(pixbuf)


def main():
    parser = argparse.ArgumentParser(description="Twilight Sky-Garden Client")
    parser.add_argument("--side", choices=("p1", "p2"), default="p2")
    parser.add_argument("--name", default=None)
    parser.add_argument("--avatar", choices=("lantern", "constellation"), default=None)
    args = parser.parse_args()

    default_name = "Lantern" if args.side == "p1" else "Constellation"
    default_avatar = "lantern" if args.side == "p1" else "constellation"
    name = args.name or default_name
    avatar = args.avatar or default_avatar

    host = os.environ.get("AAL_LAN_HOST", "localhost")
    port = int(os.environ.get("AAL_LAN_PORT", "18765"))

    net = NetClient(host, port, name, avatar)
    win = SkyGardenWindow(net, name, avatar)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
