#!/usr/bin/env python3
"""Lantern Garden — 854x480 GTK client (Laptop / host side). See PROTOCOL.md."""
import json
import math
import os
import socket
import sys
import threading
import time

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from PIL import Image, ImageChops, ImageDraw, ImageFont

WIN_W, WIN_H = 854, 480
TILE = 32
GRID_W, GRID_H = 26, 13
OX, OY = 11, 54
SAYINGS = {"1": "hello", "2": "nice lantern", "3": "follow me", "4": "thank you"}
ACT_BTN = (752, 9, 842, 39)
NAME = os.environ.get("AAL_PLAYER_NAME", "P1")


def load_font(size, bold=False):
    names = ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
             "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"]
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


F_TITLE = load_font(17, True)
F_HUD = load_font(13, True)
F_SMALL = load_font(11)


def make_light(radius):
    size = radius * 2
    img = Image.new("L", (size, size), 0)
    px = img.load()
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - radius, y - radius) / radius
            if d < 1:
                px[x, y] = int(255 * (1 - d) ** 1.4)
    return img


LIGHT = make_light(84)
SMALL_LIGHT = make_light(44)


class Net:
    """Background socket reader; main thread sends."""

    def __init__(self):
        self.lock = threading.Lock()
        self.state = None
        self.my_id = None
        self.connected = False
        self.sock = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        host = os.environ["AAL_LAN_HOST"]
        port = int(os.environ.get("AAL_LAN_PORT", "18765"))
        while True:
            try:
                sock = socket.create_connection((host, port), timeout=5)
                sock.settimeout(None)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.sock = sock
                self.send({"t": "join", "name": NAME})
                buf = b""
                while True:
                    data = sock.recv(65536)
                    if not data:
                        break
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        try:
                            msg = json.loads(line)
                        except ValueError:
                            continue
                        with self.lock:
                            if msg.get("t") == "welcome":
                                self.my_id = msg["id"]
                                self.connected = True
                            elif msg.get("t") == "state":
                                self.state = msg
            except OSError:
                pass
            with self.lock:
                self.connected = False
                self.sock = None
            time.sleep(1.0)

    def send(self, obj):
        sock = self.sock
        if sock is None:
            return
        try:
            sock.sendall((json.dumps(obj) + "\n").encode())
        except OSError:
            pass


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def tile_center(x, y):
    return OX + x * TILE + TILE // 2, OY + y * TILE + TILE // 2


def draw_plant(d, pl, frame):
    cx, cy = tile_center(pl["x"], pl["y"])
    col = tuple(pl.get("color", (255, 200, 80)))
    st = pl["stage"]
    if st == 0:
        d.ellipse((cx - 6, cy + 3, cx + 6, cy + 9), fill=(92, 62, 36))
        d.ellipse((cx - 2, cy + 3, cx + 2, cy + 7), fill=shade(col, 0.8))
    elif st == 1:
        d.line((cx, cy + 9, cx, cy - 2), fill=(70, 170, 70), width=3)
        d.ellipse((cx - 7, cy - 4, cx, cy + 1), fill=(90, 200, 90))
        d.ellipse((cx, cy - 6, cx + 7, cy - 1), fill=(90, 200, 90))
    elif st == 2:
        d.line((cx, cy + 10, cx, cy - 4), fill=(70, 170, 70), width=3)
        d.ellipse((cx - 8, cy + 1, cx, cy + 6), fill=(90, 200, 90))
        d.ellipse((cx - 5, cy - 11, cx + 5, cy - 1), fill=shade(col, 0.75))
    elif st == 3:
        d.line((cx, cy + 11, cx, cy), fill=(70, 170, 70), width=3)
        pulse = 1 + 0.15 * math.sin(frame * 0.5)
        r = 6 * pulse
        for k in range(5):
            a = k * 2 * math.pi / 5 + frame * 0.05
            px, py = cx + 7 * math.cos(a), cy - 4 + 7 * math.sin(a)
            d.ellipse((px - r, py - r, px + r, py + r), fill=col)
        d.ellipse((cx - 4, cy - 8, cx + 4, cy), fill=(255, 250, 200))
    else:
        d.line((cx, cy + 12, cx, cy + 2), fill=(90, 70, 50), width=3)
        d.rectangle((cx - 6, cy - 14, cx + 6, cy - 11), fill=(60, 50, 50))
        d.rounded_rectangle((cx - 9, cy - 11, cx + 9, cy + 5), radius=5,
                            fill=col, outline=shade(col, 0.55), width=2)
        flick = 3 + (frame // 2) % 2
        d.ellipse((cx - flick, cy - 7, cx + flick, cy + 1), fill=(255, 252, 215))
        ring = pl.get("ring", -1)
        if 0 <= ring < 10:
            rr = 12 + ring * 5
            d.ellipse((cx - rr, cy - 3 - rr, cx + rr, cy - 3 + rr),
                      outline=shade(col, 1.2), width=2)
            rr2 = rr - 9
            if rr2 > 4:
                d.ellipse((cx - rr2, cy - 3 - rr2, cx + rr2, cy - 3 + rr2),
                          outline=(255, 255, 230), width=1)


def draw_player(d, p, me):
    cx, cy = tile_center(p["x"], p["y"])
    col = tuple(p["color"])
    d.ellipse((cx - 11, cy + 8, cx + 11, cy + 14), fill=(30, 60, 40))
    d.rounded_rectangle((cx - 9, cy - 3, cx + 9, cy + 12), radius=6,
                        fill=col, outline=shade(col, 0.5), width=2)
    d.ellipse((cx - 8, cy - 15, cx + 8, cy + 1), fill=(250, 232, 205),
              outline=shade(col, 0.5), width=2)
    d.ellipse((cx - 4, cy - 9, cx - 2, cy - 6), fill=(40, 40, 50))
    d.ellipse((cx + 2, cy - 9, cx + 4, cy - 6), fill=(40, 40, 50))
    if me:
        d.ellipse((cx - 14, cy - 18, cx + 14, cy + 15), outline=(255, 255, 255), width=1)
    label = p["name"] + (" (you)" if me else "")
    tw = d.textlength(label, font=F_SMALL)
    d.rectangle((cx - tw / 2 - 3, cy - 31, cx + tw / 2 + 3, cy - 18), fill=(20, 26, 44))
    d.text((cx - tw / 2, cy - 31), label, font=F_SMALL, fill=(255, 255, 255))


def draw_plaque(d, q, occupied):
    cx, cy = tile_center(q["x"], q["y"])
    text = q["text"]
    tw = d.textlength(text, font=F_SMALL)
    x0 = max(OX + 2, min(WIN_W - OX - tw - 12, cx - tw / 2 - 5))
    # sit on an empty tile; hang under a planted one so the lantern stays visible
    y0 = cy + 15 if occupied else cy - 8
    d.rounded_rectangle((x0, y0, x0 + tw + 10, y0 + 15), radius=3,
                        fill=(214, 182, 128), outline=(110, 80, 50), width=2)
    d.text((x0 + 5, y0 + 1), text, font=F_SMALL, fill=(60, 40, 20))


def draw_wind(d, st, frame):
    wind = st.get("wind", -1)
    if not 0 <= wind < 30:
        return
    at = st.get("wind_at")
    for k in range(6):
        y = OY + 30 + k * 66 + (k % 2) * 14
        x = OX + ((wind * 40 + k * 150 + frame * 3) % (GRID_W * TILE - 70))
        d.arc((x, y, x + 60, y + 16), 200, 340, fill=(215, 235, 255), width=2)
    if at:
        cx, cy = tile_center(at[0], at[1])
        d.ellipse((cx - 17, cy - 19, cx + 17, cy + 15), outline=(215, 235, 255), width=2)
        d.text((cx - 28, cy + 15), "snuffed!", font=F_SMALL, fill=(225, 240, 255))


def draw_bubble(d, p):
    if not p.get("say"):
        return
    cx, cy = tile_center(p["x"], p["y"])
    text = p["say"]
    tw = d.textlength(text, font=F_HUD)
    x0 = max(4, min(WIN_W - tw - 20, cx - tw / 2 - 8))
    y0 = max(OY + 2, cy - 58)
    d.rounded_rectangle((x0, y0, x0 + tw + 16, y0 + 22), radius=8,
                        fill=(255, 255, 255), outline=(40, 40, 60), width=2)
    d.text((x0 + 8, y0 + 3), text, font=F_HUD, fill=(30, 30, 50))


def render(net, frame, typing=None):
    with net.lock:
        st = net.state
        my_id = net.my_id
        connected = net.connected
    img = Image.new("RGB", (WIN_W, WIN_H), (18, 24, 40))
    d = ImageDraw.Draw(img)
    # garden floor
    for y in range(GRID_H):
        for x in range(GRID_W):
            base = (64, 138, 78) if (x + y) % 2 == 0 else (58, 128, 72)
            if (x * 7 + y * 13) % 11 == 0:
                base = (70, 146, 84)
            x0, y0 = OX + x * TILE, OY + y * TILE
            d.rectangle((x0, y0, x0 + TILE - 1, y0 + TILE - 1), fill=base)
    d.rectangle((OX - 2, OY - 2, OX + GRID_W * TILE + 1, OY + GRID_H * TILE + 1),
                outline=(120, 96, 60), width=2)
    me = None
    night = 0.25
    if st:
        night = st.get("night", 0.25)
        for pl in st["plants"]:
            draw_plant(d, pl, frame)
        for p in sorted(st["players"], key=lambda q: q["y"]):
            draw_player(d, p, p["id"] == my_id)
            if p["id"] == my_id:
                me = p
        planted = {(pl["x"], pl["y"]) for pl in st["plants"]}
        for q in st.get("plaques", []):
            draw_plaque(d, q, (q["x"], q["y"]) in planted)
        # darkness, pushed back by lanterns and by players
        mask = Image.new("L", (WIN_W, WIN_H), int(20 + night * 170))
        for pl in st["plants"]:
            if pl["stage"] == 4:
                cx, cy = tile_center(pl["x"], pl["y"])
                box = (cx - 84, cy - 84 - 3)
                region = mask.crop((box[0], box[1], box[0] + 168, box[1] + 168))
                mask.paste(ImageChops.subtract(region, LIGHT), box)
        for p in st["players"]:
            cx, cy = tile_center(p["x"], p["y"])
            box = (cx - 44, cy - 44)
            region = mask.crop((box[0], box[1], box[0] + 88, box[1] + 88))
            mask.paste(ImageChops.subtract(region, SMALL_LIGHT), box)
        ImageDraw.Draw(mask).rectangle((0, 0, WIN_W, OY - 4), fill=0)
        img = Image.composite(Image.new("RGB", (WIN_W, WIN_H), (8, 10, 34)), img, mask)
        d = ImageDraw.Draw(img)
        for p in st["players"]:
            draw_bubble(d, p)
        draw_wind(d, st, frame)
    # HUD
    d.rectangle((0, 0, WIN_W, 48), fill=(24, 30, 52))
    d.line((0, 48, WIN_W, 48), fill=(70, 80, 120), width=2)
    d.text((12, 5), "Lantern Garden", font=F_TITLE, fill=(255, 214, 120))
    d.text((12, 29), "Arrows/click walk · Space act · T talk · N name",
           font=F_SMALL, fill=(170, 180, 210))
    if typing is not None:
        mode, text = typing
        label = ("Say: " if mode == "say" else "Name this place: ") + text + "_"
        tw = d.textlength(label, font=F_HUD)
        x0 = (WIN_W - tw) / 2 - 10
        d.rounded_rectangle((x0, WIN_H - 38, x0 + tw + 20, WIN_H - 12), radius=8,
                            fill=(250, 246, 225), outline=(60, 50, 40), width=2)
        d.text((x0 + 10, WIN_H - 34), label, font=F_HUD, fill=(40, 30, 30))
    if connected:
        d.rounded_rectangle((296, 10, 436, 38), radius=13, fill=(30, 120, 70),
                            outline=(120, 240, 160), width=2)
        d.ellipse((306, 19, 316, 29), fill=(140, 255, 170))
        d.text((322, 16), "LAN Connected", font=F_HUD, fill=(235, 255, 240))
    else:
        d.rounded_rectangle((296, 10, 436, 38), radius=13, fill=(120, 60, 40),
                            outline=(240, 160, 120), width=2)
        d.text((318, 16), "Connecting...", font=F_HUD, fill=(255, 235, 225))
    if st:
        glow, goal = st.get("glow", 0), st.get("goal", 12)
        d.text((450, 6), "Glow %d / %d" % (glow, goal), font=F_HUD, fill=(255, 230, 150))
        d.rounded_rectangle((450, 26, 600, 38), radius=6, outline=(150, 140, 100), width=1)
        fw = int(148 * min(1.0, glow / float(goal or 1)))
        if fw > 3:
            d.rounded_rectangle((451, 27, 451 + fw, 37), radius=5, fill=(255, 205, 90))
        chapter = st.get("chapter", 0)
        if chapter:
            d.text((612, 25), "Night %d · windy" % (chapter + 1), font=F_HUD,
                   fill=(255, 240, 170))
        if me:
            d.text((612, 6), "Seeds %d   Lit %d" % (me["seeds"], me["lit"]),
                   font=F_HUD, fill=(200, 235, 200))
    d.rounded_rectangle(ACT_BTN, radius=8, fill=(200, 120, 40),
                        outline=(255, 210, 140), width=2)
    d.text((ACT_BTN[0] + 12, ACT_BTN[1] + 7), "ACT (Space)", font=F_SMALL,
           fill=(255, 250, 235))
    return img


class App:
    def __init__(self):
        self.net = Net()
        self.frame = 0
        self.typing = None   # (mode, text) while entering free text
        win = Gtk.Window(title="Lantern Garden")
        win.set_default_size(WIN_W, WIN_H)
        win.set_resizable(False)
        win.set_position(Gtk.WindowPosition.CENTER)
        win.connect("destroy", Gtk.main_quit)
        self.image = Gtk.Image()
        box = Gtk.EventBox()
        box.add(self.image)
        box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        box.connect("button-press-event", self.on_click)
        win.add(box)
        win.connect("key-press-event", self.on_key)
        self.redraw()
        win.show_all()
        win.present()
        GLib.timeout_add(100, self.redraw)

    def redraw(self):
        self.frame += 1
        img = render(self.net, self.frame, self.typing)
        data = GLib.Bytes.new(img.tobytes())
        pb = GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB, False, 8,
                                             WIN_W, WIN_H, WIN_W * 3)
        self.image.set_from_pixbuf(pb)
        return True

    def on_click(self, _w, ev):
        x, y = ev.x, ev.y
        if ACT_BTN[0] <= x <= ACT_BTN[2] and ACT_BTN[1] <= y <= ACT_BTN[3]:
            self.net.send({"t": "act"})
            return True
        tx, ty = int((x - OX) // TILE), int((y - OY) // TILE)
        if 0 <= tx < GRID_W and 0 <= ty < GRID_H:
            self.net.send({"t": "goto", "x": tx, "y": ty})
        return True

    def on_key(self, _w, ev):
        name = Gdk.keyval_name(ev.keyval) or ""
        if self.typing is not None:
            mode, text = self.typing
            if name == "Return":
                if mode == "say" and text.strip():
                    self.net.send({"t": "say", "text": text.strip()})
                elif mode == "name":
                    self.net.send({"t": "name", "text": text.strip()})
                self.typing = None
            elif name == "Escape":
                self.typing = None
            elif name == "BackSpace":
                self.typing = (mode, text[:-1])
            else:
                ch = Gdk.keyval_to_unicode(ev.keyval)
                limit = 40 if mode == "say" else 24
                if ch >= 32 and len(text) < limit:
                    self.typing = (mode, text + chr(ch))
            return True
        if name in ("t", "T"):
            self.typing = ("say", "")
            return True
        if name in ("n", "N"):
            self.typing = ("name", "")
            return True
        moves = {"Left": (-1, 0), "a": (-1, 0), "Right": (1, 0), "d": (1, 0),
                 "Up": (0, -1), "w": (0, -1), "Down": (0, 1), "s": (0, 1)}
        key = name if len(name) > 1 else name.lower()
        if key in moves:
            dx, dy = moves[key]
            self.net.send({"t": "move", "dx": dx, "dy": dy})
        elif key in ("space", "Return"):
            self.net.send({"t": "act"})
        elif key in SAYINGS:
            self.net.send({"t": "say", "text": SAYINGS[key]})
        return True


if __name__ == "__main__":
    if "AAL_LAN_HOST" not in os.environ:
        sys.exit("AAL_LAN_HOST is not set")
    App()
    Gtk.main()
