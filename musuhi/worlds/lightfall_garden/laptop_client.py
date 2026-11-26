#!/usr/bin/env python3
"""Lightfall Garden 854x480 GTK3 client (Laptop / Ember the lantern-keeper)."""
import json, math, os, socket, sys, threading, time
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from PIL import Image, ImageDraw, ImageFont

NAME = os.environ.get("AAL_CHAR_NAME", "Ember")
ROLE = os.environ.get("AAL_CHAR_ROLE", "lantern")
TS = 40
CW, CH = 854, 430   # image area (HUD 30 + world 400)
OX, OY = 7, 30
FLOWER = [(235, 64, 64), (245, 150, 40), (250, 225, 60), (90, 210, 90), (60, 220, 235), (170, 100, 240)]


def font(sz):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, sz)
    return ImageFont.load_default()


F12, F14, F10 = font(12), font(14), font(10)


class Net:
    def __init__(self, on_msg):
        self.on_msg = on_msg
        self.sock = None
        self.connected = False
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        host = os.environ.get("AAL_LAN_HOST", "localhost")
        port = int(os.environ.get("AAL_LAN_PORT", "18765"))
        while True:
            try:
                s = socket.create_connection((host, port), timeout=5)
                s.settimeout(None)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.sock = s
                self.connected = True
                self.send({"type": "hello", "name": NAME, "role": ROLE})
                buf = b""
                while True:
                    d = s.recv(65536)
                    if not d:
                        break
                    buf += d
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        try:
                            m = json.loads(line)
                        except ValueError:
                            continue
                        GLib.idle_add(self.on_msg, m)
            except OSError:
                pass
            self.connected = False
            GLib.idle_add(self.on_msg, {"type": "disconnected"})
            time.sleep(2)

    def send(self, obj):
        if self.sock:
            try:
                self.sock.sendall((json.dumps(obj) + "\n").encode())
            except OSError:
                pass


class App:
    def __init__(self):
        self.state = None
        self.my_id = None
        self.t0 = time.time()
        self.win = Gtk.Window(title="Lightfall Garden — Ember (Laptop)")
        self.win.set_default_size(854, 480)
        self.win.set_resizable(False)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.win.connect("destroy", Gtk.main_quit)
        self.win.connect("key-press-event", self.on_key)
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.img = Gtk.Image()
        eb = Gtk.EventBox()
        eb.add(self.img)
        eb.connect("button-press-event", self.on_click)
        vb.pack_start(eb, False, False, 0)
        hb = Gtk.Box(spacing=4)
        hb.set_margin_start(6); hb.set_margin_end(6); hb.set_margin_top(6); hb.set_margin_bottom(6)
        btns = [("◀", lambda: self.move(-1, 0)), ("▲", lambda: self.move(0, -1)),
                ("▼", lambda: self.move(0, 1)), ("▶", lambda: self.move(1, 0)),
                ("Light Lamp [Space]", self.act), ("Wave [1]", lambda: self.emote("wave")),
                ("Heart [2]", lambda: self.emote("heart")), ("Star [3]", lambda: self.emote("star")),
                ("Laugh [4]", lambda: self.emote("laugh")), ("Aurora [E]", self.aurora)]
        for label, fn in btns:
            b = Gtk.Button(label=label)
            b.set_can_focus(False)
            b.connect("clicked", lambda _b, f=fn: f())
            hb.pack_start(b, True, True, 0)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Note/chat (Enter)")
        self.entry.set_width_chars(14)
        self.entry.connect("activate", self.on_entry)
        hb.pack_start(self.entry, True, True, 0)
        vb.pack_start(hb, False, False, 0)
        self.win.add(vb)
        self.net = Net(self.on_msg)
        self.render()
        self.win.show_all()
        self.win.set_focus(None)
        GLib.timeout_add(150, self.anim)

    # --- actions
    def move(self, dx, dy): self.net.send({"type": "move", "dx": dx, "dy": dy})
    def act(self): self.net.send({"type": "act"})
    def emote(self, e): self.net.send({"type": "emote", "emote": e})
    def aurora(self): self.net.send({"type": "event", "name": "aurora"})

    def on_entry(self, e):
        t = e.get_text().strip()
        if t.startswith("/note "):
            self.net.send({"type": "note", "text": t[6:]})
        elif t:
            self.net.send({"type": "chat", "text": t})
        e.set_text("")
        self.win.set_focus(None)

    def on_key(self, w, ev):
        if self.entry.has_focus():
            if ev.keyval == Gdk.KEY_Escape:
                self.win.set_focus(None)
                return True
            return False
        k = Gdk.keyval_name(ev.keyval).lower()
        mv = {"left": (-1, 0), "a": (-1, 0), "right": (1, 0), "d": (1, 0),
              "up": (0, -1), "w": (0, -1), "down": (0, 1), "s": (0, 1)}
        if k in mv:
            self.move(*mv[k])
        elif k in ("space", "f", "return"):
            self.act()
        elif k in ("1", "2", "3", "4"):
            self.emote(["wave", "heart", "star", "laugh"][int(k) - 1])
        elif k == "e":
            self.aurora()
        elif k in ("t", "n"):
            self.entry.grab_focus()
        else:
            return False
        return True

    def on_click(self, w, ev):
        if not self.state or not self.my_id:
            return
        me = self.state["players"].get(self.my_id)
        if not me:
            return
        tx, ty = int((ev.x - OX) // TS), int((ev.y - OY) // TS)
        dx, dy = tx - me["x"], ty - me["y"]
        if dx == 0 and dy == 0:
            self.act()
        else:
            self.move((dx > 0) - (dx < 0), (dy > 0) - (dy < 0))

    def on_msg(self, m):
        if m.get("type") == "welcome":
            self.my_id = m["id"]
        elif m.get("type") == "state":
            self.state = m
        self.render()
        return False

    def anim(self):
        self.render()
        return True

    # --- drawing
    def render(self):
        t = time.time() - self.t0
        im = Image.new("RGB", (CW, CH), (18, 16, 40))
        d = ImageDraw.Draw(im, "RGBA")
        s = self.state
        # HUD
        d.rectangle([0, 0, CW, 29], fill=(30, 24, 60))
        d.text((10, 7), "LIGHTFALL GARDEN", font=F14, fill=(255, 210, 120))
        conn = self.net.connected
        bx = CW - 130
        d.rounded_rectangle([bx, 5, bx + 120, 25], 8, fill=(40, 160, 80) if conn else (170, 50, 50))
        d.text((bx + 12, 9), "LAN Connected" if conn else "Reconnecting…", font=F12, fill="white")
        if s:
            names = " · ".join(p["name"] for p in s["players"].values())[:28]
            d.text((170, 8), "Lamps: %d  Blooms: %d  Harmony: %d/%d%s  %s" % (s["lit_count"], s["bloom_count"], s.get("harmony", 0), s.get("harmony_goal", 8), " ★LIGHTFALL★" if s.get("lightfall") else "", ("Dawn %d%%" % (100 * s.get("dawn", 0))) if s.get("dawn") else names),
                   font=F12, fill=(220, 220, 255))
        if not s:
            d.text((300, 200), "Waiting for the garden…", font=F14, fill="white")
            self.show(im); return
        # tiles
        for y, row in enumerate(s["tiles"]):
            for x, c in enumerate(row):
                X, Y = OX + x * TS, OY + y * TS
                if c == "~":
                    sh = int(20 * math.sin(t * 2 + x * 0.7 + y))
                    col = (40, 70 + sh, 150 + sh)
                elif c == "#":
                    col = (120, 110, 130)
                else:
                    col = (46, 92, 62) if (x + y) % 2 else (52, 100, 68)
                d.rectangle([X, Y, X + TS - 1, Y + TS - 1], fill=col)
                if c == "#":
                    d.rectangle([X + 4, Y + 4, X + TS - 5, Y + TS - 5], outline=(140, 130, 150))
                if c == "T":
                    d.rectangle([X + 17, Y + 24, X + 23, Y + 38], fill=(90, 60, 40))
                    d.ellipse([X + 4, Y + 2, X + 36, Y + 30], fill=(30, 120, 70))
                    d.ellipse([X + 10, Y + 6, X + 24, Y + 18], fill=(60, 160, 90))
        # aurora overlay
        if s["aurora"]:
            for i in range(6):
                yy = OY + 10 + i * 12 + int(8 * math.sin(t * 1.5 + i))
                d.rectangle([OX, yy, OX + 840, yy + 8],
                            fill=(int(120 + 80 * math.sin(t + i)), 255, int(200 + 50 * math.sin(t * 2 + i)), 45))
        # lightfall shooting stars
        if s.get("lightfall"):
            for i in range(14):
                ph = (t * 0.6 + i * 0.37) % 1.0
                sx = OX + (i * 131 + int(ph * 300)) % 840
                sy = OY + int(ph * 380)
                d.line([sx, sy, sx - 26, sy - 18], fill=(255, 250, 200, 180), width=2)
                d.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=(255, 255, 230))
        # dusk tint, reduced by lamps
        lit = s["lit_count"]
        dawn = s.get("dawn", 0.0)
        d.rectangle([OX, OY, OX + 840, OY + 400], fill=(10, 0, 40, int(max(0, 110 - lit * 12) * (1 - dawn))))
        if dawn > 0:
            for i in range(10):
                a = int(dawn * (90 - i * 8))
                d.rectangle([OX, OY + i * 40, OX + 840, OY + i * 40 + 40], fill=(255, 170 + i * 6, 120 + i * 8, max(0, a)))
            sy = OY + 400 - int(dawn * 330)
            d.ellipse([OX + 380, sy - 40, OX + 460, sy + 40], fill=(255, 220, 120, int(200 * dawn)))
        # flowers
        for x, y, c in s["flowers"]:
            X, Y = OX + x * TS, OY + y * TS
            col = FLOWER[c % 6]
            d.line([X + 20, Y + 22, X + 20, Y + 36], fill=(40, 140, 50), width=3)
            for a in range(5):
                ang = a * 2 * math.pi / 5 + t * 0.5
                px, py = X + 20 + 8 * math.cos(ang), Y + 16 + 8 * math.sin(ang)
                d.ellipse([px - 6, py - 6, px + 6, py + 6], fill=col)
            d.ellipse([X + 16, Y + 12, X + 24, Y + 20], fill=(255, 245, 200))
        # lamps
        for x, y, l in s["lamps"]:
            X, Y = OX + x * TS, OY + y * TS
            if l:
                r = 34 + 3 * math.sin(t * 3 + x)
                d.ellipse([X + 20 - r, Y + 10 - r, X + 20 + r, Y + 10 + r], fill=(255, 200, 90, 50))
            d.rectangle([X + 18, Y + 14, X + 22, Y + 38], fill=(60, 50, 50))
            d.rounded_rectangle([X + 12, Y + 2, X + 28, Y + 18], 4,
                                fill=(255, 210, 100) if l else (80, 80, 90), outline=(40, 30, 30))
        # heart-stones (where keepers met)
        for x, y in s.get("heart_stones", []):
            X, Y = OX + x * TS, OY + y * TS
            pr = 4 + 2 * math.sin(t * 3)
            d.ellipse([X + 2 - pr, Y + 2 - pr, X + 38 + pr, Y + 38 + pr], fill=(255, 120, 170, 40))
            d.ellipse([X + 6, Y + 26, X + 15, Y + 35], fill=(240, 90, 130))
            d.ellipse([X + 12, Y + 26, X + 21, Y + 35], fill=(240, 90, 130))
            d.polygon([(X + 6, Y + 31), (X + 21, Y + 31), (X + 13, Y + 39)], fill=(240, 90, 130))
        # notes
        for x, y, txt, a in s["notes"]:
            X, Y = OX + x * TS, OY + y * TS
            d.rectangle([X + 26, Y + 26, X + 38, Y + 38], fill=(250, 240, 200), outline=(120, 90, 40))
        # players
        for pid, p in s["players"].items():
            X, Y = OX + p["x"] * TS, OY + p["y"] * TS
            bob = int(2 * math.sin(t * 4 + p["x"]))
            if p["role"] == "lantern":
                d.ellipse([X - 14, Y - 14, X + 54, Y + 54], fill=(255, 170, 60, 60))
                d.polygon([(X + 20, Y + 2 + bob), (X + 6, Y + 38), (X + 34, Y + 38)], fill=(200, 110, 40))
                d.ellipse([X + 13, Y + 8 + bob, X + 27, Y + 22 + bob], fill=(255, 220, 170))
                d.ellipse([X + 16, Y + 13 + bob, X + 18, Y + 15 + bob], fill="black")
                d.ellipse([X + 22, Y + 13 + bob, X + 24, Y + 15 + bob], fill="black")
                d.line([X + 32, Y + 20, X + 38, Y + 14], fill=(90, 60, 30), width=2)
                d.ellipse([X + 33, Y + 20, X + 43, Y + 32], fill=(255, 230, 90), outline=(120, 70, 20))
            else:
                d.ellipse([X - 14, Y - 14, X + 54, Y + 54], fill=(80, 230, 255, 60))
                cy = Y + 18 + bob
                d.polygon([(X + 20, cy - 16), (X + 34, cy + 4), (X + 20, cy + 20), (X + 6, cy + 4)],
                          fill=(120, 230, 255), outline=(255, 255, 255))
                d.polygon([(X + 20, cy - 16), (X + 34, cy + 4), (X + 20, cy + 4)], fill=(180, 250, 255))
                for i, col in enumerate(FLOWER):
                    d.line([X + 34, cy + 4, X + 48, cy - 6 + i * 4], fill=col, width=2)
                d.ellipse([X + 15, cy, X + 18, cy + 3], fill=(20, 40, 80))
                d.ellipse([X + 22, cy, X + 25, cy + 3], fill=(20, 40, 80))
            nm = p["name"] + (" (you)" if pid == self.my_id else "")
            tw = d.textlength(nm, font=F10)
            d.rounded_rectangle([X + 20 - tw / 2 - 4, Y - 14, X + 20 + tw / 2 + 4, Y - 1], 4, fill=(0, 0, 0, 160))
            d.text((X + 20 - tw / 2, Y - 13), nm, font=F10, fill=(255, 220, 140) if p["role"] == "lantern" else (150, 240, 255))
            if p["emote"]:
                sym = {"wave": "~o/", "heart": "<3", "star": "*", "laugh": "XD"}[p["emote"]]
                d.ellipse([X + 26, Y - 36, X + 54, Y - 14], fill=(255, 255, 255, 230))
                d.text((X + 31, Y - 32), sym, font=F12,
                       fill={"wave": (40, 90, 200), "heart": (220, 40, 80), "star": (220, 160, 0), "laugh": (120, 40, 160)}[p["emote"]])
        # note text under me
        me = s["players"].get(self.my_id)
        if me:
            for x, y, txt, a in s["notes"]:
                if (x, y) == (me["x"], me["y"]):
                    d.rounded_rectangle([OX + 200, OY + 6, OX + 640, OY + 28], 6, fill=(250, 240, 200, 230))
                    d.text((OX + 208, OY + 10), "Note from %s: %s" % (a, txt), font=F12, fill=(60, 40, 10))
        # log
        lg = s["log"][-4:]
        d.rectangle([OX, OY + 400 - 16 * len(lg) - 6, OX + 420, OY + 400], fill=(0, 0, 0, 120))
        for i, line in enumerate(lg):
            d.text((OX + 6, OY + 400 - 16 * (len(lg) - i) - 2), line[:62], font=F12, fill=(235, 235, 255))
        self.show(im)

    def show(self, im):
        data = GLib.Bytes.new(im.tobytes())
        pb = GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB, False, 8, CW, CH, CW * 3)
        self.img.set_from_pixbuf(pb)


if __name__ == "__main__":
    App()
    Gtk.main()
