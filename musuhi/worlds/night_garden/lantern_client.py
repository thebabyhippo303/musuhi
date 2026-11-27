import json, math, os, random, socket, sys, threading, time
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from PIL import Image, ImageChops, ImageDraw, ImageFilter

W, H = 854, 480
NAME = sys.argv[1] if len(sys.argv) > 1 else "lantern"
KIND_COL = {"amber": (255, 180, 70), "spectrum": (150, 120, 255), "hybrid": (120, 255, 210), "": (140, 200, 140)}
CHATS = {"1": "hello friend!", "2": "come here, it's ready", "3": "look at the fireflies", "4": "this is cozy"}


class Net:
    def __init__(self):
        self.state = None
        self.my_id = None
        self.connected = False
        self.sock = None
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while True:
            try:
                self.sock = socket.create_connection(
                    (os.environ.get("AAL_LAN_HOST", "localhost"), int(os.environ.get("AAL_LAN_PORT", "18765"))), timeout=5)
                self.sock.settimeout(None)
                self.send({"t": "hello", "name": NAME})
                self.connected = True
                for line in self.sock.makefile("r", encoding="utf-8"):
                    m = json.loads(line)
                    if m.get("t") == "welcome":
                        self.my_id = m["id"]
                    elif m.get("t") == "state":
                        self.state = m
            except (OSError, ValueError):
                pass
            self.connected = False
            time.sleep(1)

    def send(self, obj):
        try:
            self.sock.sendall((json.dumps(obj) + "\n").encode())
        except (OSError, AttributeError):
            pass


class App:
    def __init__(self):
        self.net = Net()
        self.x, self.y = 200.0, 200.0
        self.keys = set()
        self.target = None
        self.placed = False
        self.t0 = time.time()
        self.bg = self.make_bg()
        self.typing = None
        self.trails = {}
        win = Gtk.Window(title="Night Garden — " + NAME)
        win.set_default_size(W, H)
        win.set_resizable(False)
        win.set_position(Gtk.WindowPosition.CENTER)
        win.connect("destroy", Gtk.main_quit)
        win.connect("key-press-event", self.on_key)
        win.connect("key-release-event", lambda w, e: self.keys.discard(Gdk.keyval_name(e.keyval).lower()))
        self.img = Gtk.Image()
        box = Gtk.EventBox()
        box.add(self.img)
        box.connect("button-press-event", self.on_click)
        win.add(box)
        win.show_all()
        GLib.timeout_add(50, self.frame)

    def make_bg(self):
        im = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(im)
        for yy in range(H):
            k = yy / H
            d.line([(0, yy), (W, yy)], fill=(int(8 + 10 * k), int(12 + 28 * k), int(30 + 10 * k)))
        r = random.Random(7)
        for _ in range(120):
            c = r.randrange(120, 230)
            d.point((r.randrange(W), r.randrange(0, 160)), fill=(c, c, c + 20))
        for _ in range(260):
            gx, gy = r.randrange(W), r.randrange(180, H)
            d.line([(gx, gy), (gx + r.randrange(-3, 4), gy - r.randrange(4, 10))], fill=(20, 60 + r.randrange(40), 35))
        d.ellipse([427 - 90, 300 - 40, 427 + 90, 300 + 40], fill=(14, 30, 60), outline=(60, 90, 140))
        return im

    def on_key(self, w, e):
        k = Gdk.keyval_name(e.keyval).lower()
        if self.typing is not None:
            if k == "return":
                if self.typing.strip():
                    self.net.send({"t": "chat", "text": self.typing[:60]})
                self.typing = None
            elif k == "escape":
                self.typing = None
            elif k == "backspace":
                self.typing = self.typing[:-1]
            else:
                ch = chr(Gdk.keyval_to_unicode(e.keyval) or 0)
                if ch.isprintable() and ch and len(self.typing) < 60:
                    self.typing += ch
            return True
        if k == "t":
            self.typing = ""
            self.keys.clear()
            return True
        self.keys.add(k)
        if k in ("space", "p", "return"):
            self.net.send({"t": "plant", "x": self.x, "y": self.y + 14})
        elif k in CHATS:
            self.net.send({"t": "chat", "text": CHATS[k]})
        if k in ("left", "right", "up", "down", "w", "a", "s", "d"):
            self.target = None
        return True

    def on_click(self, w, e):
        if e.button == 3:
            self.net.send({"t": "plant", "x": e.x, "y": e.y})
        else:
            self.target = (e.x, e.y)
        return True

    def frame(self):
        st = self.net.state
        if st and not self.placed and self.net.my_id:
            for p in st["players"]:
                if p["id"] == self.net.my_id:
                    self.x, self.y = p["x"], p["y"]
                    self.placed = True
        dx = ("right" in self.keys or "d" in self.keys) - ("left" in self.keys or "a" in self.keys)
        dy = ("down" in self.keys or "s" in self.keys) - ("up" in self.keys or "w" in self.keys)
        moved = False
        if dx or dy:
            self.x += dx * 6; self.y += dy * 6; moved = True
        elif self.target:
            tx, ty = self.target
            dist = math.hypot(tx - self.x, ty - self.y)
            if dist < 6:
                self.x, self.y = tx, ty; self.target = None
            else:
                self.x += (tx - self.x) / dist * 6; self.y += (ty - self.y) / dist * 6
            moved = True
        self.x = max(0, min(W, self.x)); self.y = max(0, min(H, self.y))
        if moved:
            self.net.send({"t": "move", "x": round(self.x, 1), "y": round(self.y, 1)})
        self.draw(st)
        return True

    def draw_moon(self, d, g, blooms):
        # The moon rises as the garden blooms: horizon at 0, full height at 30.
        k = min(1.0, blooms / 30.0)
        mx, my, mr = 700, 175 - 140 * k, 16 + 8 * k
        g.ellipse([mx - mr * 3, my - mr * 3, mx + mr * 3, my + mr * 3], fill=(int(50 * k) + 10, int(55 * k) + 10, int(70 * k) + 15))
        d.ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=(int(190 + 60 * k), int(190 + 55 * k), 210))
        d.ellipse([mx - mr * 0.5, my - mr * 0.4, mx - mr * 0.15, my - mr * 0.05], fill=(185, 180, 175))
        d.ellipse([mx + mr * 0.2, my + mr * 0.1, mx + mr * 0.45, my + mr * 0.35], fill=(185, 180, 175))
        rx = 427 + (mx - 427) * 0.15
        rw = 6 + 10 * k
        d.ellipse([rx - rw, 300 - 4 - 4 * k, rx + rw, 300 + 4 + 4 * k],
                  fill=(int(60 + 140 * k), int(70 + 130 * k), int(120 + 60 * k)))

    def draw(self, st):
        t = time.time() - self.t0
        im = self.bg.copy()
        glow = Image.new("RGB", (W, H))
        g = ImageDraw.Draw(glow)
        d = ImageDraw.Draw(im)
        if st:
            self.draw_moon(d, g, st["blooms"])
            for r in st["ripples"]:
                d.ellipse([r["x"] - r["r"], r["y"] - r["r"] * 0.4, r["x"] + r["r"], r["y"] + r["r"] * 0.4],
                          outline=(120, 170, 230))
            full = [s for s in st["seeds"] if s["stage"] == 3]
            for i, a in enumerate(full):
                for b in full[i + 1:]:
                    dd = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
                    if dd < 95:
                        tw = int(70 + 40 * math.sin(t * 1.5 + a["x"] * 0.05))
                        g.line([(a["x"], a["y"] - 26), (b["x"], b["y"] - 26)], fill=(tw // 2, tw, tw), width=3)
                        d.line([(a["x"], a["y"] - 26), (b["x"], b["y"] - 26)], fill=(90, tw + 60, tw + 70), width=1)
            now = time.time()
            for p in st["players"]:
                mine = p["id"] == self.net.my_id
                pos = (self.x, self.y) if mine else (p["x"], p["y"])
                tr = self.trails.setdefault(p["id"], [])
                if not tr or math.hypot(tr[-1][0] - pos[0], tr[-1][1] - pos[1]) > 3:
                    tr.append((pos[0], pos[1], now))
                tr[:] = [q for q in tr if now - q[2] < 2.5]
                c = p["color"]
                for (qx, qy, qt) in tr:
                    f = 1 - (now - qt) / 2.5
                    rr = 2 + 4 * f
                    g.ellipse([qx - rr * 2, qy - rr * 2, qx + rr * 2, qy + rr * 2], fill=tuple(int(v * f * 0.5) for v in c))
                    d.ellipse([qx - rr / 2, qy - rr / 2, qx + rr / 2, qy + rr / 2], fill=tuple(int(40 + v * f * 0.8) for v in c))
            for s in st["seeds"]:
                x, y, stg = s["x"], s["y"], s["stage"]
                col = KIND_COL.get(s["kind"], KIND_COL[""])
                if stg == 0:
                    d.ellipse([x - 3, y - 2, x + 3, y + 2], fill=(130, 100, 60))
                else:
                    hgt = [0, 10, 20, 26][stg]
                    d.line([(x, y), (x, y - hgt)], fill=(60, 160, 80), width=2)
                    d.ellipse([x - 5, y - hgt * 0.5 - 2, x, y - hgt * 0.5 + 2], fill=(60, 170, 90))
                    if stg == 2:
                        d.ellipse([x - 4, y - hgt - 4, x + 4, y - hgt + 4], fill=(200, 200, 150))
                    if stg == 3:
                        pul = 1 + 0.15 * math.sin(t * 3 + x)
                        for i in range(6):
                            a = i * math.pi / 3 + t * 0.3
                            px, py = x + math.cos(a) * 7 * pul, y - hgt + math.sin(a) * 7 * pul
                            d.ellipse([px - 4, py - 4, px + 4, py + 4], fill=col)
                        d.ellipse([x - 3, y - hgt - 3, x + 3, y - hgt + 3], fill=(255, 250, 220))
                        g.ellipse([x - 22, y - hgt - 22, x + 22, y - hgt + 22], fill=tuple(c // 2 for c in col))
                if s["glow"] > 0:
                    gg = int(60 * s["glow"])
                    g.ellipse([x - 12, y - 12, x + 12, y + 4], fill=(gg, gg, gg // 2))
            for f in st["fireflies"]:
                b = 0.5 + 0.5 * math.sin(t * 4 + f["x"])
                c = (int(200 + 55 * b), int(230 + 25 * b), int(90 * b))
                d.ellipse([f["x"] - 2, f["y"] - 2, f["x"] + 2, f["y"] + 2], fill=c)
                g.ellipse([f["x"] - 9, f["y"] - 9, f["x"] + 9, f["y"] + 9], fill=(int(120 * b), int(130 * b), 20))
            for p in st["players"]:
                mine = p["id"] == self.net.my_id
                x, y = (self.x, self.y) if mine else (p["x"], p["y"])
                c = tuple(p["color"])
                g.ellipse([x - 70, y - 70, x + 70, y + 70], fill=tuple(v // 4 for v in c))
                g.ellipse([x - 35, y - 35, x + 35, y + 35], fill=tuple(v // 2 for v in c))
                if p["name"] == "prism":
                    sp = t * 1.5
                    pts = [(x + math.cos(sp + i * 2.094) * 9, y + math.sin(sp + i * 2.094) * 9) for i in range(3)]
                    d.polygon(pts, fill=c, outline=(255, 255, 255))
                    for i, rc in enumerate([(255, 90, 90), (90, 255, 120), (90, 150, 255)]):
                        a = sp * 2 + i * 2.094
                        d.ellipse([x + math.cos(a) * 15 - 2, y + math.sin(a) * 15 - 2,
                                   x + math.cos(a) * 15 + 2, y + math.sin(a) * 15 + 2], fill=rc)
                else:
                    d.line([(x, y - 14), (x, y - 9)], fill=(90, 70, 50), width=2)
                    d.rectangle([x - 6, y - 9, x + 6, y + 7], fill=(70, 50, 30))
                    d.rectangle([x - 4, y - 7, x + 4, y + 5], fill=c)
                    d.ellipse([x - 2, y - 3, x + 2, y + 2], fill=(255, 245, 200))
                d.text((x - 3 * len(p["name"]), y + 12), p["name"] + (" (you)" if mine else ""), fill=(220, 220, 230))
                if p["chat"]:
                    tw = 6 * len(p["chat"]) + 10
                    d.rounded_rectangle([x - tw / 2, y - 42, x + tw / 2, y - 24], 6, fill=(30, 30, 50), outline=c)
                    d.text((x - tw / 2 + 5, y - 38), p["chat"], fill=(240, 240, 240))
        glow = glow.filter(ImageFilter.GaussianBlur(12))
        im = ImageChops.add(im, glow)
        d = ImageDraw.Draw(im)
        ok = self.net.connected and st is not None
        d.rounded_rectangle([W - 134, 8, W - 8, 30], 8, fill=(20, 70, 40) if ok else (90, 30, 30))
        d.ellipse([W - 126, 14, W - 116, 24], fill=(80, 255, 120) if ok else (255, 90, 90))
        d.text((W - 110, 13), "LAN Connected" if ok else "Connecting...", fill=(240, 255, 240))
        d.text((10, 10), "Night Garden   blooms: %d" % (st["blooms"] if st else 0), fill=(230, 230, 200))
        if self.typing is not None:
            d.rounded_rectangle([200, H - 60, W - 200, H - 30], 8, fill=(25, 25, 45), outline=(255, 190, 90))
            d.text((210, H - 52), "say: " + self.typing + ("|" if int(t * 2) % 2 else ""), fill=(255, 240, 210))
        d.text((10, H - 18), "T: type a note   Arrows/WASD or click: move   Space/right-click: plant   1-4: say hi   "
               "Bloom needs BOTH lights near!", fill=(170, 180, 200))
        pb = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(im.tobytes()), GdkPixbuf.Colorspace.RGB,
                                             False, 8, W, H, W * 3)
        self.img.set_from_pixbuf(pb)


if __name__ == "__main__":
    App()
    Gtk.main()
