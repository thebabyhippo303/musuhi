#!/usr/bin/env python3
"""Twilight Sky Garden - Lantern GUI client (854x480, GTK3 + PIL)."""
import json, math, os, socket, sys, threading, time
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from PIL import Image, ImageDraw, ImageFont

W, H = 854, 480
TS = 32
OX, OY = 8, 104
PANEL_X = 664
ROLE = os.environ.get("AAL_ROLE", "lantern")
NAME = os.environ.get("AAL_NAME", "Lantern")
FD = "/usr/share/fonts/truetype/dejavu/"
F = ImageFont.truetype(FD + "DejaVuSans.ttf", 12)
FS = ImageFont.truetype(FD + "DejaVuSans.ttf", 10)
FB = ImageFont.truetype(FD + "DejaVuSans-Bold.ttf", 14)
FT = ImageFont.truetype(FD + "DejaVuSans-Bold.ttf", 18)
COL = {"lantern": (255, 176, 64), "prism": (64, 224, 208)}
BUTTONS = [  # (label, key, x, y, w, h, msg)
    ("Plant  [Space]", "plant", PANEL_X, 168, 182, 28, {"t": "plant"}),
    ("Ring Chime  [C]", "chime", PANEL_X, 200, 182, 28, {"t": "chime"}),
    ("Light Star  [L]", "star", PANEL_X, 232, 182, 28, {"t": "star"}),
    ("Note  [N]", "note", PANEL_X, 264, 88, 28, None),
    ("Wave [1]", "wave", PANEL_X + 94, 264, 88, 28, {"t": "emote", "e": "wave"}),
    ("Heart [2]", "heart", PANEL_X, 296, 88, 28, {"t": "emote", "e": "heart"}),
    ("Spark [3]", "spark", PANEL_X + 94, 296, 88, 28, {"t": "emote", "e": "spark"}),
    ("Lamp [P]", "lamp", PANEL_X, 328, 88, 26, {"t": "lamp"}),
    ("Stone [B]", "build", PANEL_X + 94, 328, 88, 26, None),
]
DPAD = [("^", 0, -1, PANEL_X + 66, 360), ("<", -1, 0, PANEL_X + 22, 386),
        (">", 1, 0, PANEL_X + 110, 386), ("v", 0, 1, PANEL_X + 66, 412)]


class Client:
    def __init__(self):
        self.state = None
        self.my_id = None
        self.connected = False
        self.typing = None
        self.facing = (1, 0)
        self.flash = {}
        self.sock = None
        self.lock = threading.Lock()
        threading.Thread(target=self.net, daemon=True).start()

        self.win = Gtk.Window(title="Twilight Sky Garden - Lantern")
        self.win.set_default_size(W, H)
        self.win.set_resizable(False)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.win.connect("destroy", Gtk.main_quit)
        self.win.connect("key-press-event", self.on_key)
        self.eb = Gtk.EventBox()
        self.img = Gtk.Image()
        self.eb.add(self.img)
        self.eb.connect("button-press-event", self.on_click)
        self.win.add(self.eb)
        self.win.show_all()
        GLib.timeout_add(100, self.redraw)

    # ---- network ----
    def net(self):
        host = os.environ.get("AAL_LAN_HOST", "localhost")
        port = int(os.environ.get("AAL_LAN_PORT", "18765"))
        while True:
            try:
                s = socket.create_connection((host, port), timeout=5)
                s.settimeout(None)
                self.sock = s
                self.send({"t": "hello", "name": NAME, "role": ROLE})
                f = s.makefile("r", encoding="utf-8")
                for line in f:
                    m = json.loads(line)
                    if m.get("t") == "welcome":
                        self.my_id = m["id"]
                        self.connected = True
                        print("PHASE: LAN CONNECTED", flush=True)
                    elif m.get("t") == "state":
                        self.state = m
            except (OSError, ValueError):
                pass
            self.connected = False
            time.sleep(1.5)

    def send(self, obj):
        try:
            with self.lock:
                self.sock.sendall((json.dumps(obj) + "\n").encode())
        except (OSError, AttributeError):
            pass

    # ---- input ----
    def act(self, key, msg):
        self.flash[key] = time.time()
        if key == "note":
            self.typing = ""
        elif key == "build":
            self.send({"t": "build", "dx": self.facing[0], "dy": self.facing[1]})
        elif msg:
            self.send(msg)

    def move(self, dx, dy):
        self.facing = (dx, dy)
        self.flash["mv%d%d" % (dx, dy)] = time.time()
        self.send({"t": "move", "dx": dx, "dy": dy})

    def on_key(self, w, ev):
        k = Gdk.keyval_name(ev.keyval)
        if self.typing is not None:
            if k in ("Return", "KP_Enter"):
                if self.typing.strip():
                    self.send({"t": "note", "text": self.typing})
                self.typing = None
            elif k == "Escape":
                self.typing = None
            elif k == "BackSpace":
                self.typing = self.typing[:-1]
            else:
                ch = Gdk.keyval_to_unicode(ev.keyval)
                if ch and ch >= 32 and len(self.typing) < 60:
                    self.typing += chr(ch)
            return True
        mv = {"Up": (0, -1), "w": (0, -1), "Down": (0, 1), "s": (0, 1),
              "Left": (-1, 0), "a": (-1, 0), "Right": (1, 0), "d": (1, 0)}
        if k in mv:
            self.move(*mv[k])
            return True
        keymap = {"space": "plant", "c": "chime", "l": "star", "n": "note",
                  "1": "wave", "2": "heart", "3": "spark", "Return": "note", "p": "lamp", "b": "build"}
        if k in keymap:
            for b in BUTTONS:
                if b[1] == keymap[k]:
                    self.act(b[1], b[6])
            return True
        return False

    def on_click(self, w, ev):
        x, y = ev.x, ev.y
        for b in BUTTONS:
            if b[2] <= x < b[2] + b[4] and b[3] <= y < b[3] + b[5]:
                self.act(b[1], b[6])
                return True
        for lab, dx, dy, bx, by in DPAD:
            if bx <= x < bx + 50 and by <= y < by + 24:
                self.move(dx, dy)
                return True
        # click on island: step toward clicked tile
        st = self.state
        if st and self.my_id in st["players"] and OX <= x < OX + 20 * TS and OY <= y < OY + 10 * TS:
            me = st["players"][self.my_id]
            tx, ty = int((x - OX) // TS), int((y - OY) // TS)
            dx = (tx > me["x"]) - (tx < me["x"])
            dy = (ty > me["y"]) - (ty < me["y"])
            if dx or dy:
                self.move(dx, 0) if dx else None
                self.move(0, dy) if dy else None
        return True

    # ---- render ----
    def render(self):
        now = time.time()
        st = self.state
        bloom = st["bloom"] if st else 0
        im = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(im)
        for y in range(H):  # dusk gradient
            t = y / H
            d.line([(0, y), (W, y)], fill=(int(40 + 90 * t), int(24 + 30 * t), int(80 + 40 * (1 - t))))
        if bloom >= 60:  # aurora
            a = (bloom - 60) / 40
            for i in range(0, PANEL_X, 4):
                yy = 40 + 18 * math.sin(i / 50 + now)
                c = (int(120 * a), int(220 * a), int(160 * a)) if (i // 80) % 2 else (int(230 * a), int(150 * a), int(60 * a))
                d.line([(i, yy), (i, yy + 30)], fill=tuple(min(255, v + 60) for v in c))
        if st:
            lit = [s for s in st["stars"] if s["lit"]]
            for i, s in enumerate(st["stars"]):
                sx, sy = OX + s["x"] * 640, 8 + s["y"] * 90
                if s["lit"]:
                    c = (255, 220, 130) if s["by"] == NAME else (150, 255, 240)
                    r = 5 + math.sin(now * 3 + i)
                    d.ellipse([sx - r - 4, sy - r - 4, sx + r + 4, sy + r + 4], fill=tuple(v // 3 for v in c))
                    d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=c)
                else:
                    d.ellipse([sx - 2, sy - 2, sx + 2, sy + 2], fill=(110, 100, 150))
            for a, b in zip(lit, lit[1:]):
                d.line([(OX + a["x"] * 640, 8 + a["y"] * 90), (OX + b["x"] * 640, 8 + b["y"] * 90)],
                       fill=(230, 210, 255), width=1)
            wa = st.get("wish_age")
            if wa is not None and wa < 3:
                sx, sy = 40 + wa * 200, 10 + wa * 25
                for k in range(12):
                    c = int(255 - k * 18)
                    d.ellipse([sx - k * 12 - 3, sy - k * 1.5 - 3, sx - k * 12 + 3, sy - k * 1.5 + 3], fill=(c, c, int(c * 0.8)))
                d.text((320, 84), "A wish! (%d)" % st.get("wishes", 0), font=FB, fill=(255, 240, 200), anchor="mm")
            # island
            for ty, row in enumerate(st["island"]):
                for tx, ch in enumerate(row):
                    if ch == "#":
                        x0, y0 = OX + tx * TS, OY + ty * TS
                        g = 90 + ((tx + ty) % 2) * 12
                        d.rectangle([x0, y0, x0 + TS - 1, y0 + TS - 1], fill=(40, g, 70))
                        if ty == 9 or st["island"][ty + 1][tx] != "#" if ty < 9 else True:
                            d.rectangle([x0, y0 + TS - 6, x0 + TS - 1, y0 + TS - 1], fill=(90, 60, 50))
                    elif ch == "*":
                        x0, y0 = OX + tx * TS, OY + ty * TS
                        gl = int(30 * math.sin(now * 2 + tx + ty))
                        d.ellipse([x0 + 2, y0 + 6, x0 + TS - 3, y0 + TS - 4], fill=(150 + gl, 120, 200 + gl // 2), outline=(255, 230, 255))
            for l in st.get("lamps", []):
                lx, ly = OX + l["x"] * TS + 6, OY + l["y"] * TS + 4
                lc = COL.get(l["role"], (255, 255, 255))
                d.ellipse([lx - 8, ly - 8, lx + 8, ly + 8], fill=tuple(v // 3 for v in lc))
                d.line([(lx, ly), (lx, ly + 22)], fill=(60, 50, 70), width=3)
                d.ellipse([lx - 4, ly - 4, lx + 4, ly + 4], fill=lc)
            for n in st["notes"]:
                x0, y0 = OX + n["x"] * TS, OY + n["y"] * TS
                d.rectangle([x0 + 2, y0 + 2, x0 + 13, y0 + 13], fill=(250, 240, 200), outline=(120, 90, 40))
            for p in st["plants"]:
                cx, cy = OX + p["x"] * TS + 22, OY + p["y"] * TS + 20
                sg = p["stage"]
                d.line([(cx, cy + 10), (cx, cy - 2 - sg * 2)], fill=(80, 200, 90), width=2)
                r = 3 + sg * 2 + math.sin(now * 2 + p["x"]) * 0.8
                c = (255, 120, 200) if sg == 3 else (200, 160, 255)
                d.ellipse([cx - r - 3, cy - 6 - sg * 2 - r - 3, cx + r + 3, cy - 6 - sg * 2 + r + 3], fill=(90, 60, 110))
                d.ellipse([cx - r, cy - 6 - sg * 2 - r, cx + r, cy - 6 - sg * 2 + r], fill=c)
            for c in st["chimes"]:
                cx, cy = OX + c["x"] * TS + 16, OY + c["y"] * TS + 16
                d.line([(cx, cy - 14), (cx, cy + 14)], fill=(200, 200, 220), width=2)
                d.polygon([(cx - 8, cy - 4), (cx + 8, cy - 4), (cx + 5, cy + 8), (cx - 5, cy + 8)], fill=(210, 190, 120))
                ra = c["ring_age"]
                if ra is not None and ra < 2.5:
                    rr = 10 + ra * 40
                    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(255, 255, 200), width=2)
            # players
            seen = {}
            for pid, p in sorted(st["players"].items()):
                k = (p["x"], p["y"])
                off = 9 * seen.get(k, 0) - (9 if any((q["x"], q["y"]) == k for qid, q in st["players"].items() if qid != pid) and k not in seen else 0)
                seen[k] = seen.get(k, 0) + 1
                cx, cy = OX + p["x"] * TS + 16 + off, OY + p["y"] * TS + 14
                col = COL.get(p["role"], (255, 255, 255))
                glow = 18 + 3 * math.sin(now * 4)
                d.ellipse([cx - glow, cy - glow, cx + glow, cy + glow], fill=tuple(int(v * 0.35) + 30 for v in col))
                if p["role"] == "lantern":
                    d.rectangle([cx - 7, cy - 9, cx + 7, cy + 9], fill=(120, 70, 20))
                    d.rectangle([cx - 5, cy - 7, cx + 5, cy + 7], fill=col)
                    d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(255, 250, 220))
                    d.arc([cx - 5, cy - 17, cx + 5, cy - 7], 180, 360, fill=(180, 120, 40), width=2)
                else:
                    a = now * 1.5
                    pts = [(cx + 11 * math.cos(a + k * 2.094), cy + 11 * math.sin(a + k * 2.094)) for k in range(3)]
                    d.polygon(pts, fill=col, outline=(220, 255, 255))
                d.text((cx, cy + 22), p["name"], font=FS, fill=(255, 255, 255), anchor="mm")
                if p["emote"] and p["emote_age"] is not None and p["emote_age"] < 3:
                    sym = {"wave": "o/", "heart": "<3", "spark": "*"}[p["emote"]]
                    d.rounded_rectangle([cx - 14, cy - 40, cx + 14, cy - 22], 5, fill=(255, 255, 255))
                    d.text((cx, cy - 31), sym, font=FB, fill=(220, 40, 90), anchor="mm")
            # proximity aurora
            ps = list(st["players"].values())
            if len(ps) >= 2 and max(abs(ps[0]["x"] - ps[1]["x"]), abs(ps[0]["y"] - ps[1]["y"])) <= 1:
                a0 = (OX + ps[0]["x"] * TS + 16, OY + ps[0]["y"] * TS + 14)
                a1 = (OX + ps[1]["x"] * TS + 16, OY + ps[1]["y"] * TS + 14)
                d.line([a0, a1], fill=(200, 255, 200), width=3)
            # note under me
            me = st["players"].get(self.my_id)
            if me:
                for n in st["notes"]:
                    if (n["x"], n["y"]) == (me["x"], me["y"]):
                        d.rounded_rectangle([OX + 4, OY + 2, OX + 500, OY + 22], 6, fill=(250, 240, 200))
                        d.text((OX + 10, OY + 5), '%s: "%s"' % (n["by"], n["text"]), font=F, fill=(60, 40, 20))
        if bloom >= 100:
            d.text((OX + 636, OY - 4), "~ the aurora has bloomed ~", font=F, fill=(180, 255, 230), anchor="rb")
        # panel
        d.rounded_rectangle([PANEL_X - 6, 6, W - 6, H - 6], 10, fill=(24, 18, 44), outline=(120, 100, 180))
        d.text((PANEL_X, 12), "Twilight Sky Garden", font=FB, fill=(255, 220, 160))
        ok = self.connected
        d.rounded_rectangle([PANEL_X, 34, PANEL_X + 120, 54], 8, fill=(30, 140, 70) if ok else (150, 50, 50))
        d.text((PANEL_X + 60, 44), "LAN Connected" if ok else "Connecting...", font=F, fill=(255, 255, 255), anchor="mm")
        yy = 62
        if st:
            for pid, p in st["players"].items():
                col = COL.get(p["role"], (255, 255, 255))
                d.ellipse([PANEL_X, yy + 2, PANEL_X + 10, yy + 12], fill=col)
                d.text((PANEL_X + 16, yy), "%s%s" % (p["name"], " (you)" if pid == self.my_id else ""), font=F, fill=col)
                yy += 18
        yy = max(yy, 100)
        d.text((PANEL_X, yy), "Bloom %d%%" % bloom, font=F, fill=(230, 230, 255))
        d.rectangle([PANEL_X, yy + 18, PANEL_X + 182, yy + 30], outline=(150, 140, 200))
        d.rectangle([PANEL_X + 1, yy + 19, PANEL_X + 1 + int(180 * bloom / 100), yy + 29], fill=(255, 160, 90) if bloom < 100 else (120, 255, 200))
        if st:
            d.text((PANEL_X, yy + 34), "Plants %d Stars %d/10 Notes %d\nLamps %d  Wishes %d" % (
                len(st["plants"]), sum(s["lit"] for s in st["stars"]), len(st["notes"]),
                len(st.get("lamps", [])), st.get("wishes", 0)), font=FS, fill=(200, 200, 230))
        for lab, key, x, y, w, h, _ in BUTTONS:
            hot = now - self.flash.get(key, 0) < 0.2
            d.rounded_rectangle([x, y, x + w, y + h], 7, fill=(255, 190, 90) if hot else (70, 55, 120), outline=(190, 170, 255))
            d.text((x + w / 2, y + h / 2), lab, font=F, fill=(20, 10, 30) if hot else (255, 255, 255), anchor="mm")
        for lab, dx, dy, bx, by in DPAD:
            hot = now - self.flash.get("mv%d%d" % (dx, dy), 0) < 0.2
            d.rounded_rectangle([bx, by, bx + 50, by + 24], 7, fill=(255, 190, 90) if hot else (60, 90, 120), outline=(170, 220, 255))
            d.text((bx + 25, by + 12), lab, font=FB, fill=(255, 255, 255), anchor="mm")
        d.text((PANEL_X, 444), "Move: Arrows/WASD/click\nStone: B builds where you last moved", font=FS, fill=(180, 180, 210))
        # log
        d.rectangle([OX, OY + 324, OX + 640, H - 4], fill=(18, 12, 34))
        if st:
            for i, line in enumerate(st["log"][-3:]):
                d.text((OX + 6, OY + 326 + i * 16), line[:90], font=F, fill=(230, 220, 255))
        if self.typing is not None:
            d.rounded_rectangle([60, 200, 600, 260], 10, fill=(250, 240, 200), outline=(120, 90, 40), width=2)
            d.text((72, 206), "Write a note (Enter to place, Esc to cancel):", font=F, fill=(90, 60, 30))
            d.text((72, 228), self.typing + ("|" if int(now * 2) % 2 else ""), font=FB, fill=(40, 20, 10))
        return im

    def redraw(self):
        im = self.render()
        pb = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(im.tobytes()), GdkPixbuf.Colorspace.RGB,
                                             False, 8, W, H, W * 3)
        self.img.set_from_pixbuf(pb)
        return True


if __name__ == "__main__":
    Client()
    Gtk.main()
