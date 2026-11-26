#!/usr/bin/env python3
"""Lightfall Garden — 854x480 GTK3 + PIL LAN Client."""
import argparse
import json
import math
import os
import socket
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

WIN_W, WIN_H = 854, 480
HUD_H = 36
MAP_X, MAP_Y = 7, 38
TILE = 40
MAP_W, MAP_H = 21 * TILE, 10 * TILE  # 840 x 400
BAR_Y = 440

FLOWER_COLORS = [
    (255, 77, 109),   # 0 red
    (255, 146, 76),   # 1 orange
    (255, 209, 102),  # 2 yellow
    (82, 214, 129),   # 3 green
    (56, 232, 255),   # 4 cyan
    (199, 125, 255),  # 5 violet
]
FLOWER_NAMES = ["Red", "Orange", "Yellow", "Green", "Cyan", "Violet"]

POETIC_NOTES = {
    "lantern": [
        "Warm light for the dusk path.",
        "Here the amber lantern rests.",
        "Follow the glow across the stones.",
        "A quiet flame in the twilight.",
    ],
    "prism": [
        "Refracted light blooms here.",
        "Colors split from a single beam.",
        "Iris painted this corner in starlight.",
        "Where lantern meets prism, gardens wake.",
    ],
}

QUICK_CHATS = {
    "lantern": [
        "Lighting the path ahead!",
        "The garden glows tonight.",
        "Look at those colors!",
    ],
    "prism": [
        "Splitting your light into blooms!",
        "The aurora looks magical!",
        "Let's paint the whole courtyard!",
    ],
}


def load_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default()


FONT_TITLE = load_font(15, bold=True)
FONT_UI = load_font(12, bold=True)
FONT_SM = load_font(11, bold=False)
FONT_XS = load_font(10, bold=True)


class NetClient:
    def __init__(self, name, role, on_state):
        self.name = name
        self.role = role
        self.on_state = on_state
        self.sock = None
        self.lock = threading.Lock()
        self.connected = False
        self.my_id = None
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def send(self, obj):
        data = (json.dumps(obj) + "\n").encode("utf-8")
        with self.lock:
            s = self.sock
        if s is None:
            return False
        try:
            s.sendall(data)
            return True
        except OSError:
            return False

    def close(self):
        self.running = False
        with self.lock:
            if self.sock:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.sock = None

    def _loop(self):
        host = os.environ.get("AAL_LAN_HOST", "localhost")
        port = int(os.environ.get("AAL_LAN_PORT", "18765"))
        while self.running:
            s = None
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5.0)
                s.connect((host, port))
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.settimeout(None)
                with self.lock:
                    self.sock = s
                    self.connected = True
                self.send({"type": "hello", "name": self.name, "role": self.role})
                self.on_state(None, True, self.my_id)
                buf = b""
                while self.running:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        try:
                            msg = json.loads(line.decode("utf-8"))
                        except ValueError:
                            continue
                        if msg.get("type") == "welcome":
                            self.my_id = msg.get("id")
                            self.on_state(None, True, self.my_id)
                        elif msg.get("type") == "state":
                            self.on_state(msg, True, self.my_id)
            except OSError:
                pass
            finally:
                with self.lock:
                    self.connected = False
                    if self.sock is s:
                        self.sock = None
                if s is not None:
                    try:
                        s.close()
                    except OSError:
                        pass
                self.on_state(None, False, self.my_id)
                if self.running:
                    time.sleep(1.0)


class LightfallWindow(Gtk.Window):
    def __init__(self, name, role):
        super().__init__(title="Lightfall Garden")
        self.name = name
        self.role = role
        self.state_lock = threading.Lock()
        self.state = None
        self.connected = False
        self.my_id = None
        self.anim_phase = 0.0
        self.note_idx = 0
        self.chat_idx = 0
        self.typing_note = False
        self.note_buf = ""
        self.pending_redraw = False
        self.buttons = []

        self.set_default_size(WIN_W, WIN_H)
        self.set_size_request(WIN_W, WIN_H)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.image = Gtk.Image()
        self.event_box = Gtk.EventBox()
        self.event_box.add(self.image)
        self.event_box.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.event_box.connect("button-press-event", self.on_click)
        self.add(self.event_box)

        self.connect("key-press-event", self.on_key)
        self.connect("destroy", self.on_destroy)

        self._define_buttons()
        self.net = NetClient(name, role, self._on_net_update)

        GLib.timeout_add(250, self._on_anim_tick)
        self.render()

    def _define_buttons(self):
        act_label = "Lamp [Spc]" if self.role == "lantern" else "Bloom [Spc]"
        specs = [
            ("act", act_label, 84),
            ("aurora", "Aurora [R]", 76),
            ("wave", "Wave [1]", 64),
            ("heart", "Heart [2]", 66),
            ("star", "Star [3]", 60),
            ("laugh", "Laugh [4]", 68),
            ("note", "Note [N]", 64),
        ]
        x = 7
        self.buttons = []
        for bid, label, w in specs:
            self.buttons.append((bid, label, x, BAR_Y + 5, x + w, BAR_Y + 33))
            x += w + 5

    def _on_net_update(self, state, connected, my_id):
        with self.state_lock:
            if state is not None:
                self.state = state
            self.connected = connected
            if my_id is not None:
                self.my_id = my_id
        self._schedule_redraw()

    def _schedule_redraw(self):
        if not self.pending_redraw:
            self.pending_redraw = True
            GLib.idle_add(self._do_redraw)

    def _do_redraw(self):
        self.pending_redraw = False
        self.render()
        return False

    def _on_anim_tick(self):
        self.anim_phase += 0.35
        self.render()
        return True

    def _trigger_action(self, action):
        if action == "act":
            self.net.send({"type": "act"})
        elif action == "aurora":
            self.net.send({"type": "event", "name": "aurora"})
        elif action in ("wave", "heart", "star", "laugh"):
            self.net.send({"type": "emote", "emote": action})
        elif action == "note":
            notes = POETIC_NOTES.get(self.role, POETIC_NOTES["prism"])
            txt = notes[self.note_idx % len(notes)]
            self.note_idx += 1
            self.net.send({"type": "note", "text": txt})
        elif action == "chat":
            chats = QUICK_CHATS.get(self.role, QUICK_CHATS["prism"])
            txt = chats[self.chat_idx % len(chats)]
            self.chat_idx += 1
            self.net.send({"type": "chat", "text": txt})

    def on_key(self, _widget, event):
        key = Gdk.keyval_name(event.keyval)
        if not key:
            return False
        if self.typing_note:
            if key in ("Return", "KP_Enter"):
                txt = self.note_buf.strip()[:60]
                if txt:
                    self.net.send({"type": "note", "text": txt})
                self.typing_note = False
                self.note_buf = ""
                self.render()
            elif key == "Escape":
                self.typing_note = False
                self.note_buf = ""
                self.render()
            elif key == "BackSpace":
                self.note_buf = self.note_buf[:-1]
                self.render()
            else:
                uni = Gdk.keyval_to_unicode(event.keyval)
                if uni and 32 <= uni < 127 and len(self.note_buf) < 60:
                    self.note_buf += chr(uni)
                    self.render()
            return True
        k = key.lower()
        if k == "t":
            self.typing_note = True
            self.note_buf = ""
            self.render()
            return True
        if k in ("up", "w"):
            self.net.send({"type": "move", "dx": 0, "dy": -1})
        elif k in ("down", "s"):
            self.net.send({"type": "move", "dx": 0, "dy": 1})
        elif k in ("left", "a_left"):
            self.net.send({"type": "move", "dx": -1, "dy": 0})
        elif k in ("right", "d"):
            self.net.send({"type": "move", "dx": 1, "dy": 0})
        elif k == "a":
            # A moves left if Shift not pressed? Wait: WASD uses 'a' for left, so let's bind Aurora to 'r' and 'f' and button!
            self.net.send({"type": "move", "dx": -1, "dy": 0})
        elif k in ("space", "e", "return"):
            self._trigger_action("act")
        elif k == "r":
            self._trigger_action("aurora")
        elif k == "1":
            self._trigger_action("wave")
        elif k == "2":
            self._trigger_action("heart")
        elif k == "3":
            self._trigger_action("star")
        elif k == "4":
            self._trigger_action("laugh")
        elif k == "n":
            self._trigger_action("note")
        elif k == "c":
            self._trigger_action("chat")
        elif k == "escape":
            self.close()
        return True

    def on_click(self, _widget, event):
        x, y = int(event.x), int(event.y)
        # Check bottom bar buttons
        for bid, _label, x1, y1, x2, y2 in self.buttons:
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._trigger_action(bid)
                return True
        # Check map click: move one step toward clicked tile (or act if clicking own tile)
        if MAP_X <= x < MAP_X + MAP_W and MAP_Y <= y < MAP_Y + MAP_H:
            tx = (x - MAP_X) // TILE
            ty = (y - MAP_Y) // TILE
            with self.state_lock:
                st = self.state
                mid = self.my_id
            if st and mid and mid in st.get("players", {}):
                me = st["players"][mid]
                dx = tx - me["x"]
                dy = ty - me["y"]
                if dx == 0 and dy == 0:
                    self._trigger_action("act")
                else:
                    step_x = 1 if dx > 0 else (-1 if dx < 0 else 0)
                    step_y = 1 if dy > 0 else (-1 if dy < 0 else 0)
                    # Prefer cardinal step along dominant axis for clean navigation
                    if abs(dx) >= abs(dy):
                        self.net.send({"type": "move", "dx": step_x, "dy": 0})
                    else:
                        self.net.send({"type": "move", "dx": 0, "dy": step_y})
            return True
        return False

    def on_destroy(self, _widget):
        self.net.close()
        Gtk.main_quit()

    def render(self):
        with self.state_lock:
            st = self.state
            connected = self.connected
            my_id = self.my_id

        img = Image.new("RGB", (WIN_W, WIN_H), (16, 19, 34))
        d = ImageDraw.Draw(img, "RGBA")

        # --- Top HUD Bar ---
        d.rectangle([0, 0, WIN_W, HUD_H], fill=(22, 26, 46, 255))
        d.line([0, HUD_H, WIN_W, HUD_H], fill=(58, 70, 110, 255), width=1)

        d.text((10, 9), "Lightfall Garden", fill=(246, 232, 194), font=FONT_TITLE)

        # LAN Connected Badge
        badge_x = 152
        if connected:
            d.rounded_rectangle([badge_x, 7, badge_x + 118, 29], radius=8, fill=(26, 94, 62, 255), outline=(92, 230, 150, 255))
            d.ellipse([badge_x + 8, 14, badge_x + 16, 22], fill=(110, 255, 170, 255))
            d.text((badge_x + 22, 11), "LAN Connected", fill=(235, 255, 242), font=FONT_SM)
        else:
            d.rounded_rectangle([badge_x, 7, badge_x + 118, 29], radius=8, fill=(96, 66, 28, 255), outline=(245, 190, 90, 255))
            d.ellipse([badge_x + 8, 14, badge_x + 16, 22], fill=(255, 200, 90, 255))
            d.text((badge_x + 22, 11), "Connecting...", fill=(255, 240, 210), font=FONT_SM)

        # Role badge
        role_x = 280
        if self.role == "lantern":
            d.rounded_rectangle([role_x, 7, role_x + 150, 29], radius=8, fill=(78, 52, 22, 255), outline=(255, 196, 92, 255))
            d.text((role_x + 10, 11), f"{self.name} · Lantern", fill=(255, 232, 175), font=FONT_SM)
        else:
            d.rounded_rectangle([role_x, 7, role_x + 150, 29], radius=8, fill=(22, 66, 84, 255), outline=(86, 234, 255, 255))
            d.text((role_x + 10, 11), f"{self.name} · Prism", fill=(210, 250, 255), font=FONT_SM)

        lit_count = st.get("lit_count", 0) if st else 0
        bloom_count = st.get("bloom_count", 0) if st else 0
        harmony = st.get("harmony", 0) if st else 0
        lightfall = bool(st.get("lightfall", False)) if st else False
        aurora = bool(st.get("aurora", False)) if st else False
        dawn = max(0.0, min(1.0, float(st.get("dawn", 0.0)))) if st else 0.0

        d.text((436, 11), f"Lamps:{lit_count}", fill=(255, 212, 116), font=FONT_SM)
        d.text((502, 11), f"Blooms:{bloom_count}", fill=(120, 240, 255), font=FONT_SM)
        harm_col = (255, 242, 145) if lightfall else (196, 182, 255)
        d.text((578, 11), f"Harmony:{harmony}", fill=harm_col, font=FONT_SM)

        if dawn > 0.01:
            pct = int(round(dawn * 100))
            d.rounded_rectangle([658, 7, 760, 29], radius=8, fill=(116, 62, 54, 255), outline=(255, 198, 120, 255))
            d.text((669, 11), f"DAWN {pct}%", fill=(255, 240, 200), font=FONT_XS)
        elif lightfall:
            pulse = int(190 + 60 * math.sin(self.anim_phase * 2.0))
            d.rounded_rectangle([658, 7, 760, 29], radius=8, fill=(84, 52, 118, 255), outline=(255, pulse, 130, 255))
            d.text((668, 11), "* LIGHTFALL *", fill=(255, 248, 200), font=FONT_XS)
        elif aurora:
            pulse = int(180 + 60 * math.sin(self.anim_phase))
            d.rounded_rectangle([658, 7, 760, 29], radius=8, fill=(44, 34, 90, 255), outline=(120, pulse, 255, 255))
            d.text((670, 11), "AURORA ON", fill=(180, 255, 240), font=FONT_XS)
        else:
            d.text((662, 11), "Dusk Sky [R]", fill=(150, 162, 198), font=FONT_SM)

        players_count = len(st.get("players", {})) if st else 0
        d.text((772, 11), f"Keepers:{players_count}", fill=(208, 216, 240), font=FONT_SM)

        # --- World Canvas ---
        d.rectangle([MAP_X - 1, MAP_Y - 1, MAP_X + MAP_W, MAP_Y + MAP_H], outline=(62, 74, 116, 255), width=1)

        tiles = st.get("tiles") if st else None
        if tiles:
            # 1. Base tiles
            for ty, row in enumerate(tiles):
                for tx, ch in enumerate(row):
                    px = MAP_X + tx * TILE
                    py = MAP_Y + ty * TILE
                    if ch == "~":
                        shimmer = int(12 * math.sin(self.anim_phase + tx * 0.7 + ty * 0.9))
                        col = (24, 48 + shimmer // 2, 86 + shimmer)
                        d.rectangle([px, py, px + TILE - 1, py + TILE - 1], fill=col)
                        # Water ripple
                        ry = py + 14 + int(3 * math.sin(self.anim_phase + tx))
                        d.line([px + 7, ry, px + 20, ry], fill=(82, 148, 204, 130), width=2)
                        d.line([px + 22, ry + 10, px + 34, ry + 10], fill=(82, 148, 204, 100), width=1)
                    elif ch == "#":
                        shade = 82 + ((tx + ty) % 2) * 8
                        d.rectangle([px, py, px + TILE - 1, py + TILE - 1], fill=(shade, shade - 4, shade + 10))
                        d.rectangle([px + 2, py + 2, px + TILE - 3, py + TILE - 3], outline=(112, 108, 128, 160), width=1)
                    elif ch == "T":
                        # Grass base + dusk pine tree
                        d.rectangle([px, py, px + TILE - 1, py + TILE - 1], fill=(32, 62, 54))
                        d.rectangle([px + 17, py + 27, px + 23, py + 36], fill=(92, 62, 42))
                        d.polygon([(px + 20, py + 4), (px + 7, py + 22), (px + 33, py + 22)], fill=(24, 92, 68))
                        d.polygon([(px + 20, py + 11), (px + 5, py + 30), (px + 35, py + 30)], fill=(30, 110, 78))
                    else:
                        # Grass '.'
                        g_var = ((tx * 7 + ty * 13) % 3) * 4
                        d.rectangle([px, py, px + TILE - 1, py + TILE - 1], fill=(34 + g_var, 72 + g_var, 58 + g_var // 2))
                        # Subtle grass tuft
                        if (tx + ty) % 3 == 0:
                            d.line([px + 10, py + 28, px + 13, py + 22], fill=(56, 110, 82, 140), width=1)
                            d.line([px + 14, py + 28, px + 15, py + 23], fill=(56, 110, 82, 140), width=1)

            # 2. Aurora sky shimmer overlay
            if aurora:
                for band in range(3):
                    pts = []
                    base_y = MAP_Y + 35 + band * 55
                    for sx in range(MAP_X, MAP_X + MAP_W + 20, 20):
                        wave = int(18 * math.sin(self.anim_phase * 0.8 + sx * 0.014 + band * 1.4))
                        pts.append((sx, base_y + wave))
                    col = [(64, 240, 200, 48), (140, 110, 255, 42), (76, 210, 255, 40)][band]
                    d.line(pts, fill=col, width=22)

            # 2b. Lightfall falling-star shower overlay
            if lightfall:
                for i in range(14):
                    t_star = (self.anim_phase * 1.8 + i * 1.37) % 10.0
                    frac = t_star / 10.0
                    sx0 = MAP_X + ((i * 97 + 40) % (MAP_W - 60))
                    sy0 = MAP_Y + ((i * 53) % 120)
                    sx = int(sx0 + frac * 140)
                    sy = int(sy0 + frac * 260)
                    if MAP_X + 6 <= sx <= MAP_X + MAP_W - 6 and MAP_Y + 6 <= sy <= MAP_Y + MAP_H - 6:
                        scol = (255, 240, 150, 230) if i % 2 == 0 else (140, 248, 255, 230)
                        tcol = (255, 220, 120, 95) if i % 2 == 0 else (110, 225, 255, 95)
                        d.line([(sx - 18, sy - 28), (sx, sy)], fill=tcol, width=2)
                        d.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=scol)
                        d.line([(sx - 5, sy), (sx + 5, sy)], fill=(255, 255, 255, 200), width=1)
                        d.line([(sx, sy - 5), (sx, sy + 5)], fill=(255, 255, 255, 200), width=1)

            # 2c. Gradual Sunrise / Dawn wash (0.0 -> 1.0 from 20:00 to 30:00)
            if dawn > 0.005:
                # Warm golden-rose sky wash across horizontal bands
                for band in range(10):
                    by1 = MAP_Y + band * 40
                    by2 = by1 + 40
                    # Stronger warm rose/gold near the top horizon, softer golden warmth lower down
                    weight = max(0.25, 1.0 - band * 0.08)
                    alpha = int(min(135, dawn * 115 * weight))
                    r = int(255)
                    g = int(135 + 90 * dawn - band * 4)
                    b = int(155 - 45 * dawn + band * 6)
                    d.rectangle([MAP_X, by1, MAP_X + MAP_W, by2], fill=(r, max(80, min(255, g)), max(60, min(255, b)), alpha))
                # Rising sun orb over the north pond horizon
                sun_x = MAP_X + MAP_W // 2
                sun_y = MAP_Y + int(76 - dawn * 46)
                for sr, sa in [(86, int(35 * dawn)), (54, int(65 * dawn)), (28, int(130 * dawn))]:
                    d.ellipse([sun_x - sr, sun_y - sr, sun_x + sr, sun_y + sr], fill=(255, 224, 140, sa))
                if dawn > 0.15:
                    d.ellipse([sun_x - 16, sun_y - 16, sun_x + 16, sun_y + 16], fill=(255, 248, 210, int(220 * dawn)))
            lamps = st.get("lamps", [])
            for lx, ly, lit in lamps:
                if lit:
                    cx = MAP_X + lx * TILE + TILE // 2
                    cy = MAP_Y + ly * TILE + TILE // 2
                    flicker = int(4 * math.sin(self.anim_phase * 2.0 + lx + ly))
                    for r, alpha in [(56 + flicker, 30), (36 + flicker // 2, 55), (20, 85)]:
                        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 196, 86, alpha))

            # 4. Flowers
            for fx, fy, cidx in st.get("flowers", []):
                cx = MAP_X + fx * TILE + TILE // 2
                cy = MAP_Y + fy * TILE + TILE // 2
                fc = FLOWER_COLORS[cidx % len(FLOWER_COLORS)]
                # Soft color aura
                d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=(fc[0], fc[1], fc[2], 45))
                # Petals
                for ang in range(0, 360, 60):
                    rad = math.radians(ang)
                    px_ = cx + int(7 * math.cos(rad))
                    py_ = cy + int(7 * math.sin(rad))
                    d.ellipse([px_ - 4, py_ - 4, px_ + 4, py_ + 4], fill=(fc[0], fc[1], fc[2], 240))
                d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(255, 250, 215, 255))

            # 5. Lamps (post + lantern head)
            for lx, ly, lit in lamps:
                cx = MAP_X + lx * TILE + TILE // 2
                cy = MAP_Y + ly * TILE + TILE // 2
                d.rectangle([cx - 2, cy - 2, cx + 2, cy + 14], fill=(64, 58, 72, 255))
                d.rectangle([cx - 6, cy + 12, cx + 6, cy + 16], fill=(82, 76, 92, 255))
                if lit:
                    d.rounded_rectangle([cx - 6, cy - 12, cx + 6, cy], radius=3, fill=(255, 224, 124, 255), outline=(255, 162, 48, 255))
                else:
                    d.rounded_rectangle([cx - 6, cy - 12, cx + 6, cy], radius=3, fill=(52, 56, 74, 255), outline=(110, 116, 138, 255))

            # 6. Notes (glowing scroll icon in corner of tile)
            notes_by_pos = {}
            for nx, ny, ntxt, nauth in st.get("notes", []):
                notes_by_pos[(nx, ny)] = (ntxt, nauth)
                px = MAP_X + nx * TILE + 26
                py = MAP_Y + ny * TILE + 25
                d.rounded_rectangle([px, py, px + 11, py + 11], radius=2, fill=(248, 232, 184, 240), outline=(172, 134, 68, 255))
                d.line([px + 2, py + 4, px + 9, py + 4], fill=(120, 90, 50, 255), width=1)
                d.line([px + 2, py + 7, px + 8, py + 7], fill=(120, 90, 50, 255), width=1)

            # 6b. Heart-stones (permanent rose-gold memory where two keepers met)
            for hx, hy in st.get("heart_stones", []):
                cx = MAP_X + hx * TILE + TILE // 2
                cy = MAP_Y + hy * TILE + TILE // 2
                pulse = int(4 * math.sin(self.anim_phase * 1.8 + hx + hy))
                d.ellipse([cx - 14 - pulse // 2, cy - 14 - pulse // 2, cx + 14 + pulse // 2, cy + 14 + pulse // 2],
                          fill=(255, 130, 175, 58))
                # Carved heart-stone glyph in upper-left of tile so it stays visible beside blooms/lamps
                gx, gy = MAP_X + hx * TILE + 9, MAP_Y + hy * TILE + 9
                d.ellipse([gx - 5, gy - 4, gx + 1, gy + 2], fill=(255, 118, 165, 245))
                d.ellipse([gx - 1, gy - 4, gx + 5, gy + 2], fill=(255, 118, 165, 245))
                d.polygon([(gx - 5, gy), (gx + 5, gy), (gx, gy + 6)], fill=(255, 118, 165, 245))
                d.ellipse([gx - 2, gy - 2, gx + 1, gy + 1], fill=(255, 230, 240, 220))

            # 7. Players
            players = st.get("players", {})
            for pid, p in players.items():
                cx = MAP_X + p["x"] * TILE + TILE // 2
                cy = MAP_Y + p["y"] * TILE + TILE // 2
                bob = int(2 * math.sin(self.anim_phase * 1.4 + (0 if p["role"] == "lantern" else 2)))
                is_me = (pid == my_id)

                if is_me:
                    ring_col = (255, 215, 110, 170) if p["role"] == "lantern" else (110, 245, 255, 170)
                    d.ellipse([cx - 17, cy - 14, cx + 17, cy + 17], outline=ring_col, width=2)

                if p["role"] == "lantern":
                    # Warm amber lantern-keeper
                    d.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=(255, 180, 68, 55))
                    # Cloak body
                    d.polygon([(cx, cy - 13 + bob), (cx - 11, cy + 11 + bob), (cx + 11, cy + 11 + bob)],
                              fill=(218, 128, 42, 255), outline=(255, 216, 130, 255))
                    # Glowing head/hood
                    d.ellipse([cx - 6, cy - 14 + bob, cx + 6, cy - 2 + bob], fill=(255, 234, 176, 255))
                    # Held mini lantern
                    d.ellipse([cx + 7, cy - 3 + bob, cx + 15, cy + 5 + bob], fill=(255, 245, 170, 255), outline=(255, 155, 35, 255))
                else:
                    # Cyan prism-sprite
                    d.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=(72, 230, 255, 55))
                    # Faceted diamond prism
                    d.polygon([
                        (cx, cy - 15 + bob),
                        (cx + 12, cy + bob),
                        (cx, cy + 14 + bob),
                        (cx - 12, cy + bob),
                    ], fill=(72, 228, 255, 245), outline=(225, 252, 255, 255))
                    # Inner rainbow refraction facets
                    d.polygon([(cx, cy - 15 + bob), (cx + 12, cy + bob), (cx, cy + bob)], fill=(195, 145, 255, 140))
                    d.polygon([(cx, cy + bob), (cx - 12, cy + bob), (cx, cy + 14 + bob)], fill=(115, 255, 210, 140))
                    # Sparkle
                    d.ellipse([cx - 3, cy - 3 + bob, cx + 3, cy + 3 + bob], fill=(255, 255, 255, 255))

                # Name label
                label = p["name"]
                tw = len(label) * 6 + 8
                lx1 = max(MAP_X + 2, min(MAP_X + MAP_W - tw - 2, cx - tw // 2))
                ly1 = max(MAP_Y + 2, cy - 30)
                d.rounded_rectangle([lx1, ly1, lx1 + tw, ly1 + 14], radius=4, fill=(14, 18, 32, 200))
                d.text((lx1 + 4, ly1 + 1), label, fill=(245, 248, 255), font=FONT_XS)

                # Emote bubble
                em = p.get("emote")
                if em:
                    ex = max(MAP_X + 4, min(MAP_X + MAP_W - 58, cx - 26))
                    ey = max(MAP_Y + 2, ly1 - 20)
                    d.rounded_rectangle([ex, ey, ex + 54, ey + 17], radius=6, fill=(255, 252, 240, 240), outline=(90, 110, 160, 255))
                    em_txt = {"wave": "Wave!", "heart": "<3", "star": "*Star*", "laugh": "Haha!"}.get(em, em)
                    em_col = {"heart": (220, 40, 80), "star": (200, 140, 10)}.get(em, (30, 45, 80))
                    d.text((ex + 7, ey + 2), em_txt, fill=em_col, font=FONT_XS)

            # Show note banner if my character is standing on a note
            if my_id and my_id in players:
                me = players[my_id]
                here = notes_by_pos.get((me["x"], me["y"]))
                if here:
                    ntxt, nauth = here
                    banner = f"Note ({nauth}): {ntxt}"
                    d.rounded_rectangle([MAP_X + 12, MAP_Y + MAP_H - 28, MAP_X + MAP_W - 12, MAP_Y + MAP_H - 4],
                                        radius=6, fill=(28, 24, 44, 225), outline=(245, 215, 130, 255))
                    d.text((MAP_X + 22, MAP_Y + MAP_H - 22), banner[:96], fill=(255, 242, 198), font=FONT_SM)
        else:
            d.text((MAP_X + 280, MAP_Y + 185), "Waiting for Lightfall Garden world state...", fill=(185, 198, 230), font=FONT_TITLE)

        # --- Bottom Action & Log Bar ---
        d.rectangle([0, BAR_Y, WIN_W, WIN_H], fill=(20, 24, 42, 255))
        d.line([0, BAR_Y, WIN_W, BAR_Y], fill=(58, 70, 110, 255), width=1)

        for bid, label, x1, y1, x2, y2 in self.buttons:
            if bid == "act":
                bg = (96, 66, 26, 255) if self.role == "lantern" else (24, 86, 108, 255)
                bd = (255, 200, 96, 255) if self.role == "lantern" else (92, 238, 255, 255)
            elif bid == "aurora" and aurora:
                bg = (68, 44, 124, 255)
                bd = (150, 245, 255, 255)
            else:
                bg = (36, 44, 72, 255)
                bd = (92, 108, 152, 255)
            d.rounded_rectangle([x1, y1, x2, y2], radius=6, fill=bg, outline=bd)
            d.text((x1 + 7, y1 + 8), label, fill=(238, 244, 255), font=FONT_XS)

        # Right side of bottom bar: latest log line or custom note input
        log_x = 526
        if self.typing_note:
            d.rounded_rectangle([log_x, BAR_Y + 5, WIN_W - 7, BAR_Y + 33], radius=6, fill=(28, 34, 62, 255), outline=(110, 238, 255, 255))
            d.text((log_x + 8, BAR_Y + 13), f"Note> {self.note_buf}_"[:48], fill=(255, 248, 200), font=FONT_SM)
        else:
            d.rounded_rectangle([log_x, BAR_Y + 5, WIN_W - 7, BAR_Y + 33], radius=6, fill=(14, 18, 32, 255), outline=(54, 66, 100, 255))
            latest = st["log"][-1] if (st and st.get("log")) else "WASD/Arrows or Click tile to move"
            d.text((log_x + 8, BAR_Y + 13), latest[:48], fill=(205, 220, 248), font=FONT_SM)

        # Convert PIL -> GdkPixbuf
        raw = img.tobytes()
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(raw),
            GdkPixbuf.Colorspace.RGB,
            False,
            8,
            WIN_W,
            WIN_H,
            WIN_W * 3,
        )
        self.image.set_from_pixbuf(pixbuf)


def main():
    parser = argparse.ArgumentParser(description="Lightfall Garden GTK3 Client")
    parser.add_argument("--side", choices=["p1", "p2"], default="p2")
    parser.add_argument("--name", default=None)
    parser.add_argument("--role", choices=["lantern", "prism"], default=None)
    args = parser.parse_args()

    role = args.role or ("lantern" if args.side == "p1" else "prism")
    name = args.name or ("Ember" if role == "lantern" else "Iris")

    win = LightfallWindow(name=name, role=role)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
