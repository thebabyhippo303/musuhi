#!/usr/bin/env python3
"""Afterlight - floating night garden. GTK3 LAN client, 854x480."""
import argparse, json, os, socket, threading, time, random, math
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from PIL import Image, ImageDraw, ImageFont

W, H = 854, 480
WORLD = (24, 92, 830, 380)  # left, top, right, bottom (absolute image coords)
random.seed(42)
STARS = [(random.randint(WORLD[0]+4, WORLD[2]-4), random.randint(WORLD[1]+4, WORLD[3]-4), random.randint(1,2)) for _ in range(90)]

def font(sz, bold=False):
    names = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for n in names:
        try:
            return ImageFont.truetype(n, sz)
        except Exception:
            pass
    return ImageFont.load_default()

F_TITLE, F_HUD, F_SMALL, F_BTN, F_NAME = font(20, True), font(13), font(11), font(14, True), font(12, True)

# Button rects: (left, top, right, bottom, label, action)
BUTTONS = [
    (24, 396, 84, 436, "< Left", ("move", -1, 0)),
    (92, 396, 152, 436, "^ Up", ("move", 0, -1)),
    (160, 396, 220, 436, "v Down", ("move", 0, 1)),
    (228, 396, 288, 436, "Right >", ("move", 1, 0)),
    (340, 396, 480, 436, "Tend  [Space]", ("tend",)),
    (492, 396, 632, 436, "Weave  [E]", ("weave",)),
    (644, 396, 784, 436, "Wave  [Q]", ("wave",)),
]

def default_state():
    return {
        "type": "state",
        "players": {
            "1": {"name": "Lumen", "x": 350, "y": 236, "online": False, "waves": 0},
            "2": {"name": "Vela", "x": 504, "y": 236, "online": False, "waves": 0},
        },
        "islands": [
            {"id": 1, "name": "Heart Isle", "x": 427, "y": 236, "rx": 130, "ry": 62, "lantern": False, "bloom": False, "woven": False},
            {"id": 2, "name": "Fern Drift", "x": 150, "y": 150, "rx": 80, "ry": 38, "lantern": False, "bloom": False, "woven": False},
            {"id": 3, "name": "Petal Rock", "x": 700, "y": 150, "rx": 80, "ry": 38, "lantern": False, "bloom": False, "woven": False},
            {"id": 4, "name": "Moss Hollow", "x": 160, "y": 325, "rx": 85, "ry": 38, "lantern": False, "bloom": False, "woven": False},
            {"id": 5, "name": "Star Terrace", "x": 690, "y": 325, "rx": 85, "ry": 38, "lantern": False, "bloom": False, "woven": False},
            {"id": 6, "name": "High Perch", "x": 427, "y": 128, "rx": 75, "ry": 30, "lantern": False, "bloom": False, "woven": False},
        ],
        "message": "Welcome to Afterlight. Move with arrows / WASD or click the garden.",
        "revision": 0,
    }

class Net:
    def __init__(self, seat):
        self.seat = seat
        self.sock = None
        self.connected = False
        self.lock = threading.Lock()
        self.state = default_state()
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        try:
            host = os.environ.get("AAL_LAN_HOST", "localhost")
        except KeyError:
            host = ""
        port = int(os.environ.get("AAL_LAN_PORT", "18765"))
        while self.running:
            if not host:
                time.sleep(1.0)
                continue
            try:
                s = socket.create_connection((host, port), timeout=5)
                s.settimeout(None)
                with self.lock:
                    self.sock = s
                self.connected = False
                self.send({"type": "join", "seat": self.seat})
                buf = b""
                while self.running:
                    data = s.recv(65536)
                    if not data:
                        break
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line.decode("utf-8"))
                        except Exception:
                            continue
                        if msg.get("type") == "state":
                            with self.lock:
                                self.state = msg
                            self.connected = True
            except Exception:
                pass
            self.connected = False
            with self.lock:
                self.sock = None
            time.sleep(1.5)

    def send(self, obj):
        with self.lock:
            s = self.sock
        if s is None:
            return False
        try:
            s.sendall((json.dumps(obj) + "\n").encode("utf-8"))
            return True
        except Exception:
            return False

    def get_state(self):
        with self.lock:
            return self.state


def draw_world(state, connected, seat, trails, wave_until):
    img = Image.new("RGB", (W, H), (16, 14, 38))
    d = ImageDraw.Draw(img, "RGBA")
    # sky gradient bands
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(14 + 18 * t), int(12 + 10 * t), int(42 - 12 * t)))
    # header
    d.text((24, 10), "Afterlight", font=F_TITLE, fill=(255, 225, 150))
    d.text((170, 16), "Floating Night Garden", font=F_HUD, fill=(190, 200, 255))
    badge = "LAN Connected" if connected else "Connecting..."
    bc = (40, 180, 110) if connected else (200, 140, 40)
    d.rounded_rectangle([680, 10, 830, 38], radius=14, fill=bc)
    tw = d.textlength(badge, font=F_HUD)
    d.text((755 - tw / 2, 17), badge, font=F_HUD, fill=(255, 255, 255))
    players = state.get("players", {})
    p1 = players.get("1", {}) if isinstance(players, dict) else {}
    p2 = players.get("2", {}) if isinstance(players, dict) else {}
    islands = state.get("islands", [])
    woven = sum(1 for i in islands if i.get("woven"))
    you = "Lumen (amber lantern)" if seat == 1 else "Vela (teal comet)"
    hud = f"You: {you}   |   Lumen: {'here' if p1.get('online') else 'away'}   Vela: {'here' if p2.get('online') else 'away'}   |   Islands woven: {woven}/{len(islands)}"
    d.text((24, 44), hud, font=F_SMALL, fill=(220, 225, 255))
    msg = str(state.get("message", ""))[:118]
    d.rounded_rectangle([24, 64, 830, 86], radius=8, fill=(255, 255, 255, 28), outline=(255, 255, 255, 60))
    d.text((34, 69), msg, font=F_SMALL, fill=(255, 240, 200))
    # world panel
    d.rounded_rectangle([WORLD[0]-2, WORLD[1]-2, WORLD[2]+2, WORLD[3]+2], radius=14, fill=(24, 28, 66), outline=(120, 130, 220), width=2)
    for (sx, sy, sr) in STARS:
        d.ellipse([sx-sr, sy-sr, sx+sr, sy+sr], fill=(255, 255, 230, 170))
    # islands: x,y are centres, rx,ry radii
    for isl in islands:
        cx, cy = int(isl.get("x", 427)), int(isl.get("y", 236))
        rx, ry = int(isl.get("rx", 70)), int(isl.get("ry", 32))
        lantern, bloom, woven_i = bool(isl.get("lantern")), bool(isl.get("bloom")), bool(isl.get("woven"))
        if woven_i:
            # aurora glow
            for k in range(5, 0, -1):
                d.ellipse([cx-rx-k*5, cy-ry-k*4, cx+rx+k*5, cy+ry+k*4], outline=(90, 255, 200, 45), width=4)
            base = (62, 140, 110)
        elif lantern or bloom:
            base = (78, 110, 92)
        else:
            base = (58, 62, 96)
        d.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=base, outline=(170, 210, 190), width=2)
        d.ellipse([cx-rx+10, cy-ry+6, cx+rx-10, cy+ry-14], fill=(base[0]+22, base[1]+24, base[2]+18))
        name = str(isl.get("name", ""))
        nw = d.textlength(name, font=F_SMALL)
        d.text((cx-nw/2, cy+ry-16), name, font=F_SMALL, fill=(240, 245, 255))
        # markers: lantern (amber dot left), bloom (teal flower right)
        if lantern:
            lx, ly = cx-rx+26, cy-6
            d.ellipse([lx-13, ly-13, lx+13, ly+13], fill=(255, 190, 60, 90))
            d.rectangle([lx-6, ly-8, lx+6, ly+8], fill=(255, 200, 80), outline=(120, 70, 0))
        if bloom:
            bx, by = cx+rx-26, cy-6
            for a in range(0, 360, 60):
                px = bx + int(9*math.cos(math.radians(a))); py = by + int(9*math.sin(math.radians(a)))
                d.ellipse([px-5, py-5, px+5, py+5], fill=(120, 240, 230))
            d.ellipse([bx-4, by-4, bx+4, by+4], fill=(255, 255, 200))
        if woven_i:
            d.arc([cx-rx+14, cy-ry-16, cx+rx-14, cy+ry-2], start=180, end=360, fill=(150, 255, 220), width=3)
    # comet trail for Vela
    for i, (tx, ty) in enumerate(trails.get("2", [])):
        r = 3 + i
        d.ellipse([tx-r, ty-r, tx+r, ty+r], fill=(80, 220, 215, 70+i*18))
    # characters
    now = time.time()
    for key, p in (("1", p1), ("2", p2)):
        if not p:
            continue
        x, y = int(p.get("x", 427)), int(p.get("y", 236))
        name = str(p.get("name", "Lumen" if key == "1" else "Vela"))
        waving = now < wave_until.get(key, 0)
        if key == "1":
            # Lumen: amber square glass head + too-big midnight coat
            d.ellipse([x-24, y-30, x+24, y+18], fill=(255, 180, 60, 70))
            d.polygon([(x-16, y+4), (x+16, y+4), (x+20, y+28), (x-20, y+28)], fill=(28, 32, 72), outline=(140, 150, 230))
            d.rectangle([x-11, y-22, x+11, y+4], fill=(255, 205, 90), outline=(130, 80, 10), width=2)
            d.ellipse([x-4, y-13, x+4, y-4], fill=(255, 245, 180))
            d.line([(x-11, y-22), (x+11, y-22)], fill=(80, 50, 10), width=3)
        else:
            # Vela: teal comet with tail to the left
            d.polygon([(x-6, y-9), (x-34, y-3), (x-6, y+9)], fill=(70, 210, 205))
            d.polygon([(x-6, y-5), (x-26, y), (x-6, y+5)], fill=(160, 250, 245))
            d.ellipse([x-14, y-14, x+14, y+14], fill=(60, 225, 215), outline=(220, 255, 250), width=2)
            d.ellipse([x-6, y-8, x+2, y], fill=(220, 255, 250))
            d.ellipse([x+3, y-3, x+7, y+1], fill=(20, 40, 50))
        if waving:
            d.arc([x+10, y-30, x+30, y-10], start=300, end=80, fill=(255, 255, 255), width=3)
            d.text((x+16, y-38), "hi!", font=F_SMALL, fill=(255, 255, 255))
        nw = d.textlength(name, font=F_NAME)
        d.rounded_rectangle([x-nw/2-6, y+30, x+nw/2+6, y+48], radius=7, fill=(0, 0, 0, 130))
        d.text((x-nw/2, y+32), name, font=F_NAME, fill=(255, 255, 255))
    # buttons
    for (l, t, r, b, label, _act) in BUTTONS:
        d.rounded_rectangle([l, t, r, b], radius=10, fill=(52, 58, 120), outline=(170, 180, 255), width=2)
        tw = d.textlength(label, font=F_BTN if r-l > 80 else F_SMALL)
        d.text(((l+r)/2-tw/2, t+12), label, font=(F_BTN if r-l > 80 else F_SMALL), fill=(255, 255, 255))
    d.text((24, 444), "Arrows / WASD move  •  Click garden to go there  •  Space = Tend your half  •  E = Weave together  •  Q = Wave", font=F_SMALL, fill=(190, 200, 235))
    d.text((24, 460), "Tend: Lumen plants a lantern, Vela wakes a starbloom. Stand close on a tended island, then Weave an aurora.", font=F_SMALL, fill=(160, 170, 210))
    return img



def to_pixbuf(img):
    data = img.tobytes()
    return GdkPixbuf.Pixbuf.new_from_data(data, GdkPixbuf.Colorspace.RGB, False, 8, W, H, W * 3)


class App:
    def __init__(self, seat):
        self.seat = seat
        self.net = Net(seat)
        self.trails = {"2": []}
        self.last_pos = {}
        self.last_waves = {"1": 0, "2": 0}
        self.wave_until = {}
        self.win = Gtk.Window(title="Afterlight — Floating Night Garden")
        self.win.set_default_size(854, 480)
        self.win.set_resizable(False)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.win.set_decorated(False)
        self.win.connect("destroy", Gtk.main_quit)
        self.win.connect("key-press-event", self.on_key)
        self.image = Gtk.Image()
        self.ebox = Gtk.EventBox()
        self.ebox.add(self.image)
        self.ebox.connect("button-press-event", self.on_click)
        self.win.add(self.ebox)
        self.win.show_all()
        GLib.timeout_add(120, self.tick)
        self.tick()

    def do_action(self, act):
        if not act:
            return
        if act[0] == "move":
            self.net.send({"type": "move", "dx": act[1], "dy": act[2]})
        elif act[0] in ("tend", "weave", "wave"):
            self.net.send({"type": act[0]})

    def on_click(self, _w, ev):
        x, y = int(ev.x), int(ev.y)
        for (l, t, r, b, _label, act) in BUTTONS:
            if l <= x <= r and t <= y <= b:
                self.do_action(act)
                return True
        if WORLD[0] <= x <= WORLD[2] and WORLD[1] <= y <= WORLD[3]:
            self.net.send({"type": "goto", "x": x, "y": y})
            return True
        return False

    def on_key(self, _w, ev):
        k = Gdk.keyval_name(ev.keyval) or ""
        low = k.lower()
        m = {
            "left": ("move", -1, 0), "a": ("move", -1, 0),
            "right": ("move", 1, 0), "d": ("move", 1, 0),
            "up": ("move", 0, -1), "w": ("move", 0, -1),
            "down": ("move", 0, 1), "s": ("move", 0, 1),
            "space": ("tend",), "e": ("weave",), "q": ("wave",),
        }
        act = m.get(low)
        if act:
            self.do_action(act)
            return True
        return False

    def tick(self):
        state = self.net.get_state()
        players = state.get("players", {}) if isinstance(state, dict) else {}
        # trails + wave detection
        for key in ("1", "2"):
            p = players.get(key, {}) if isinstance(players, dict) else {}
            if not p:
                continue
            pos = (int(p.get("x", 0)), int(p.get("y", 0)))
            if key == "2" and self.last_pos.get(key) not in (None, pos):
                self.trails["2"].append(self.last_pos[key])
                self.trails["2"] = self.trails["2"][-7:]
            self.last_pos[key] = pos
            wv = int(p.get("waves", 0) or 0)
            if wv != self.last_waves.get(key, 0):
                self.wave_until[key] = time.time() + 1.8
                self.last_waves[key] = wv
        img = draw_world(state, self.net.connected, self.seat, self.trails, self.wave_until)
        self.image.set_from_pixbuf(to_pixbuf(img))
        return True


def parse_seat():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seat", type=int, default=None)
    ap.add_argument("--side", type=str, default=None)
    a = ap.parse_args()
    if a.seat in (1, 2):
        return a.seat
    if a.side:
        return 2 if str(a.side).lower() in ("p2", "2", "vela") else 1
    env = os.environ.get("AAL_SEAT", "")
    return 2 if env in ("2", "p2") else 1


if __name__ == "__main__":
    App(parse_seat())
    Gtk.main()
