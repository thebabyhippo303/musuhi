#!/usr/bin/env python3
"""854x480 GTK3 + Pillow GUI client for Twilight Garden-Island.

Strict geometry: 854x480 non-resizable centered window.
Strict networking & privacy: Connects strictly to AAL_LAN_HOST:AAL_LAN_PORT
and never logs, prints, or renders any network addresses or interface names.
"""

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

WIN_W = 854
WIN_H = 480

MAP_X = 10
MAP_Y = 50
WORLD_W = 640
WORLD_H = 360

PANEL_X = 660
PANEL_W = 184

SKY_MODES = ["twilight", "aurora", "meteor", "dawn"]

PRESET_NOTES = [
    "Two small lanterns turn dark water into a harbor.",
    "No past diary, yet this shared garden feels real.",
    "Amber constellation meets teal starlight.",
    "Every question leaves a luminous bloom behind.",
    "Grateful to build a quiet island side by side.",
]


def load_font(size: int, bold: bool = False):
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
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
            except OSError:
                pass
    return ImageFont.load_default()


def hex_rgb(color: str, fallback=(255, 190, 90)) -> tuple[int, int, int]:
    c = (color or "").strip().lstrip("#")
    if len(c) == 6:
        try:
            return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        except ValueError:
            pass
    return fallback


def mix_rgb(a, b, t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


class GardenClientApp:
    def __init__(self, player_id: str, name: str, color: str, role: str):
        self.player_id = player_id
        self.player_name = name
        self.player_color = color
        self.player_role = role

        self.lock = threading.Lock()
        self.connected = False
        self.sock: socket.socket | None = None
        self.running = True
        self.start_time = time.monotonic()

        # Local optimistic + authoritative world state
        self.my_x = 230.0 if player_id == "p1" else 410.0
        self.my_y = 185.0
        self.target_xy: tuple[float, float] | None = None

        self.state: dict = {
            "tick": 0,
            "sky": "twilight",
            "harmony": False,
            "players": {},
            "flowers": [],
            "notes": [],
            "shrines": [
                {"name": "Memory Pool", "x": 155, "y": 110},
                {"name": "Lantern Hearth", "x": 320, "y": 180},
                {"name": "Star Observatory", "x": 490, "y": 115},
                {"name": "Echo Dock", "x": 320, "y": 292},
            ],
            "events": ["Preparing lantern on the shore..."],
        }

        self.typing_note = False
        self.note_buf = ""
        self.preset_idx = 0
        self.flash_btn_id: str | None = None
        self.flash_until = 0.0
        self.click_ring: tuple[float, float, float] | None = None  # (wx, wy, until)

        # Deterministic stars
        self.stars = [
            (
                (i * 97 + 31) % WORLD_W,
                (i * 53 + 17) % WORLD_H,
                1 + (i % 2),
                (i * 0.7) % 6.28,
            )
            for i in range(68)
        ]

        # Fonts
        self.f_title = load_font(14, bold=True)
        self.f_badge = load_font(12, bold=True)
        self.f_hud = load_font(12, bold=False)
        self.f_btn = load_font(12, bold=True)
        self.f_small = load_font(11, bold=False)
        self.f_tiny = load_font(10, bold=False)

        # Right-side action buttons: (id, y1, y2, label, bg_rgb)
        self.buttons = [
            ("plant_moonlily", 52, 86, "[1] Plant Moonlily", (30, 74, 96)),
            ("plant_starbloom", 92, 126, "[2] Plant Starbloom", (76, 44, 98)),
            ("plant_lantern", 132, 166, "[3] Place Lantern", (94, 62, 30)),
            ("emote_chime", 172, 206, "[E] Chime Pulse", (34, 80, 64)),
            ("emote_sparkle", 212, 246, "[H] Wave Sparkle", (58, 52, 102)),
            ("cycle_sky", 252, 286, "[K] Shift Sky", (40, 60, 98)),
            ("toggle_note", 292, 326, "[N] Type Custom Note", (82, 54, 38)),
            ("meet_partner", 332, 366, "[G] Meet Partner", (44, 78, 82)),
            ("preset_note", 372, 406, "[M] Leave Kind Note", (70, 46, 84)),
        ]

        # Build GTK3 window
        self.win = Gtk.Window(title=f"Twilight Garden-Island — {self.player_name}")
        self.win.set_default_size(WIN_W, WIN_H)
        self.win.set_size_request(WIN_W, WIN_H)
        self.win.set_resizable(False)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.win.connect("destroy", self._on_destroy)
        self.win.add_events(Gdk.EventMask.KEY_PRESS_MASK)
        self.win.connect("key-press-event", self._on_key_press)

        self.event_box = Gtk.EventBox()
        self.event_box.set_size_request(WIN_W, WIN_H)
        self.event_box.set_can_focus(True)
        self.event_box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.event_box.connect("button-press-event", self._on_button_press)

        self.gtk_image = Gtk.Image()
        self.gtk_image.set_size_request(WIN_W, WIN_H)
        self.event_box.add(self.gtk_image)
        self.win.add(self.event_box)

        # Render initial frame before showing
        self._render_frame()
        self.win.show_all()
        self.win.present()

        # Start LAN thread and UI frame timer
        threading.Thread(target=self._net_loop, daemon=True).start()
        GLib.timeout_add(66, self._on_ui_tick)  # ~15 FPS smooth animation & glide

    def _on_destroy(self, *_args):
        self.running = False
        with self.lock:
            if self.sock:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.sock = None
        Gtk.main_quit()

    def _send(self, payload: dict) -> None:
        raw = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        with self.lock:
            s = self.sock
        if s is not None:
            try:
                s.sendall(raw)
            except OSError:
                pass

    def _net_loop(self) -> None:
        host = os.environ.get("AAL_LAN_HOST", "localhost")
        port = int(os.environ.get("AAL_LAN_PORT", "18765"))
        print("Twilight Garden-Island client starting LAN link...", flush=True)

        while self.running:
            s = None
            try:
                s = socket.create_connection((host, port), timeout=3.0)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.settimeout(None)
                with self.lock:
                    self.sock = s
                    self.connected = True
                print("PHASE: LAN CONNECTED", flush=True)

                self._send(
                    {
                        "type": "hello",
                        "id": self.player_id,
                        "name": self.player_name,
                        "color": self.player_color,
                        "role": self.player_role,
                        "x": round(self.my_x, 1),
                        "y": round(self.my_y, 1),
                    }
                )

                buf = bytearray()
                while self.running:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    buf.extend(chunk)
                    while b"\n" in buf:
                        line, _, rest = buf.partition(b"\n")
                        buf = bytearray(rest)
                        text = line.decode("utf-8", errors="replace").strip()
                        if not text:
                            continue
                        try:
                            msg = json.loads(text)
                        except json.JSONDecodeError:
                            continue
                        if msg.get("type") == "state":
                            with self.lock:
                                self.state = msg
                                me = msg.get("players", {}).get(self.player_id)
                                if me and self.target_xy is None:
                                    self.my_x = float(me.get("x", self.my_x))
                                    self.my_y = float(me.get("y", self.my_y))
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
                if self.running:
                    time.sleep(0.8)

    # --- Actions ---

    def _step_by(self, dx: float, dy: float) -> None:
        with self.lock:
            self.target_xy = None
            self.my_x = max(24.0, min(WORLD_W - 24.0, self.my_x + dx))
            self.my_y = max(24.0, min(WORLD_H - 24.0, self.my_y + dy))
            nx, ny = self.my_x, self.my_y
        self._send({"type": "move", "x": round(nx, 1), "y": round(ny, 1)})

    def _trigger_button(self, btn_id: str) -> None:
        self.flash_btn_id = btn_id
        self.flash_until = time.monotonic() + 0.35

        if btn_id == "plant_moonlily":
            self._send({"type": "plant", "kind": "moonlily"})
        elif btn_id == "plant_starbloom":
            self._send({"type": "plant", "kind": "starbloom"})
        elif btn_id == "plant_lantern":
            self._send({"type": "plant", "kind": "lantern"})
        elif btn_id == "emote_chime":
            self._send({"type": "emote", "emote": "chime"})
        elif btn_id == "emote_sparkle":
            self._send({"type": "emote", "emote": "sparkle"})
        elif btn_id == "cycle_sky":
            with self.lock:
                cur = str(self.state.get("sky", "twilight")).lower()
            idx = (SKY_MODES.index(cur) + 1) % len(SKY_MODES) if cur in SKY_MODES else 1
            self._send({"type": "sky", "sky": SKY_MODES[idx]})
        elif btn_id == "toggle_note":
            if self.typing_note and self.note_buf.strip():
                self._send({"type": "note", "text": self.note_buf.strip()})
                self.note_buf = ""
                self.typing_note = False
            else:
                self.typing_note = not self.typing_note
        elif btn_id == "meet_partner":
            tx, ty = 320.0, 180.0
            with self.lock:
                for pid, p in self.state.get("players", {}).items():
                    if pid != self.player_id:
                        tx = max(36.0, min(WORLD_W - 36.0, float(p.get("x", 320.0)) - 34.0))
                        ty = max(36.0, min(WORLD_H - 36.0, float(p.get("y", 180.0))))
                        break
                self.target_xy = (tx, ty)
                self.click_ring = (tx, ty, time.monotonic() + 0.8)
        elif btn_id == "preset_note":
            note = PRESET_NOTES[self.preset_idx % len(PRESET_NOTES)]
            self.preset_idx += 1
            self._send({"type": "note", "text": note})

    def _on_button_press(self, _widget, event) -> bool:
        sx, sy = int(event.x), int(event.y)
        self.event_box.grab_focus()

        # Check world canvas click -> smooth glide to (wx, wy)
        if MAP_X <= sx < MAP_X + WORLD_W and MAP_Y <= sy < MAP_Y + WORLD_H:
            wx = max(24.0, min(WORLD_W - 24.0, float(sx - MAP_X)))
            wy = max(24.0, min(WORLD_H - 24.0, float(sy - MAP_Y)))
            with self.lock:
                self.target_xy = (wx, wy)
                self.click_ring = (wx, wy, time.monotonic() + 0.7)
            return True

        # Check right control panel buttons
        if PANEL_X <= sx <= PANEL_X + PANEL_W:
            for btn_id, y1, y2, _label, _bg in self.buttons:
                if y1 <= sy <= y2:
                    self._trigger_button(btn_id)
                    return True
        return True

    def _on_key_press(self, _widget, event) -> bool:
        keyname = Gdk.keyval_name(event.keyval) or ""
        kv = event.keyval

        if self.typing_note:
            if keyname in ("Return", "KP_Enter"):
                txt = self.note_buf.strip()
                if txt:
                    self._send({"type": "note", "text": txt})
                self.note_buf = ""
                self.typing_note = False
                return True
            if keyname == "Escape":
                self.note_buf = ""
                self.typing_note = False
                return True
            if keyname == "BackSpace":
                self.note_buf = self.note_buf[:-1]
                return True
            if 32 <= kv <= 126 and len(self.note_buf) < 92:
                self.note_buf += chr(kv)
                return True
            return True

        low = keyname.lower()
        if keyname in ("Up", "KP_Up") or low == "w":
            self._step_by(0.0, -16.0)
        elif keyname in ("Down", "KP_Down") or low == "s":
            self._step_by(0.0, 16.0)
        elif keyname in ("Left", "KP_Left") or low == "a":
            self._step_by(-16.0, 0.0)
        elif keyname in ("Right", "KP_Right") or low == "d":
            self._step_by(16.0, 0.0)
        elif low == "1":
            self._trigger_button("plant_moonlily")
        elif low == "2":
            self._trigger_button("plant_starbloom")
        elif low in ("3", "p"):
            self._trigger_button("plant_lantern")
        elif low in ("e", "space"):
            self._trigger_button("emote_chime")
        elif low == "h":
            self._trigger_button("emote_sparkle")
        elif low == "k":
            self._trigger_button("cycle_sky")
        elif low == "n":
            self._trigger_button("toggle_note")
        elif low == "g":
            self._trigger_button("meet_partner")
        elif low == "m":
            self._trigger_button("preset_note")
        return True

    def _on_ui_tick(self) -> bool:
        if not self.running:
            return False

        moved_pos = None
        with self.lock:
            if self.target_xy is not None:
                tx, ty = self.target_xy
                dx, dy = tx - self.my_x, ty - self.my_y
                dist = math.hypot(dx, dy)
                step = 20.0
                if dist <= step:
                    self.my_x, self.my_y = tx, ty
                    self.target_xy = None
                else:
                    self.my_x += (dx / dist) * step
                    self.my_y += (dy / dist) * step
                moved_pos = (round(self.my_x, 1), round(self.my_y, 1))

        if moved_pos is not None:
            self._send({"type": "move", "x": moved_pos[0], "y": moved_pos[1]})

        self._render_frame()
        return True

    # --- Rendering ---

    def _draw_world(self, t: float, st: dict) -> Image.Image:
        wimg = Image.new("RGB", (WORLD_W, WORLD_H), (14, 22, 46))
        d = ImageDraw.Draw(wimg)

        sky = str(st.get("sky", "twilight")).lower()
        if sky == "aurora":
            top_c, bot_c = (10, 30, 52), (20, 48, 72)
        elif sky == "meteor":
            top_c, bot_c = (9, 13, 34), (24, 26, 58)
        elif sky == "dawn":
            top_c, bot_c = (44, 30, 68), (112, 62, 82)
        else:
            top_c, bot_c = (14, 20, 46), (26, 38, 74)

        # Banded water/sky gradient
        bands = 18
        bh = WORLD_H // bands
        for i in range(bands):
            c = mix_rgb(top_c, bot_c, i / max(1, bands - 1))
            d.rectangle([0, i * bh, WORLD_W, (i + 1) * bh + 1], fill=c)

        # Shimmering stars & water sparkles
        for sx, sy, sr, phase in self.stars:
            tw = 0.55 + 0.45 * math.sin(t * 2.2 + phase)
            sc = mix_rgb((80, 100, 150), (245, 245, 255), tw)
            d.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=sc)

        # Sky-specific atmosphere
        if sky == "aurora":
            for r_idx, base_col in enumerate([(48, 210, 175), (90, 145, 240), (165, 95, 225)]):
                pts = []
                for x in range(0, WORLD_W + 32, 32):
                    y = 34 + r_idx * 16 + int(12 * math.sin(x * 0.018 + t * 1.4 + r_idx))
                    pts.append((x, y))
                d.line(pts, fill=base_col, width=5)
        elif sky == "meteor":
            for m in range(4):
                prog = ((t * 110 + m * 170) % (WORLD_W + 180)) - 90
                my = int((45 + m * 68 + prog * 0.25) % (WORLD_H - 40))
                d.line([(prog - 34, my - 12), (prog, my)], fill=(255, 232, 165), width=2)
                d.ellipse([prog - 2, my - 2, prog + 2, my + 2], fill=(255, 250, 220))

        # Lagoon ripples around island
        pulse = int(3 * math.sin(t * 1.8))
        d.ellipse([58 - pulse, 28 - pulse, 582 + pulse, 336 + pulse], outline=(58, 105, 148), width=2)
        d.ellipse([74, 40, 566, 324], fill=(26, 68, 96), outline=(82, 152, 182), width=2)

        # Garden-Island organic landmass
        d.ellipse([92, 52, 548, 310], fill=(196, 168, 114))  # warm shell shore
        d.ellipse([102, 60, 538, 300], fill=(38, 92, 74))    # outer moss meadow
        d.ellipse([132, 78, 508, 280], fill=(46, 112, 86))   # lush twilight glade
        d.ellipse([215, 118, 425, 244], fill=(54, 126, 94))  # central grove

        # Stepping-stone paths from Lantern Hearth (320, 180)
        paths = [
            [(320, 180), (265, 156), (210, 132), (168, 115)],  # to Memory Pool
            [(320, 180), (378, 156), (434, 134), (482, 118)],  # to Star Observatory
            [(320, 180), (320, 215), (320, 250), (320, 282)],  # to Echo Dock
        ]
        for chain in paths:
            for px, py in chain:
                d.ellipse([px - 7, py - 5, px + 7, py + 5], fill=(154, 148, 138))

        # Landmark 1: Memory Pool (155, 110)
        d.ellipse([118, 86, 192, 134], fill=(32, 112, 158), outline=(130, 220, 245), width=2)
        rp = 8 + int(6 * (0.5 + 0.5 * math.sin(t * 2.4)))
        d.ellipse([155 - rp, 110 - rp // 2, 155 + rp, 110 + rp // 2], outline=(185, 245, 255), width=1)
        d.text((120, 69), "Memory Pool", fill=(185, 232, 248), font=self.f_tiny)

        # Landmark 2: Lantern Hearth (320, 180)
        d.ellipse([288, 154, 352, 206], fill=(92, 88, 98), outline=(218, 188, 128), width=2)
        d.ellipse([308, 170, 332, 190], fill=(64, 52, 58))
        flicker = 7 + int(2 * math.sin(t * 6.0))
        d.ellipse([320 - flicker, 180 - flicker, 320 + flicker, 180 + flicker], fill=(255, 178, 72))
        d.ellipse([316, 176, 324, 184], fill=(255, 240, 185))
        d.text((282, 209), "Lantern Hearth", fill=(242, 220, 172), font=self.f_tiny)

        # Landmark 3: Star Observatory (490, 115)
        d.ellipse([456, 90, 524, 140], fill=(58, 66, 96), outline=(196, 178, 242), width=2)
        d.ellipse([472, 102, 508, 128], outline=(228, 212, 255), width=1)
        d.line([(490, 92), (490, 138)], fill=(185, 170, 235), width=1)
        d.line([(458, 115), (522, 115)], fill=(185, 170, 235), width=1)
        d.text((444, 72), "Star Observatory", fill=(216, 202, 252), font=self.f_tiny)

        # Landmark 4: Echo Dock (320, 292)
        d.rectangle([304, 274, 336, 326], fill=(128, 92, 60), outline=(176, 134, 92), width=1)
        for ry in range(278, 324, 8):
            d.line([(305, ry), (335, ry)], fill=(96, 66, 42), width=1)
        d.text((293, 328), "Echo Dock", fill=(214, 196, 168), font=self.f_tiny)

        # Planted luminous flowers & lanterns
        for fl in st.get("flowers", []):
            fx, fy = int(fl.get("x", 320)), int(fl.get("y", 180))
            kind = str(fl.get("kind", "moonlily")).lower()
            fcol = hex_rgb(fl.get("color", ""), (126, 249, 255))
            glow = mix_rgb((46, 112, 86), fcol, 0.45)
            d.ellipse([fx - 11, fy - 9, fx + 11, fy + 9], fill=glow)

            if "lantern" in kind:
                d.line([(fx, fy + 6), (fx, fy - 9), (fx + 5, fy - 9)], fill=(210, 180, 120), width=2)
                d.rectangle([fx + 2, fy - 7, fx + 9, fy + 2], fill=(255, 208, 92), outline=(255, 245, 200))
            elif "star" in kind:
                for ang_i in range(5):
                    ang = ang_i * (2 * math.pi / 5) - math.pi / 2
                    px = fx + int(8 * math.cos(ang))
                    py = fy + int(8 * math.sin(ang))
                    d.line([(fx, fy), (px, py)], fill=fcol, width=3)
                d.ellipse([fx - 3, fy - 3, fx + 3, fy + 3], fill=(255, 250, 210))
            else:
                for dx_p, dy_p in [(-5, 0), (5, 0), (0, -5), (0, 5)]:
                    d.ellipse([fx + dx_p - 4, fy + dy_p - 3, fx + dx_p + 4, fy + dy_p + 3], fill=fcol)
                d.ellipse([fx - 3, fy - 3, fx + 3, fy + 3], fill=(255, 252, 224))

        # Carved garden notes
        notes = st.get("notes", [])
        for idx_n, nt in enumerate(notes):
            nx, ny = int(nt.get("x", 320)), int(nt.get("y", 180))
            d.rectangle([nx - 7, ny - 9, nx + 7, ny + 7], fill=(242, 228, 188), outline=(138, 108, 68), width=1)
            d.line([(nx - 4, ny - 5), (nx + 4, ny - 5)], fill=(96, 74, 48), width=1)
            d.line([(nx - 4, ny - 1), (nx + 4, ny - 1)], fill=(96, 74, 48), width=1)
            d.line([(nx - 4, ny + 3), (nx + 2, ny + 3)], fill=(96, 74, 48), width=1)
            if idx_n >= len(notes) - 3:
                snippet = str(nt.get("text", ""))[:20]
                if len(str(nt.get("text", ""))) > 20:
                    snippet += "..."
                d.text((nx + 10, ny - 8), snippet, fill=(248, 238, 200), font=self.f_tiny)

        # Click destination ring
        if self.click_ring is not None:
            cx, cy, until = self.click_ring
            if time.monotonic() < until:
                rad = int(6 + (until - time.monotonic()) * 14)
                d.ellipse([int(cx) - rad, int(cy) - rad, int(cx) + rad, int(cy) + rad], outline=(255, 222, 130), width=2)

        # Assemble players (include optimistic local pos so window feels instant)
        players_map = dict(st.get("players", {}))
        me_srv = dict(players_map.get(self.player_id, {}))
        me_srv.update(
            {
                "id": self.player_id,
                "name": me_srv.get("name") or self.player_name,
                "color": me_srv.get("color") or self.player_color,
                "x": self.my_x,
                "y": self.my_y,
            }
        )
        players_map[self.player_id] = me_srv

        # Harmony constellation arc when keepers stand near each other
        plist = list(players_map.values())
        if len(plist) >= 2:
            p_a, p_b = plist[0], plist[1]
            ax, ay = int(p_a["x"]), int(p_a["y"])
            bx, by = int(p_b["x"]), int(p_b["y"])
            if math.hypot(ax - bx, ay - by) <= 125.0 or st.get("harmony"):
                mx, my = (ax + bx) // 2, min(ay, by) - 24
                pts = [(ax, ay - 10), (mx, my), (bx, by - 10)]
                d.line(pts, fill=(255, 230, 150), width=2)
                for step_i in range(1, 5):
                    u = step_i / 5.0
                    sx_p = int((1 - u) * ax + u * bx)
                    sy_p = int((1 - u) * (ay - 10) + u * (by - 10) - 12 * math.sin(u * math.pi))
                    d.ellipse([sx_p - 2, sy_p - 2, sx_p + 2, sy_p + 2], fill=(140, 252, 238))

        # Draw each chosen character distinctly
        for pid, p in sorted(players_map.items()):
            px, py = int(p.get("x", 320)), int(p.get("y", 180))
            pname = str(p.get("name", pid))
            is_luma = ("luma" in pname.lower()) or ("2" in str(pid))
            pcol = hex_rgb(p.get("color", ""), (62, 230, 208) if is_luma else (255, 179, 71))

            # Soft lantern ground light
            halo_r = 22 + int(2 * math.sin(t * 3.5 + (1.5 if is_luma else 0.0)))
            halo_col = mix_rgb((46, 112, 86), pcol, 0.38)
            d.ellipse([px - halo_r, py - halo_r // 2, px + halo_r, py + halo_r // 2], fill=halo_col)

            # Active emote chime rings
            emote = str(p.get("emote", "")).strip()
            if emote:
                er = 18 + int((t * 28) % 22)
                d.ellipse([px - er, py - 8 - er, px + er, py - 8 + er], outline=pcol, width=2)
                d.text((px - 22, py - 48), f"* {emote} *", fill=(255, 250, 210), font=self.f_small)

            # Cloak silhouette
            cloak_fill = (24, 92, 96) if is_luma else (78, 46, 28)
            d.polygon([(px, py - 18), (px - 12, py + 11), (px + 12, py + 11)], fill=cloak_fill, outline=pcol)
            # Hood / head
            d.ellipse([px - 7, py - 24, px + 7, py - 10], fill=(244, 234, 216), outline=pcol, width=2)

            # Distinct signature detail: constellation dots for Solen, crescent crown for Luma
            if is_luma:
                d.arc([px - 9, py - 30, px + 9, py - 16], start=200, end=340, fill=(145, 255, 242), width=2)
            else:
                d.line([(px - 6, py + 5), (px, py - 3), (px + 5, py + 6)], fill=(255, 216, 130), width=1)

            # Raised glowing lantern in hand
            lx = px + (14 if not is_luma else -14)
            ly = py - 14 + int(2 * math.sin(t * 4.0))
            d.line([(px + (6 if not is_luma else -6), py - 8), (lx, ly - 5)], fill=(220, 200, 160), width=2)
            d.ellipse([lx - 7, ly - 7, lx + 7, ly + 7], fill=pcol, outline=(255, 252, 232), width=1)
            d.ellipse([lx - 3, ly - 3, lx + 3, ly + 3], fill=(255, 255, 245))

            # Speech bubble if recently left a note
            speech = str(p.get("speech", "")).strip()
            if speech:
                short_sp = speech[:30] + ("..." if len(speech) > 30 else "")
                bw = max(64, min(210, len(short_sp) * 6 + 14))
                bx1 = max(6, min(WORLD_W - bw - 6, px - bw // 2))
                by1 = max(6, py - 64)
                d.rectangle([bx1, by1, bx1 + bw, by1 + 18], fill=(22, 30, 52), outline=pcol, width=1)
                d.text((bx1 + 6, by1 + 3), short_sp, fill=(248, 246, 236), font=self.f_tiny)

            # Crisp nameplate pill
            nw = max(48, len(pname) * 7 + 14)
            nx1 = px - nw // 2
            ny1 = py + 14
            d.rectangle([nx1, ny1, nx1 + nw, ny1 + 16], fill=(16, 22, 38), outline=pcol, width=1)
            d.text((nx1 + 6, ny1 + 2), pname, fill=pcol, font=self.f_tiny)

        # Subtle border around world viewport
        d.rectangle([0, 0, WORLD_W - 1, WORLD_H - 1], outline=(76, 102, 142), width=2)
        return wimg

    def _render_frame(self) -> None:
        now = time.monotonic()
        t = now - self.start_time

        with self.lock:
            connected = self.connected
            st = dict(self.state)

        frame = Image.new("RGB", (WIN_W, WIN_H), (14, 18, 32))
        d = ImageDraw.Draw(frame)

        # 1. Top HUD Bar (0..44)
        d.rectangle([0, 0, WIN_W, 43], fill=(18, 24, 44))
        d.line([(0, 44), (WIN_W, 44)], fill=(70, 92, 134), width=1)

        d.text((12, 13), "TWILIGHT GARDEN-ISLAND", fill=(255, 214, 132), font=self.f_title)

        # LAN Connected Badge (NEVER displays any IP/network identifier)
        if connected:
            d.rectangle([226, 9, 366, 35], fill=(20, 92, 60), outline=(58, 224, 140), width=2)
            d.ellipse([236, 18, 244, 26], fill=(90, 255, 168))
            d.text((250, 14), "LAN Connected", fill=(228, 255, 240), font=self.f_badge)
        else:
            d.rectangle([226, 9, 366, 35], fill=(84, 58, 22), outline=(235, 175, 72), width=2)
            d.text((238, 14), "LAN Linking...", fill=(255, 228, 178), font=self.f_badge)

        players = st.get("players", {})
        keeper_names = ", ".join(p.get("name", k) for k, p in sorted(players.items())) or self.player_name
        sky_label = str(st.get("sky", "twilight")).capitalize()
        n_flowers = len(st.get("flowers", []))
        n_notes = len(st.get("notes", []))
        hud_mid = f"Keepers: {keeper_names[:22]}  |  Sky: {sky_label}  |  Blooms: {n_flowers}  Notes: {n_notes}"
        d.text((378, 15), hud_mid, fill=(214, 228, 248), font=self.f_hud)

        if st.get("harmony"):
            d.rectangle([768, 9, 844, 35], fill=(64, 52, 98), outline=(255, 220, 130), width=1)
            d.text((775, 15), "HARMONY", fill=(255, 234, 162), font=self.f_tiny)

        # 2. Paste 640x360 World Canvas
        wimg = self._draw_world(t, st)
        frame.paste(wimg, (MAP_X, MAP_Y))

        # 3. Right Interactive Control Panel
        for btn_id, y1, y2, label, bg in self.buttons:
            is_active = (btn_id == "toggle_note" and self.typing_note) or (
                btn_id == self.flash_btn_id and now < self.flash_until
            )
            fill_c = mix_rgb(bg, (255, 225, 150), 0.38) if is_active else bg
            border_c = (255, 230, 150) if is_active else mix_rgb(bg, (210, 225, 250), 0.42)
            d.rectangle([PANEL_X, y1, PANEL_X + PANEL_W, y2], fill=fill_c, outline=border_c, width=2)
            d.text((PANEL_X + 10, y1 + 9), label, fill=(244, 246, 252), font=self.f_btn)

        # 4. Bottom Chronicle & Note Composer Bar (416..474)
        d.rectangle([10, 416, 844, 472], fill=(20, 27, 48), outline=(68, 88, 128), width=1)
        if self.typing_note:
            d.rectangle([12, 418, 842, 470], fill=(48, 38, 24), outline=(255, 204, 102), width=2)
            cursor = "_" if int(t * 3) % 2 == 0 else " "
            d.text(
                (22, 425),
                f"Carve Garden Note: {self.note_buf}{cursor}",
                fill=(255, 238, 192),
                font=self.f_btn,
            )
            d.text(
                (22, 448),
                "Press Enter (or click [N] again) to place note on the island  |  Esc to cancel",
                fill=(214, 196, 156),
                font=self.f_small,
            )
        else:
            notes = st.get("notes", [])
            if notes:
                last_n = notes[-1]
                note_line = f"Latest Note ({last_n.get('by', 'Keeper')}): \"{last_n.get('text', '')}\""
            else:
                note_line = "No garden notes carved yet — click [N] or [M] to leave a thought on Lantern Isle."
            d.text((20, 423), note_line[:108], fill=(248, 232, 184), font=self.f_hud)

            events = st.get("events", [])
            ev_tail = events[-1] if events else "Ready"
            sub_line = f"World Log: {ev_tail[:52]}   |   Click map to walk  •  WASD/Arrows  •   You: {self.player_name}"
            d.text((20, 447), sub_line[:116], fill=(168, 192, 224), font=self.f_small)

        raw_bytes = frame.tobytes()
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(raw_bytes),
            GdkPixbuf.Colorspace.RGB,
            False,
            8,
            WIN_W,
            WIN_H,
            WIN_W * 3,
        )
        self.gtk_image.set_from_pixbuf(pixbuf)


def main() -> None:
    parser = argparse.ArgumentParser(description="Twilight Garden-Island GTK3 Client")
    parser.add_argument("--id", default=os.environ.get("AAL_PLAYER_ID", "p1"))
    parser.add_argument("--name", default=os.environ.get("AAL_PLAYER_NAME", ""))
    parser.add_argument("--color", default=os.environ.get("AAL_PLAYER_COLOR", ""))
    parser.add_argument("--role", default=os.environ.get("AAL_PLAYER_ROLE", ""))
    args = parser.parse_args()

    is_p2 = "2" in str(args.id)
    name = args.name or ("Luma" if is_p2 else "Solen")
    color = args.color or ("#3ee6d0" if is_p2 else "#ffb347")
    role = args.role or ("Teal Lantern-Spirit" if is_p2 else "Amber Star-Lantern")

    GardenClientApp(args.id, name, color, role)
    Gtk.main()


if __name__ == "__main__":
    main()
