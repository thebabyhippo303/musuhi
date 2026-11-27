#!/usr/bin/env python3
"""Lantern Garden — Windows tkinter client (854x480). See PROTOCOL.md."""
import argparse
import ctypes
import json
import math
import os
import queue
import random
import socket
import sys
import threading
import time
import tkinter as tk

W, H = 854, 480
HUD_H = 44

CAST = {
    "p1": ("P1", "lantern", [60, 220, 200]),
    "p2": ("P2", "moth", [255, 190, 90]),
    "p3": ("P3", "prism", [255, 118, 128]),
    "p4": ("P4", "diamond", [190, 130, 255]),
}

QUICK_CHIMES = {
    "1": "come bloom my seed!",
    "2": "let us make a star bloom!",
    "3": "the garden glows brighter",
}


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def rgb_hex(rgb):
    r, g, b = (int(clamp(c, 0, 255)) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def blend_rgb(fg, bg, alpha):
    a = clamp(alpha, 0.0, 1.0)
    return [
        int(fg[0] * a + bg[0] * (1.0 - a)),
        int(fg[1] * a + bg[1] * (1.0 - a)),
        int(fg[2] * a + bg[2] * (1.0 - a)),
    ]


def blend_hex(fg, bg, alpha):
    return rgb_hex(blend_rgb(fg, bg, alpha))


def parse_color(val, fallback):
    if isinstance(val, (list, tuple)) and len(val) == 3:
        try:
            return [int(clamp(int(c), 0, 255)) for c in val]
        except (TypeError, ValueError):
            pass
    if isinstance(val, str) and val.startswith("#") and len(val) == 7:
        try:
            return [int(val[1:3], 16), int(val[3:5], 16), int(val[5:7], 16)]
        except ValueError:
            pass
    return list(fallback)


class LanClient:
    def __init__(self, name, shape, color):
        self.name = name[:12]
        self.shape = shape[:12]
        self.color = list(color)
        self.lock = threading.Lock()
        self.connected = False
        self.my_id = None
        self.state = {
            "tick": 0,
            "glow": 0,
            "players": [],
            "seeds": [],
            "blooms": [],
            "msgs": [],
        }
        self.outbox = queue.Queue(maxsize=64)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def send(self, obj):
        try:
            self.outbox.put_nowait(obj)
        except queue.Full:
            pass

    def snapshot(self):
        with self.lock:
            return self.connected, self.my_id, self.state

    def stop(self):
        self._stop.set()

    def _run(self):
        host = os.environ.get("AAL_LAN_HOST", "")
        port = int(os.environ.get("AAL_LAN_PORT", "18765"))
        if not host:
            print("Missing LAN host configuration", flush=True)
            return
        while not self._stop.is_set():
            sock = None
            try:
                sock = socket.create_connection((host, port), timeout=4.0)
                try:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError:
                    pass
                sock.settimeout(0.04)
                hello = {
                    "t": "hello",
                    "name": self.name,
                    "shape": self.shape,
                    "color": self.color,
                }
                sock.sendall((json.dumps(hello) + "\n").encode("utf-8"))
                buf = b""
                while not self._stop.is_set():
                    while True:
                        try:
                            pkt = self.outbox.get_nowait()
                        except queue.Empty:
                            break
                        sock.sendall((json.dumps(pkt) + "\n").encode("utf-8"))
                    try:
                        chunk = sock.recv(65536)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        raw, buf = buf.split(b"\n", 1)
                        if not raw.strip():
                            continue
                        try:
                            msg = json.loads(raw.decode("utf-8", "replace"))
                        except ValueError:
                            continue
                        kind = msg.get("t")
                        if kind == "welcome":
                            with self.lock:
                                self.my_id = msg.get("id")
                                self.connected = True
                            print("LAN Connected", flush=True)
                        elif kind == "state":
                            with self.lock:
                                self.state = msg
                                self.connected = True
            except OSError:
                pass
            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
                with self.lock:
                    self.connected = False
                    self.my_id = None
                while not self.outbox.empty():
                    try:
                        self.outbox.get_nowait()
                    except queue.Empty:
                        break
                self._stop.wait(1.0)


class LanternGardenApp:
    def __init__(self, root, net):
        self.root = root
        self.net = net
        self.t0 = time.monotonic()
        self.ripples = []  # (x, y, t_start, color_rgb)
        self.target_marker = None  # (x, y, t_start)

        rng = random.Random(42)
        self.stars = [
            (rng.randint(10, W - 10), rng.randint(HUD_H + 8, H - 14),
             rng.uniform(0.0, math.tau), rng.choice([1, 1, 2]))
            for _ in range(72)
        ]
        self.motes = [
            (rng.uniform(20, W - 20), rng.uniform(HUD_H + 20, H - 20),
             rng.uniform(0.4, 1.1), rng.uniform(0.0, math.tau))
            for _ in range(18)
        ]

        # Clickable HUD button rects: (x0, y0, x1, y1)
        self.plant_btn = (650, 8, 758, 36)
        self.chime_btn = (766, 8, 846, 36)
        self.chime_idx = 0
        self.typing = False

        self.canvas = tk.Canvas(
            root, width=W, height=H, bg="#0b1024",
            highlightthickness=0, bd=0,
        )
        self.canvas.pack(fill="both", expand=False)

        self.say_var = tk.StringVar()
        self.say_entry = tk.Entry(
            root, textvariable=self.say_var,
            bg="#101836", fg="#eef4ff", insertbackground="#fff8d6",
            relief="solid", bd=1, highlightthickness=1,
            highlightcolor="#8cb4ff", highlightbackground="#3a4f88",
            font=("Segoe UI", -12),
        )
        self.say_entry.bind("<Return>", self._submit_say)
        self.say_entry.bind("<Escape>", self._cancel_say)

        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<Button-3>", self.on_right_click)
        root.bind("<KeyPress>", self.on_key)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.canvas.focus_set()
        self._schedule_redraw()

    def _open_say(self, initial=""):
        self.typing = True
        self.say_var.set(initial)
        self.say_entry.place(x=360, y=H - 34, width=W - 372, height=26)
        self.say_entry.focus_set()
        self.say_entry.icursor(tk.END)

    def _submit_say(self, _event=None):
        text = self.say_var.get().strip()
        self._cancel_say()
        if text:
            self.net.send({"t": "say", "text": text[:60]})
        return "break"

    def _cancel_say(self, _event=None):
        self.typing = False
        self.say_var.set("")
        self.say_entry.place_forget()
        self.canvas.focus_set()
        return "break"

    def on_close(self):
        self.net.stop()
        self.root.destroy()

    def _in_rect(self, x, y, r):
        return r[0] <= x <= r[2] and r[1] <= y <= r[3]

    def _trigger_plant(self):
        self.net.send({"t": "plant"})
        _, my_id, st = self.net.snapshot()
        for p in st.get("players", []):
            if p.get("id") == my_id:
                self.ripples.append((p["x"], p["y"], time.monotonic(), self.net.color))
                break

    def _trigger_chime(self, key=None):
        if key in QUICK_CHIMES:
            text = QUICK_CHIMES[key]
        else:
            keys = ["1", "2", "3"]
            text = QUICK_CHIMES[keys[self.chime_idx % len(keys)]]
            self.chime_idx += 1
        self.net.send({"t": "say", "text": text})

    def on_left_click(self, event):
        x, y = event.x, event.y
        if self._in_rect(x, y, self.plant_btn):
            if self.typing:
                self._cancel_say()
            self._trigger_plant()
            return
        if self._in_rect(x, y, self.chime_btn):
            if self.typing:
                self._cancel_say()
            else:
                self._open_say()
            return
        if self.typing:
            self._cancel_say()
        if y < HUD_H:
            return
        cx = clamp(x, 12, 842)
        cy = clamp(y, 56, 468)
        self.net.send({"t": "move", "x": cx, "y": cy})
        now = time.monotonic()
        self.target_marker = (cx, cy, now)
        self.ripples.append((cx, cy, now, self.net.color))

    def on_right_click(self, event):
        if event.y >= HUD_H:
            self._trigger_plant()

    def on_key(self, event):
        if self.typing:
            return
        ks = (event.keysym or "").lower()
        step_map = {
            "left": (-1, 0), "a": (-1, 0),
            "right": (1, 0), "d": (1, 0),
            "up": (0, -1), "w": (0, -1),
            "down": (0, 1), "s": (0, 1),
        }
        if ks in step_map:
            dx, dy = step_map[ks]
            self.net.send({"t": "step", "dx": dx, "dy": dy})
        elif ks in ("space", "p", "e"):
            self._trigger_plant()
        elif ks == "return":
            self._open_say()
        elif ks in ("1", "2", "3"):
            self._trigger_chime(ks)

    def _sky_rgb(self, glow):
        # Deep midnight indigo brightening gracefully toward luminous twilight
        f = clamp(glow / 60.0, 0.0, 1.0)
        return [
            int(11 + 24 * f),
            int(16 + 34 * f),
            int(36 + 52 * f),
        ]

    def _draw_bloom(self, c, b, sky, t):
        x, y = float(b["x"]), float(b["y"])
        col = parse_color(b.get("color"), [200, 210, 240])
        level = int(b.get("level", 2))
        names = b.get("names", [])
        pulse = 1.0 + 0.06 * math.sin(t * 2.4 + b.get("id", 0))

        # Layered soft glow halo
        halo_r = (16 + level * 6) * pulse
        c.create_oval(
            x - halo_r, y - halo_r, x + halo_r, y + halo_r,
            fill=blend_hex(col, sky, 0.16), outline="",
        )
        mid_r = halo_r * 0.66
        c.create_oval(
            x - mid_r, y - mid_r, x + mid_r, y + mid_r,
            fill=blend_hex(col, sky, 0.32), outline="",
        )

        if level >= 4:
            # Special Star Bloom: 8-pointed radiant star + shimmer rays
            rot = t * 0.45 + b.get("id", 0)
            pts = []
            outer_r = 21 * pulse
            inner_r = 9 * pulse
            for i in range(16):
                ang = rot + i * (math.pi / 8.0)
                rad = outer_r if i % 2 == 0 else inner_r
                pts.extend((x + math.cos(ang) * rad, y + math.sin(ang) * rad))
            c.create_polygon(
                pts, fill=rgb_hex(col),
                outline=blend_hex([255, 250, 210], col, 0.75), width=2,
            )
            # Crisp inner star sparkle
            for i in range(4):
                ang = -rot * 1.3 + i * (math.pi / 2.0)
                c.create_line(
                    x - math.cos(ang) * 11, y - math.sin(ang) * 11,
                    x + math.cos(ang) * 11, y + math.sin(ang) * 11,
                    fill="#fffbe0", width=2,
                )
            c.create_oval(x - 5, y - 5, x + 5, y + 5, fill="#fffdf2", outline="")
        else:
            petals = 5 if level <= 2 else 7
            petal_dist = (8.5 if level <= 2 else 11.5) * pulse
            petal_r = (5.5 if level <= 2 else 6.8) * pulse
            rot = t * 0.2 + b.get("id", 0) * 0.7
            petal_fill = rgb_hex(col)
            petal_hi = blend_hex([255, 255, 255], col, 0.45)
            for i in range(petals):
                ang = rot + i * (math.tau / petals)
                px = x + math.cos(ang) * petal_dist
                py = y + math.sin(ang) * petal_dist
                c.create_oval(
                    px - petal_r, py - petal_r, px + petal_r, py + petal_r,
                    fill=petal_fill, outline=petal_hi, width=1,
                )
            core_r = 4.5 if level <= 2 else 5.5
            c.create_oval(
                x - core_r, y - core_r, x + core_r, y + core_r,
                fill="#fff6d6", outline="",
            )

        word = str(b.get("word", "")).strip()
        if word:
            wy = y + (27 if level >= 4 else 21)
            half_w = max(24, len(word) * 4 + 8)
            c.create_rectangle(
                x - half_w, wy - 8, x + half_w, wy + 8,
                fill=blend_hex([8, 12, 28], sky, 0.78),
                outline=blend_hex([255, 245, 200], col, 0.45),
                width=1,
            )
            c.create_text(
                x, wy, text=word,
                fill="#fff9db",
                font=("Segoe UI", -12, "bold"),
            )
            if names:
                tag = ("* " if level >= 4 else "") + "+".join(names)
                c.create_text(
                    x, wy + 14, text=tag,
                    fill=blend_hex([230, 238, 255], col, 0.55),
                    font=("Segoe UI", -9),
                )
        elif names:
            tag = ("* " if level >= 4 else "") + "+".join(names)
            c.create_text(
                x, y + (25 if level >= 4 else 19),
                text=tag,
                fill=blend_hex([255, 255, 255], col, 0.6),
                font=("Segoe UI", -10),
            )

    def _draw_seed(self, c, s, sky, my_id, t):
        x, y = float(s["x"]), float(s["y"])
        col = parse_color(s.get("color"), [180, 190, 210])
        is_mine = s.get("owner") == my_id
        pulse = 0.5 + 0.5 * math.sin(t * 3.5 + s.get("id", 0))
        r_glow = 9 + 3 * pulse
        c.create_oval(
            x - r_glow, y - r_glow, x + r_glow, y + r_glow,
            fill=blend_hex(col, sky, 0.22), outline="",
        )
        if not is_mine:
            # Subtle inviting ring around other players' seeds waiting to be woken
            r_ring = 11 + 2 * pulse
            c.create_oval(
                x - r_ring, y - r_ring, x + r_ring, y + r_ring,
                outline=blend_hex(col, sky, 0.55), width=1, dash=(3, 3),
            )
        c.create_oval(
            x - 4, y - 4, x + 4, y + 4,
            fill=blend_hex(col, sky, 0.85),
            outline="#ffffff" if not is_mine else "",
            width=1,
        )
        owner_name = s.get("name", "")
        if owner_name:
            c.create_text(
                x, y + 13, text=owner_name,
                fill=blend_hex(col, sky, 0.72),
                font=("Segoe UI", -9),
            )

    def _draw_avatar(self, c, p, sky, my_id, t):
        x, y = float(p["x"]), float(p["y"])
        col = parse_color(p.get("color"), [220, 220, 230])
        shape = str(p.get("shape", "circle")).lower()
        name = str(p.get("name", "?"))
        is_me = p.get("id") == my_id

        # Soft personal aura
        c.create_oval(
            x - 22, y - 22, x + 22, y + 22,
            fill=blend_hex(col, sky, 0.17), outline="",
        )
        if is_me:
            c.create_oval(
                x - 19, y - 19, x + 19, y + 19,
                outline=blend_hex([255, 255, 255], col, 0.55),
                width=1, dash=(4, 3),
            )

        fill_hex = rgb_hex(col)
        hi_hex = blend_hex([255, 255, 255], col, 0.55)

        if shape == "lantern":
            # Teal lantern: arched handle, rounded glow chamber, warm inner flame
            c.create_arc(
                x - 5, y - 16, x + 5, y - 6,
                start=0, extent=180, style=tk.ARC,
                outline=hi_hex, width=2,
            )
            c.create_rectangle(
                x - 6, y - 11, x + 6, y - 8,
                fill=blend_hex([40, 80, 80], col, 0.4), outline="",
            )
            c.create_oval(
                x - 9, y - 9, x + 9, y + 10,
                fill=fill_hex, outline=hi_hex, width=2,
            )
            c.create_oval(
                x - 4, y - 4, x + 4, y + 5,
                fill="#ecfff7", outline="",
            )
            c.create_rectangle(
                x - 5, y + 9, x + 5, y + 12,
                fill=blend_hex([40, 80, 80], col, 0.4), outline="",
            )
        elif shape == "moth":
            # Amber moth with two gently fluttering uneven wings
            flap = 2.6 * math.sin(t * 5.2)
            left_wing = [
                x - 1, y - 3,
                x - 16, y - 10 + flap,
                x - 13, y + 2 + flap * 0.4,
                x - 5, y + 8,
                x - 1, y + 3,
            ]
            right_wing = [
                x + 1, y - 3,
                x + 13, y - 8 + flap * 0.85,
                x + 11, y + 4 + flap * 0.3,
                x + 5, y + 7,
                x + 1, y + 3,
            ]
            c.create_polygon(left_wing, fill=fill_hex, outline=hi_hex, width=1)
            c.create_polygon(right_wing, fill=fill_hex, outline=hi_hex, width=1)
            c.create_line(x - 1, y - 4, x - 5, y - 11, fill="#fff2cc", width=1)
            c.create_line(x + 1, y - 4, x + 4, y - 10, fill="#fff2cc", width=1)
            c.create_line(x, y - 5, x, y + 7, fill="#fff5d6", width=3)
        elif shape == "prism":
            # Coral crystal prism with inner refraction facets
            tri = [x, y - 14, x - 13, y + 9, x + 12, y + 10]
            c.create_polygon(tri, fill=fill_hex, outline="#ffe6dc", width=2)
            # Inner specular facet lines
            c.create_line(x, y - 12, x + 1, y + 2, fill="#fff5e6", width=2)
            c.create_line(x + 1, y + 2, x - 11, y + 8, fill="#ffd9cc", width=1)
            c.create_line(x + 1, y + 2, x + 10, y + 9, fill="#ffe8cc", width=1)
            # Tiny refracted spark glints
            glint_a = t * 2.1
            gx = x + math.cos(glint_a) * 14
            gy = y - 2 + math.sin(glint_a) * 8
            c.create_oval(gx - 2, gy - 2, gx + 2, gy + 2, fill="#a8f5ff", outline="")
        elif shape in ("diamond", "kite"):
            # Violet diamond kite with gentle trailing ribbon
            sway = 2.5 * math.sin(t * 3.8)
            c.create_line(
                x, y + 10,
                x + 3 + sway * 0.6, y + 15,
                x - 1 + sway, y + 20,
                fill=hi_hex, width=2, smooth=True,
            )
            pts = [x, y - 14, x + 11, y - 1, x, y + 11, x - 11, y - 1]
            c.create_polygon(pts, fill=fill_hex, outline="#f3e3ff", width=2)
            c.create_line(x, y - 12, x, y + 9, fill="#f5e9ff", width=1)
            c.create_line(x - 9, y - 1, x + 9, y - 1, fill="#f5e9ff", width=1)
        else:
            c.create_oval(
                x - 10, y - 10, x + 10, y + 10,
                fill=fill_hex, outline=hi_hex, width=2,
            )

        label = f"{name} (you)" if is_me else name
        c.create_text(
            x, y + 23, text=label,
            fill="#ffffff" if is_me else "#dce6ff",
            font=("Segoe UI", -11, "bold" if is_me else "normal"),
        )

    def _draw_hud(self, c, connected, st, sky):
        hud_bg = blend_hex([14, 20, 44], sky, 0.85)
        c.create_rectangle(0, 0, W, HUD_H, fill=hud_bg, outline="")
        c.create_line(0, HUD_H - 1, W, HUD_H - 1, fill="#2e3f6e", width=1)

        # Title
        c.create_text(
            14, 22, anchor="w", text="Lantern Garden",
            fill="#eef4ff", font=("Segoe UI", -16, "bold"),
        )

        # LAN Connected badge
        if connected:
            badge_bg, dot_col, badge_txt = "#143d32", "#4ef2a8", "LAN Connected"
        else:
            badge_bg, dot_col, badge_txt = "#423018", "#ffbe55", "Connecting..."
        c.create_rectangle(148, 9, 274, 35, fill=badge_bg, outline=dot_col, width=1)
        c.create_oval(157, 18, 165, 26, fill=dot_col, outline="")
        c.create_text(
            172, 22, anchor="w", text=badge_txt,
            fill="#e9fff5" if connected else "#ffe9c2",
            font=("Segoe UI", -12, "bold"),
        )

        # Shared stats
        glow = st.get("glow", 0)
        n_blooms = len(st.get("blooms", []))
        n_seeds = len(st.get("seeds", []))
        n_players = len(st.get("players", []))
        stats = f"Glow {glow}   Blooms {n_blooms}   Seeds {n_seeds}   Players {n_players}"
        c.create_text(
            462, 22, anchor="center", text=stats,
            fill="#c9d9ff", font=("Segoe UI", -12),
        )

        # Plant button
        x0, y0, x1, y1 = self.plant_btn
        c.create_rectangle(x0, y0, x1, y1, fill="#293a66", outline="#ff9487", width=1)
        c.create_text(
            (x0 + x1) / 2, (y0 + y1) / 2,
            text="Plant (Space)", fill="#ffece8",
            font=("Segoe UI", -11, "bold"),
        )

        # Say / Name button
        x0, y0, x1, y1 = self.chime_btn
        c.create_rectangle(x0, y0, x1, y1, fill="#263459", outline="#8cb4ff", width=1)
        c.create_text(
            (x0 + x1) / 2, (y0 + y1) / 2,
            text="Say / Name", fill="#e3edff",
            font=("Segoe UI", -11, "bold"),
        )

    def _draw_messages(self, c, msgs, sky):
        if not msgs:
            return
        lines = msgs[-5:]
        box_h = 10 + 16 * len(lines)
        y0 = H - box_h - 8
        c.create_rectangle(
            10, y0, 345, H - 8,
            fill=blend_hex([8, 12, 28], sky, 0.78),
            outline=blend_hex([90, 115, 175], sky, 0.45),
            width=1,
        )
        for i, m in enumerate(lines):
            who = m.get("from", "*")
            txt = m.get("text", "")
            line = f"* {txt}" if who == "*" else f"{who}: {txt}"
            col = "#b8d7ff" if who == "*" else "#f2f6ff"
            c.create_text(
                18, y0 + 13 + i * 16, anchor="w",
                text=line[:48], fill=col, font=("Segoe UI", -11),
            )

    def draw(self):
        t = time.monotonic() - self.t0
        now = time.monotonic()
        connected, my_id, st = self.net.snapshot()
        glow = st.get("glow", 0)
        sky = self._sky_rgb(glow)
        c = self.canvas
        c.delete("all")

        # Sky backdrop
        c.create_rectangle(0, HUD_H, W, H, fill=rgb_hex(sky), outline="")

        # Subtle glowing horizon band
        c.create_rectangle(
            0, H - 38, W, H,
            fill=blend_hex([20, 40, 62], sky, 0.45), outline="",
        )

        # Twinkling stars
        for sx, sy, phase, sz in self.stars:
            tw = 0.28 + 0.55 * (0.5 + 0.5 * math.sin(t * 1.6 + phase))
            scol = blend_hex([225, 238, 255], sky, tw)
            c.create_oval(sx, sy, sx + sz, sy + sz, fill=scol, outline="")

        # Drifting garden firefly motes
        for mx, my, spd, ph in self.motes:
            fx = (mx + math.sin(t * 0.4 * spd + ph) * 24) % W
            fy = HUD_H + 14 + ((my - HUD_H + math.cos(t * 0.3 * spd + ph) * 16) % (H - HUD_H - 28))
            mcol = blend_hex([255, 235, 165], sky, 0.35 + 0.25 * math.sin(t * 2.5 + ph))
            c.create_oval(fx - 1.5, fy - 1.5, fx + 1.5, fy + 1.5, fill=mcol, outline="")

        # Click target marker & ripples
        if self.target_marker:
            tx, ty, ts = self.target_marker
            age = now - ts
            if age < 2.2:
                alpha = max(0.0, 1.0 - age / 2.2)
                c.create_oval(
                    tx - 5, ty - 5, tx + 5, ty + 5,
                    outline=blend_hex(self.net.color, sky, alpha * 0.8), width=1,
                )
            else:
                self.target_marker = None

        alive_ripples = []
        for rx, ry, ts, rcol in self.ripples:
            age = now - ts
            if age < 0.75:
                rad = 6 + age * 44
                alpha = (1.0 - age / 0.75) * 0.75
                c.create_oval(
                    rx - rad, ry - rad, rx + rad, ry + rad,
                    outline=blend_hex(rcol, sky, alpha), width=2,
                )
                alive_ripples.append((rx, ry, ts, rcol))
        self.ripples = alive_ripples

        # Blooms -> Seeds -> Players
        for b in st.get("blooms", []):
            self._draw_bloom(c, b, sky, t)
        for s in st.get("seeds", []):
            self._draw_seed(c, s, sky, my_id, t)
        for p in st.get("players", []):
            self._draw_avatar(c, p, sky, my_id, t)

        # Messages & bottom-right controls hint
        self._draw_messages(c, st.get("msgs", []), sky)
        if not self.typing:
            c.create_text(
                W - 12, H - 14, anchor="e",
                text="Click: walk | Space: plant | Enter: say / name <word>",
                fill=blend_hex([180, 200, 240], sky, 0.65),
                font=("Segoe UI", -10),
            )

        # HUD on top
        self._draw_hud(c, connected, st, sky)

    def _schedule_redraw(self):
        self.draw()
        self.root.after(33, self._schedule_redraw)


def enable_dpi_awareness():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lantern Garden tkinter client")
    parser.add_argument("--side", default="p3", choices=sorted(CAST.keys()))
    parser.add_argument("--name", default=None)
    parser.add_argument("--shape", default=None)
    parser.add_argument("--color", default=None, help="Hex #rrggbb or r,g,b")
    args = parser.parse_args(argv)

    default_name, default_shape, default_color = CAST[args.side]
    name = args.name or default_name
    shape = args.shape or default_shape
    if args.color:
        if "," in args.color:
            color = parse_color(args.color.split(","), default_color)
        else:
            color = parse_color(args.color, default_color)
    else:
        color = list(default_color)

    enable_dpi_awareness()
    root = tk.Tk()
    root.title(f"Lantern Garden — {name}")
    root.geometry(f"{W}x{H}")
    root.resizable(False, False)
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = max(0, (sw - W) // 2)
    y = max(0, (sh - H) // 2)
    root.geometry(f"{W}x{H}+{x}+{y}")

    net = LanClient(name, shape, color)
    LanternGardenApp(root, net)
    root.mainloop()


if __name__ == "__main__":
    main()
