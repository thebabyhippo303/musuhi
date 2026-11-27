#!/usr/bin/env python3
"""Tidal Atlas - 854x480 GTK3 client (PIL rendered into a Gtk.Image).

Keys: arrows/WASD move, P plant, L light, N bury a note, T chat,
Enter sends typed text, Escape cancels. Click a tile to walk there,
or click the buttons along the bottom.
"""
import json
import math
import os
import socket
import sys
import threading
import time
from collections import deque

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from PIL import Image, ImageDraw, ImageFont

WIN_W, WIN_H = 854, 480
TILE = 32
OX, OY = 43, 44
COLORS = {"teal": (64, 224, 208), "amber": (255, 176, 32), "white": (235, 235, 235),
          "rose": (255, 120, 150), "violet": (170, 130, 255)}


def player_color(p):
    """Accept a known color name, a #rrggbb value, or fall back on the name."""
    c = str(p.get("color", "")).lower()
    if c in COLORS:
        return COLORS[c]
    if len(c) == 7 and c[0] == "#":
        try:
            return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            pass
    return COLORS.get(str(p.get("name", "")).lower(), COLORS["white"])


BUTTONS = [("Plant [P]", "plant"), ("Light [L]", "light"),
           ("Note [N]", "note"), ("Say [T]", "say")]
BTN_Y, BTN_W, BTN_H = 438, 92, 30


def load_font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for base in ("/usr/share/fonts/truetype/dejavu/", ""):
        try:
            return ImageFont.truetype(base + name, size)
        except OSError:
            continue
    return ImageFont.load_default()


F_SM, F_MD, F_LG = load_font(11), load_font(13), load_font(17, True)
F_B = load_font(12, True)


def wrap(d, text, font, width):
    """Greedy word wrap by pixel width."""
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if cur and d.textlength(trial, font=font) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur] if cur else lines


class Net:
    """Background socket reader; keeps only the newest snapshot."""

    def __init__(self, name, color):
        self.name, self.color = name, color
        self.sock = None
        self.lock = threading.Lock()
        self.connected = False
        self.welcome = None
        self.state = None
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while True:
            try:
                host = os.environ["AAL_LAN_HOST"]
                port = int(os.environ.get("AAL_LAN_PORT", "18765"))
                s = socket.create_connection((host, port), timeout=5)
                s.settimeout(None)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.sock = s
                self.send({"t": "hello", "name": self.name, "color": self.color})
                f = s.makefile("r", encoding="utf-8")
                for line in f:
                    msg = json.loads(line)
                    if msg.get("t") == "welcome":
                        self.welcome = msg
                        self.connected = True
                    elif msg.get("t") == "state":
                        self.state = msg
            except Exception:
                pass
            self.connected = False
            self.sock = None
            time.sleep(1.0)

    def send(self, obj):
        with self.lock:
            try:
                if self.sock:
                    self.sock.sendall((json.dumps(obj) + "\n").encode())
            except Exception:
                pass


class Game:
    def __init__(self, name, color):
        self.net = Net(name, color)
        self.typing = None          # None, "note" or "say"
        self.buf = ""
        self.path = deque()
        self.last_step_tick = -1
        self.t0 = time.time()

        self.win = Gtk.Window(title="Tidal Atlas")
        self.win.set_default_size(WIN_W, WIN_H)
        self.win.set_resizable(False)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.win.connect("destroy", Gtk.main_quit)
        self.image = Gtk.Image()
        box = Gtk.EventBox()
        box.add(self.image)
        box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        box.connect("button-press-event", self.on_click)
        self.win.add(box)
        self.win.connect("key-press-event", self.on_key)
        self.win.show_all()
        GLib.timeout_add(100, self.frame)
        self.frame()

    # ---- helpers -----------------------------------------------------
    def me(self):
        st, wel = self.net.state, self.net.welcome
        if not st or not wel:
            return None
        return next((p for p in st["players"] if p["id"] == wel["id"]), None)

    def elev(self, x, y):
        return int(self.net.welcome["elev"][y][x])

    def lights(self):
        return {(l["x"], l["y"]) for l in self.net.state["lights"]}

    def can_enter(self, x, y, wading):
        wel, st = self.net.welcome, self.net.state
        if not (0 <= x < wel["w"] and 0 <= y < wel["h"]):
            return False
        e = self.elev(x, y)
        if e == 0 or (x, y) in self.lights():
            return False
        return wading or e >= st["tide"]

    def route(self, tx, ty):
        me = self.me()
        if not me:
            return
        start = (me["x"], me["y"])
        wading = self.elev(*start) < self.net.state["tide"]
        prev, todo = {start: None}, deque([start])
        while todo:
            cur = todo.popleft()
            if cur == (tx, ty):
                break
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    nxt = (cur[0] + dx, cur[1] + dy)
                    if (dx or dy) and nxt not in prev and self.can_enter(nxt[0], nxt[1], wading):
                        prev[nxt] = cur
                        todo.append(nxt)
        self.path.clear()
        if (tx, ty) in prev:
            cur = (tx, ty)
            while prev[cur] is not None:
                self.path.appendleft(cur)
                cur = prev[cur]

    def act(self, what):
        if what in ("plant", "light"):
            self.net.send({"t": what})
        elif what in ("note", "say"):
            self.typing, self.buf = what, ""

    # ---- input -------------------------------------------------------
    def on_key(self, _w, ev):
        name = Gdk.keyval_name(ev.keyval) or ""
        if self.typing:
            if name in ("Return", "KP_Enter"):
                if self.buf.strip():
                    self.net.send({"t": self.typing, "text": self.buf.strip()})
                self.typing = None
            elif name == "Escape":
                self.typing = None
            elif name == "BackSpace":
                self.buf = self.buf[:-1]
            else:
                ch = Gdk.keyval_to_unicode(ev.keyval)
                if ch >= 32 and len(self.buf) < 80:
                    self.buf += chr(ch)
            return True
        moves = {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1),
                 "a": (-1, 0), "d": (1, 0), "w": (0, -1), "s": (0, 1)}
        if name in moves:
            self.path.clear()
            self.net.send({"t": "move", "dx": moves[name][0], "dy": moves[name][1]})
        elif name in ("p", "space"):
            self.act("plant")
        elif name == "l":
            self.act("light")
        elif name == "n":
            self.act("note")
        elif name in ("t", "Return"):
            self.act("say")
        return True

    def on_click(self, _w, ev):
        x, y = int(ev.x), int(ev.y)
        for i, (_label, what) in enumerate(BUTTONS):
            bx = OX + i * (BTN_W + 8)
            if bx <= x < bx + BTN_W and BTN_Y <= y < BTN_Y + BTN_H:
                self.act(what)
                return True
        if self.net.welcome and self.net.state:
            tx, ty = (x - OX) // TILE, (y - OY) // TILE
            if 0 <= tx < self.net.welcome["w"] and 0 <= ty < self.net.welcome["h"]:
                self.route(tx, ty)
        return True

    def walk_path(self):
        st, me = self.net.state, self.me()
        if not self.path or not me or st["tick"] == self.last_step_tick:
            return
        self.last_step_tick = st["tick"]
        nx, ny = self.path[0]
        if (me["x"], me["y"]) == (nx, ny):
            self.path.popleft()
            if not self.path:
                return
            nx, ny = self.path[0]
        dx, dy = nx - me["x"], ny - me["y"]
        if max(abs(dx), abs(dy)) != 1:
            self.path.clear()
            return
        self.net.send({"t": "move", "dx": dx, "dy": dy})

    # ---- drawing -----------------------------------------------------
    def frame(self):
        self.walk_path()
        img = self.draw()
        data = GLib.Bytes.new(img.tobytes())
        pb = GdkPixbuf.Pixbuf.new_from_bytes(
            data, GdkPixbuf.Colorspace.RGB, False, 8, WIN_W, WIN_H, WIN_W * 3)
        self.image.set_from_pixbuf(pb)
        return True

    def draw(self):
        img = Image.new("RGB", (WIN_W, WIN_H), (8, 12, 28))
        d = ImageDraw.Draw(img)
        now = time.time() - self.t0
        d.text((OX, 12), "Tidal Atlas", font=F_LG, fill=(210, 225, 255))
        wel, st = self.net.welcome, self.net.state
        ok = self.net.connected and st is not None
        badge = "LAN Connected" if ok else "Searching LAN..."
        bcol = (40, 150, 90) if ok else (150, 90, 40)
        d.rounded_rectangle((694, 10, 811, 32), 10, fill=bcol)
        d.ellipse((702, 17, 710, 25), fill=(190, 255, 210) if ok else (255, 220, 170))
        d.text((715, 14), badge, font=F_B, fill=(255, 255, 255))
        if not ok:
            d.text((300, 220), "Waiting for the island to answer...", font=F_MD,
                   fill=(160, 180, 220))
            return img

        tide = st["tide"]
        chart = st.get("chart")
        lit = {(l["x"], l["y"]): l["lit"] for l in st["lights"]}
        land = {1: (150, 135, 95), 2: (86, 120, 78), 3: (52, 92, 62)}
        for y in range(wel["h"]):
            for x in range(wel["w"]):
                e = self.elev(x, y)
                px, py = OX + x * TILE, OY + y * TILE
                if e == 0:
                    s = 0.5 + 0.5 * math.sin(now * 1.5 + x * 0.8 + y * 1.1)
                    col = (12, 28 + int(8 * s), 62 + int(14 * s))
                else:
                    col = land[e]
                    if e < tide:
                        depth = min(1.0, 0.45 + 0.4 * (tide - e))
                        col = tuple(int(c * (1 - depth) + w * depth)
                                    for c, w in zip(col, (26, 62, 110)))
                    if chart and chart[y][x] == "0":
                        col = tuple(int(c * 0.45) for c in col)
                d.rectangle((px, py, px + TILE - 1, py + TILE - 1), fill=col)
                if e and e < tide:
                    wy = py + 14 + int(3 * math.sin(now * 2 + x))
                    d.line((px + 6, wy, px + 14, wy - 2, px + 24, wy), fill=(120, 170, 215))

        for n in st["notes"]:
            px, py = OX + n["x"] * TILE, OY + n["y"] * TILE
            d.rectangle((px + 9, py + 8, px + 23, py + 24), fill=(240, 228, 190),
                        outline=(120, 100, 60))
            d.line((px + 12, py + 13, px + 20, py + 13), fill=(120, 100, 60))
            d.line((px + 12, py + 18, px + 20, py + 18), fill=(120, 100, 60))

        pcol = {p["id"]: player_color(p) for p in st["players"]}
        for g in st["gardens"]:
            cx, cy = OX + g["x"] * TILE + 16, OY + g["y"] * TILE + 16
            col = pcol.get(g["owner"], (170, 190, 200))   # keeper has since rejoined
            stage = g["stage"]
            d.line((cx, cy + 10, cx, cy + 10 - 4 - 3 * stage), fill=(120, 200, 120), width=2)
            if stage >= 1:
                r = 2 + 2 * stage
                if stage == 3:
                    pulse = 2 + int(2 * math.sin(now * 3 + cx))
                    d.ellipse((cx - r - pulse, cy - 4 - r - pulse, cx + r + pulse,
                               cy - 4 + r + pulse), outline=col)
                d.ellipse((cx - r, cy - 4 - r, cx + r, cy - 4 + r), fill=col)
                d.ellipse((cx - 2, cy - 6, cx + 2, cy - 2), fill=(255, 255, 230))

        for (lx, ly), on in lit.items():
            cx, cy = OX + lx * TILE + 16, OY + ly * TILE + 16
            if on:
                for r, a in ((30, 60), (22, 95), (15, 140)):
                    rr = r + int(2 * math.sin(now * 4))
                    d.ellipse((cx - rr, cy - 10 - rr, cx + rr, cy - 10 + rr),
                              outline=(a + 100, a + 90, 60))
            d.polygon((cx - 8, cy + 14, cx + 8, cy + 14, cx + 5, cy - 8, cx - 5, cy - 8),
                      fill=(235, 235, 235))
            d.rectangle((cx - 6, cy, cx + 6, cy + 5), fill=(200, 60, 60))
            d.rectangle((cx - 6, cy - 15, cx + 6, cy - 8),
                        fill=(255, 235, 120) if on else (70, 70, 80), outline=(40, 40, 50))

        if self.path:
            tx, ty = self.path[-1]
            px, py = OX + tx * TILE, OY + ty * TILE
            d.rectangle((px + 2, py + 2, px + TILE - 3, py + TILE - 3), outline=(255, 255, 255))

        my_id = wel["id"]
        for p in st["players"]:
            cx, cy = OX + p["x"] * TILE + 16, OY + p["y"] * TILE + 16
            col = player_color(p)
            halo = 13 + int(2 * math.sin(now * 3 + p["id"]))
            d.ellipse((cx - halo, cy - halo, cx + halo, cy + halo),
                      outline=tuple(c // 2 for c in col))
            d.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=col,
                      outline=(255, 255, 255) if p["id"] == my_id else (20, 20, 30))
            d.ellipse((cx - 3, cy - 4, cx + 3, cy + 2), fill=(255, 255, 240))
            tw = d.textlength(p["name"], font=F_SM)
            d.text((cx - tw / 2, cy - 25), p["name"], font=F_SM, fill=(255, 255, 255))

        # HUD
        d.text((190, 8), "Tide", font=F_SM, fill=(150, 175, 220))
        d.rectangle((190, 24, 330, 32), outline=(90, 110, 160))
        frac = max(0.0, min(1.0, (tide - 0.5) / 2.0))
        d.rectangle((191, 25, 191 + int(138 * frac), 31), fill=(70, 140, 220))
        d.text((350, 8), "Charted", font=F_SM, fill=(150, 175, 220))
        d.text((350, 20), "%d%%" % st["charted"], font=F_B, fill=(230, 240, 255))
        d.text((420, 8), "Hum", font=F_SM, fill=(150, 175, 220))
        hum = st.get("hum", 0)
        for i in range(3):
            fill = (255, 210, 110) if i < hum else (50, 55, 75)
            d.ellipse((420 + i * 16, 22, 430 + i * 16, 32), fill=fill)
        hint = ["", "something is buried out there", "getting warmer", "right beside you"][hum]
        d.text((476, 20), hint, font=F_SM, fill=(255, 210, 110))

        me = self.me()
        here = None
        if me:
            here = next((n for n in st["notes"] if (n["x"], n["y"]) == (me["x"], me["y"])), None)
        for i, (label, _what) in enumerate(BUTTONS):
            bx = OX + i * (BTN_W + 8)
            d.rounded_rectangle((bx, BTN_Y, bx + BTN_W, BTN_Y + BTN_H), 6,
                                fill=(34, 48, 86), outline=(110, 135, 200))
            tw = d.textlength(label, font=F_B)
            d.text((bx + (BTN_W - tw) / 2, BTN_Y + 8), label, font=F_B, fill=(225, 235, 255))
        tx = OX + 4 * (BTN_W + 8) + 6
        if self.typing:
            label = "Note to bury: " if self.typing == "note" else "Say: "
            cursor = "_" if int(now * 2) % 2 else " "
            d.rectangle((tx, BTN_Y, 811, BTN_Y + BTN_H), fill=(20, 26, 50),
                        outline=(255, 210, 110))
            d.text((tx + 6, BTN_Y + 8), (label + self.buf)[-58:] + cursor, font=F_MD,
                   fill=(255, 240, 200))
        elif here:
            d.text((tx, BTN_Y - 8), "Note from %s:" % here["by"], font=F_SM,
                   fill=(255, 210, 110))
            for i, line in enumerate(wrap(d, here["text"], F_SM, 811 - tx)[:2]):
                d.text((tx, BTN_Y + 6 + i * 14), line, font=F_SM, fill=(255, 245, 215))
        else:
            lines = []
            for entry in st["log"][-3:]:
                lines += wrap(d, entry, F_SM, 811 - tx)
            for i, line in enumerate(lines[-3:]):
                d.text((tx, BTN_Y - 8 + i * 14), line, font=F_SM, fill=(175, 195, 235))
        return img


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "Teal"
    color = sys.argv[2] if len(sys.argv) > 2 else "teal"
    Game(name, color)
    Gtk.main()


if __name__ == "__main__":
    main()
