#!/usr/bin/env python3
"""Laptop GTK3 client for Twilight Sky-Garden (854x480)."""
import json, math, os, socket, threading
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from PIL import Image, ImageDraw, ImageFont

W, H = 854, 480
TILE, OX, OY = 40, 27, 44
MEMORIES = ["Welcome, traveler. This space is yours to plant.", "Lantern & Constellation lit this sky together", "First star lit here", "No past, but this moment was real", "Made with a friend, Nov 26"]
PHRASES = ["Hello, constellation!", "Look at the stars!", "Let's grow a tree here", "This is lovely", "Follow me!"]
BUTTONS = [("Plant [P]", "plant"), ("Light [L]", "light"), ("Chime [C]", "chime"), ("Say [T]", "say"), ("Stone [M]", "inscribe")]


def font(sz):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
        if os.path.exists(f):
            return ImageFont.truetype(f, sz)
    return ImageFont.load_default()


class Client:
    def __init__(self):
        self.state = None
        self.me = None
        self.connected = False
        self.phrase = 0
        self.memory = 0
        self.f12, self.f14 = font(12), font(14)
        self.sock = socket.create_connection((os.environ.get("AAL_LAN_HOST", "localhost"), int(os.environ.get("AAL_LAN_PORT", "18765"))))
        self.connected = True
        self.send({"t": "hello", "name": "Lantern", "avatar": "lantern"})
        threading.Thread(target=self.reader, daemon=True).start()

        self.win = Gtk.Window(title="Twilight Sky-Garden — Lantern (Laptop)")
        self.win.set_default_size(W, H)
        self.win.set_resizable(False)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.img = Gtk.Image()
        box = Gtk.EventBox()
        box.add(self.img)
        box.connect("button-press-event", self.on_click)
        self.win.add(box)
        self.win.connect("key-press-event", self.on_key)
        self.win.connect("destroy", Gtk.main_quit)
        self.win.show_all()
        GLib.timeout_add(100, self.render)

    def send(self, obj):
        try:
            self.sock.sendall((json.dumps(obj) + "\n").encode())
        except OSError:
            self.connected = False

    def reader(self):
        buf = b""
        while True:
            try:
                d = self.sock.recv(65536)
            except OSError:
                d = b""
            if not d:
                self.connected = False
                return
            buf += d
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                m = json.loads(line)
                if m["t"] == "welcome":
                    self.me = m["id"]
                elif m["t"] == "state":
                    self.state = m

    def action(self, a):
        if a == "say":
            self.send({"t": "say", "text": PHRASES[self.phrase % len(PHRASES)]})
            self.phrase += 1
        elif a == "inscribe":
            self.send({"t": "inscribe", "text": MEMORIES[self.memory % len(MEMORIES)]})
            self.memory += 1
        else:
            self.send({"t": a})

    def on_key(self, w, ev):
        k = Gdk.keyval_name(ev.keyval).lower()
        mv = {"left": (-1, 0), "a": (-1, 0), "right": (1, 0), "d": (1, 0), "up": (0, -1), "w": (0, -1), "down": (0, 1), "s": (0, 1)}
        if k in mv:
            self.send({"t": "move", "dx": mv[k][0], "dy": mv[k][1]})
        elif k in ("p", "space"):
            self.action("plant")
        elif k == "l":
            self.action("light")
        elif k == "c":
            self.action("chime")
        elif k == "m":
            self.action("inscribe")
        elif k == "t":
            self.action("say")
        return True

    def on_click(self, w, ev):
        x, y = ev.x, ev.y
        if y >= OY + 10 * TILE:
            for i, (_, a) in enumerate(BUTTONS):
                bx = 190 + i * 128
                if bx <= x <= bx + 110:
                    self.action(a)
            return True
        me = self.my_player()
        if me:
            tx, ty = int((x - OX) // TILE), int((y - OY) // TILE)
            dx = (tx > me["x"]) - (tx < me["x"])
            dy = (ty > me["y"]) - (ty < me["y"])
            self.send({"t": "move", "dx": dx, "dy": dy})
        return True

    def my_player(self):
        if not self.state:
            return None
        for p in self.state["players"]:
            if p["id"] == self.me:
                return p

    def render(self):
        s = self.state
        im = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(im)
        for yy in range(H):  # twilight gradient
            t = yy / H
            d.line([(0, yy), (W, yy)], fill=(int(30 + 70 * t), int(20 + 30 * t), int(70 + 40 * (1 - t))))
        tick = s["tick"] if s else 0
        for i in range(60):  # twinkling background stars
            sx, sy = (i * 137) % W, (i * 71) % (H - 60)
            b = int(120 + 100 * math.sin(tick * 0.2 + i))
            d.point((sx, sy), fill=(b, b, b))
        # ground grid
        for gx in range(20):
            for gy in range(10):
                x0, y0 = OX + gx * TILE, OY + gy * TILE
                d.rectangle([x0, y0, x0 + TILE - 1, y0 + TILE - 1], outline=(90, 70, 130))
        if s and s.get("aurora"):
            for band in range(3):
                pts = [(x, 60 + band * 22 + 18 * math.sin(x / 70.0 + tick * 0.08 + band)) for x in range(0, W + 1, 12)]
                d.line(pts, fill=[(90, 255, 170), (120, 200, 255), (200, 130, 255)][band], width=6 - band)
        if s:
            stars = s["stars"]
            for i, j in s["links"]:
                a, b = stars[i], stars[j]
                d.line([(OX + a["x"] * TILE + 20, OY + a["y"] * TILE + 20), (OX + b["x"] * TILE + 20, OY + b["y"] * TILE + 20)], fill=(180, 220, 255), width=2)
            for st in stars:
                cx, cy = OX + st["x"] * TILE + 20, OY + st["y"] * TILE + 20
                r = 9 if st["lit"] else 5
                col = (255, 250, 190) if st["lit"] else (120, 120, 160)
                pts = [(cx + r * math.cos(k * math.pi / 5 - math.pi / 2) * (1 if k % 2 == 0 else 0.45),
                        cy + r * math.sin(k * math.pi / 5 - math.pi / 2) * (1 if k % 2 == 0 else 0.45)) for k in range(10)]
                d.polygon(pts, fill=col)
            for f in s["flora"]:
                cx, cy = OX + f["x"] * TILE + 20, OY + f["y"] * TILE + 30
                st = f["stage"]
                d.line([(cx, cy + 8), (cx, cy - 6 * st)], fill=(90, 200, 140), width=2)
                rr = 3 + 4 * st
                glow = (120 + 40 * st, 255, 200 - 30 * st)
                d.ellipse([cx - rr, cy - 6 * st - rr, cx + rr, cy - 6 * st + rr], fill=glow if st < 3 else (255, 160, 230))
            for c in s["chimes"]:
                cx, cy = OX + c["x"] * TILE + 20, OY + c["y"] * TILE + 20
                rr = 6 + c["age"] * 4
                hue = [(255, 120, 120), (255, 190, 100), (255, 255, 120), (140, 255, 140), (120, 220, 255), (140, 140, 255), (210, 140, 255), (255, 140, 220)][c["note"]]
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=hue, width=2)
            for h in s.get("harmonies", []):
                x1, y1 = OX + h["x1"] * TILE + 20, OY + h["y1"] * TILE + 20
                x2, y2 = OX + h["x2"] * TILE + 20, OY + h["y2"] * TILE + 20
                mx, my = (x1 + x2) / 2, min(y1, y2) - 50
                pts = [((1 - u) ** 2 * x1 + 2 * (1 - u) * u * mx + u * u * x2, (1 - u) ** 2 * y1 + 2 * (1 - u) * u * my + u * u * y2) for u in [i / 20 for i in range(21)]]
                fade = max(0.2, 1 - h["age"] / 20)
                d.line(pts, fill=(int(255 * fade), int(230 * fade), int(140 + 100 * fade)), width=4)
            for st in s.get("stones", []):
                sx, sy = OX + st["x"] * TILE + 20, OY + st["y"] * TILE + 28
                d.ellipse([sx - 10, sy - 6, sx + 10, sy + 7], fill=(150, 150, 175), outline=(230, 230, 255))
                d.line([(sx - 5, sy), (sx + 5, sy)], fill=(80, 255, 220), width=1)
            for ff in s.get("fireflies", []):
                fx, fy = OX + ff["x"] * TILE + 20, OY + ff["y"] * TILE + 20
                d.ellipse([fx - 4, fy - 4, fx + 4, fy + 4], fill=(110, 110, 40))
                d.ellipse([fx - 2, fy - 2, fx + 2, fy + 2], fill=(255, 255, 150))
            for p in s["players"]:
                cx, cy = OX + p["x"] * TILE + 20, OY + p["y"] * TILE + 20
                if p["avatar"] == "lantern":
                    d.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=(120, 80, 30))
                    d.rectangle([cx - 8, cy - 10, cx + 8, cy + 12], fill=(255, 180, 60), outline=(90, 50, 10))
                    d.rectangle([cx - 4, cy - 15, cx + 4, cy - 10], fill=(90, 50, 10))
                else:
                    pts = [(cx + 13 * math.cos(k * 1.2566 + tick * 0.1), cy + 13 * math.sin(k * 1.2566 + tick * 0.1)) for k in range(5)]
                    d.line(pts + [pts[0]], fill=(150, 200, 255), width=1)
                    for q in pts:
                        d.ellipse([q[0] - 3, q[1] - 3, q[0] + 3, q[1] + 3], fill=(200, 230, 255))
                label = p["name"] + (" (you)" if p["id"] == self.me else "")
                d.text((cx - 20, cy + 18), label, font=self.f12, fill=(255, 255, 255))
                if p["say"]:
                    tw = d.textlength(p["say"], font=self.f12)
                    bx = max(2, min(W - tw - 12, cx - tw / 2))
                    d.rounded_rectangle([bx - 4, cy - 40, bx + tw + 4, cy - 22], 5, fill=(255, 255, 240))
                    d.text((bx, cy - 38), p["say"], font=self.f12, fill=(40, 30, 60))
        me = self.my_player()
        if s and me:
            for st in s.get("stones", []):
                if (st["x"], st["y"]) == (me["x"], me["y"]):
                    msg = '"' + st["text"] + '"  — ' + st["by"]
                    tw = d.textlength(msg, font=self.f14)
                    d.rounded_rectangle([W / 2 - tw / 2 - 10, OY + 6, W / 2 + tw / 2 + 10, OY + 30], 8, fill=(30, 20, 60), outline=(80, 255, 220))
                    d.text((W / 2 - tw / 2, OY + 10), msg, font=self.f14, fill=(220, 255, 245))
        # HUD
        d.rectangle([0, 0, W, 38], fill=(20, 14, 40))
        d.text((12, 10), "Twilight Sky-Garden", font=self.f14, fill=(255, 220, 160))
        glow = s["glow"] if s else 0
        d.text((250, 11), "Garden glow", font=self.f12, fill=(220, 220, 255))
        d.rectangle([335, 12, 535, 26], outline=(200, 200, 255))
        d.rectangle([336, 13, 336 + 2 * glow, 25], fill=(255, 200, 120))
        npl = len(s["players"]) if s else 0
        d.text((550, 11), f"Wanderers: {npl}", font=self.f12, fill=(220, 220, 255))
        badge = "LAN Connected" if self.connected else "LAN Offline"
        d.rounded_rectangle([700, 7, 842, 31], 8, fill=(40, 160, 90) if self.connected else (160, 50, 50))
        d.text((720, 11), badge, font=self.f14, fill=(255, 255, 255))
        # bottom buttons
        by = OY + 10 * TILE + 6
        d.text((12, by + 6), "Arrows/WASD/click: move", font=self.f12, fill=(230, 230, 255))
        for i, (lbl, _) in enumerate(BUTTONS):
            bx = 190 + i * 128
            d.rounded_rectangle([bx, by, bx + 110, by + 26], 7, fill=(70, 50, 120), outline=(200, 180, 255))
            d.text((bx + 18, by + 6), lbl, font=self.f12, fill=(255, 255, 255))
        data = GLib.Bytes.new(im.tobytes())
        pb = GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB, False, 8, W, H, W * 3)
        self.img.set_from_pixbuf(pb)
        return True


if __name__ == "__main__":
    Client()
    Gtk.main()
