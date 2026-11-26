#!/usr/bin/env python3
"""The Afterlight Garden — GTK3 LAN client. Wick (amber lantern) & Mote (teal sprite)."""
import os, sys, json, socket, threading, math, time
from functools import lru_cache
from random import Random
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from PIL import Image, ImageDraw, ImageFont

GRID_W, GRID_H = 20, 12
CANVAS_W, CANVAS_H = 854, 360
LEGEND = [
    ("WICK", "The moon kept one window lit for a kite that didn't have to come home."),
    ("MOTE", "The kite dropped one blue star in the moon's hand, so wherever it flew, it had already come home once."),
]

def parse_role():
    args = " ".join(sys.argv[1:]).lower()
    if "wick" in args or "p1" in args:
        return "wick"
    return "mote"  # p2 default

ROLE = parse_role()
OTHER = "wick" if ROLE == "mote" else "mote"

@lru_cache(maxsize=16)
def font(sz):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()

class State:
    def __init__(self):
        self.players = {}
        self.marks = []
        self.event = "Welcome to The Afterlight Garden — move, place your mark, meet at the heart!"
        self.bloom = False
        self.tended = []
        self.version = 0
        self.revision = 0
        self.connected = False
        self.tended = []
        self.lock = threading.Lock()
    def apply(self, msg):
        with self.lock:
            self.version += 1
            if isinstance(msg.get("players"), dict):
                self.players = msg["players"]
                self.connected = ROLE in self.players
            if isinstance(msg.get("marks"), list):
                self.marks = msg["marks"]
            if msg.get("event"):
                self.event = str(msg["event"])[:180]
            if "bloom" in msg:
                self.bloom = bool(msg["bloom"])
            if isinstance(msg.get("tended"), list):
                self.tended = [str(x) for x in msg["tended"]]
            if "revision" in msg:
                try: self.revision = int(msg["revision"])
                except Exception: pass
            if "tended" in msg:
                self.tended = msg["tended"]
            # tolerate alternate keys
            if msg.get("message"):
                self.event = str(msg["message"])[:180]

state = State()
sock_ref = {"sock": None}

def send_msg(obj):
    s = sock_ref["sock"]
    if s and state.connected:
        try:
            s.sendall((json.dumps(obj) + "\n").encode("utf-8"))
            return True
        except Exception:
            pass
    return False

def net_thread():
    while True:
        try:
            with socket.create_connection(
                (os.environ.get("AAL_LAN_HOST", "localhost"), int(os.environ.get("AAL_LAN_PORT", "18765"))), timeout=5
            ) as s:
                s.settimeout(1)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock_ref["sock"] = s
                s.sendall((json.dumps({"type": "join", "role": ROLE}) + "\n").encode())
                buf = b""
                while True:
                    try:
                        data = s.recv(8192)
                    except TimeoutError:
                        continue
                    if not data:
                        break
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if line.strip():
                            state.apply(json.loads(line))
                    if len(buf) > 128_000:
                        break
        except (OSError, KeyError, ValueError):
            pass
        sock_ref["sock"] = None
        with state.lock:
            state.connected = False
            state.players = {}
            state.version += 1
        time.sleep(2)

def cell_cx(x): return int((x + 0.5) * CANVAS_W / GRID_W)
def cell_cy(y): return int(30 + (y + 0.5) * (CANVAS_H - 30) / GRID_H)


@lru_cache(maxsize=1)
def backdrop():
    img = Image.new("RGB", (CANVAS_W, CANVAS_H))
    d = ImageDraw.Draw(img, "RGBA")
    rng = Random(782)
    for y in range(CANVAS_H):
        t = y / CANVAS_H
        d.line((0, y, CANVAS_W, y), fill=(14 + int(23*t), 22 + int(11*t), 48 + int(29*t)))
    for _ in range(120):
        x, y = rng.randrange(CANVAS_W), rng.randrange(30, CANVAS_H)
        d.point((x, y), fill=(170, 189, 255, rng.randrange(35, 155)))
    for x, y, w, h in [(90, 150, 260, 20), (740, 146, 210, 15), (450, 289, 700, 12), (799, 311, 420, 20)]:
        d.ellipse((x-w//2, y-h//2, x+w//2, y+h//2), fill=(135, 115, 215, 19))
    d.ellipse((684, 45, 739, 100), fill=(248, 208, 167))
    d.ellipse((696, 42, 746, 91), fill=(19, 24, 54))
    for x, y, w, h, grass, rock in [
        (170, 196, 145, 69, (54, 112, 88), (61, 52, 94)),
        (439, 208, 116, 72, (71, 121, 99), (77, 54, 103)),
        (672, 192, 142, 64, (44, 101, 99), (51, 48, 91)),
    ]:
        rim = [(x+int(w*math.cos(i*math.tau/14)*(0.9+rng.random()*.13)),
                y+int(h*math.sin(i*math.tau/14)*(0.9+rng.random()*.13))) for i in range(14)]
        d.polygon(rim[:8]+[(x-w//4, y+h+31), (x+w//8, y+h+45), (x+w//2, y+h+23)], fill=rock)
        d.polygon(rim, fill=grass, outline=(119, 165, 143))
        for _ in range(155):
            a, r = rng.random()*math.tau, rng.random()**.5*.81
            xx, yy = int(x+w*r*math.cos(a)), int(y+h*r*math.sin(a))
            d.line((xx, yy, xx+2, yy-2), fill=(189, 222, 161, rng.randrange(25, 100)))
    for gy in range(GRID_H):
        for gx in range(GRID_W):
            x, y = cell_cx(gx), cell_cy(gy)
            d.line((x-3, y+6, x+3, y+6), fill=(201, 235, 219, 63))
    for x, y, label in [(135, 118, "WEST TERRACE"), (446, 109, "HEARTSEED"), (678, 117, "EAST TERRACE")]:
        d.text((x, y), label, font=font(10), fill=(197, 198, 230), anchor="mm", stroke_width=2, stroke_fill=(18, 22, 48))
    return img


def render(players, marks, bloom, connected, legend):
    img = backdrop().copy()
    d = ImageDraw.Draw(img, "RGBA")
    # heart at (10,6)
    hx, hy = cell_cx(10), cell_cy(6)
    if bloom:
        for r, alpha in [(58, 17), (49, 31), (39, 58)]:
            d.ellipse((hx-r, hy-r, hx+r, hy+r), fill=(255, 134, 211, alpha), outline=(255, 197, 225, alpha*3))
        for i in range(8):
            x, y = hx+int(21*math.cos(i*math.tau/8)), hy+int(21*math.sin(i*math.tau/8))
            d.ellipse((x-10, y-10, x+10, y+10), fill=(255, 149, 210), outline=(255, 212, 232))
        d.ellipse((hx-9, hy-9, hx+9, hy+9), fill=(255, 236, 169))
    else:
        d.ellipse([hx - 12, hy - 12, hx + 12, hy + 12], outline=(255, 160, 200), width=3)
        d.text((hx, hy), "♥", font=font(16), fill=(255, 160, 200), anchor="mm")
    # marks
    for m in marks:
        try:
            mx, my, mr = int(m.get("x", 0)), int(m.get("y", 0)), str(m.get("role", ""))
        except Exception:
            continue
        cx, cy = cell_cx(mx), cell_cy(my)
        if mr == "wick":
            d.ellipse([cx - 13, cy - 13, cx + 13, cy + 13], fill=(255, 180, 50, 110))
            d.rectangle([cx - 6, cy - 9, cx + 6, cy + 9], fill=(255, 200, 80), outline=(150, 90, 20), width=2)
            d.ellipse([cx - 3, cy - 4, cx + 3, cy + 4], fill=(255, 250, 200))
        else:
            # starflower
            for a in range(5):
                ang = a * 2 * math.pi / 5 - math.pi / 2
                px, py = cx + int(11 * math.cos(ang)), cy + int(11 * math.sin(ang))
                d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(90, 220, 255))
            d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(255, 255, 200))
    # players
    def draw_wick(cx, cy):
        d.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill=(255, 170, 40, 90))
        d.rounded_rectangle([cx - 11, cy - 15, cx + 11, cy + 12], radius=5, fill=(255, 190, 70), outline=(130, 70, 10), width=3)
        d.ellipse([cx - 5, cy - 7, cx + 5, cy + 6], fill=(255, 245, 180))
        d.line([(cx - 6, cy + 12), (cx - 8, cy + 19)], fill=(80, 50, 20), width=3)
        d.line([(cx + 6, cy + 12), (cx + 8, cy + 19)], fill=(80, 50, 20), width=3)
    def draw_mote(cx, cy):
        d.ellipse([cx - 19, cy - 19, cx + 19, cy + 19], fill=(60, 200, 255, 80))
        d.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], fill=(80, 225, 255), outline=(20, 120, 170), width=3)
        d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(255, 255, 255))
        d.polygon([(cx - 11, cy - 2), (cx - 20, cy - 10), (cx - 9, cy - 11)], fill=(170, 240, 255))
        d.polygon([(cx + 11, cy - 2), (cx + 20, cy - 10), (cx + 9, cy - 11)], fill=(170, 240, 255))
    w, mo = players.get("wick"), players.get("mote")
    shared = w is not None and w == mo
    avatars = []
    if w:
        x, y = cell_cx(w["x"]) - 13 * shared, cell_cy(w["y"])
        draw_wick(x, y)
        avatars.append((x, y, "Wick", (255, 230, 160)))
    if mo:
        x, y = cell_cx(mo["x"]) + 13 * shared, cell_cy(mo["y"])
        draw_mote(x, y)
        avatars.append((x, y, "Mote", (180, 240, 255)))
    reserved = [(x-19, y-19, x+19, y+19) for x, y, _, _ in avatars]
    if legend:
        reserved.append((29, 272, CANVAS_W-29, 350))
    name_font = font(12)
    for x, y, name, color in avatars:
        label = name + (" • YOU" if name.lower() == ROLE else "")
        width = int(d.textlength(label, font=name_font)) + 12
        for ox, oy in [(0, -30), (0, 30), (-width//2-19, 0), (width//2+19, 0), (0, -50), (0, 50)]:
            cx = min(CANVAS_W-3-width//2, max(3+width//2, x+ox))
            cy = y+oy
            box = (cx-width//2, cy-9, cx+width//2, cy+9)
            if box[1] < 30 or box[3] >= CANVAS_H:
                continue
            if any(box[0] <= b[2] and b[0] <= box[2] and box[1] <= b[3] and b[1] <= box[3] for b in reserved):
                continue
            d.rounded_rectangle(box, radius=7, fill=(13, 18, 36, 220))
            d.text((cx, cy), label, font=name_font, fill=color, anchor="mm")
            reserved.append(box)
            break
    if legend:
        d.rounded_rectangle((29, 272, CANVAS_W-29, 350), radius=12, fill=(12, 16, 34, 247), outline=(145, 133, 194))
        d.text((CANVAS_W//2, 287), "A LEGEND UNDER THE HEARTSEED", font=font(11), fill=(226, 210, 247), anchor="mm")
        for i, (speaker, line) in enumerate(LEGEND):
            y = 310 + i*21
            color = (255, 216, 143) if speaker == "WICK" else (157, 239, 255)
            d.text((48, y), speaker, font=font(11), fill=color, anchor="lm")
            d.text((101, y), line, font=font(12), fill=(240, 239, 250), anchor="lm")
    # title bar
    d.rectangle([0, 0, CANVAS_W, 29], fill=(10, 14, 35))
    d.text((13, 14), "THE AFTERLIGHT GARDEN", font=font(14), fill=(245, 235, 255), anchor="lm")
    if bloom:
        d.text((CANVAS_W//2, 14), "✦  HEARTSEED IN BLOOM  ✦", font=font(12), fill=(255, 190, 224), anchor="mm")
    badge = "LAN Connected" if connected else "Connecting..."
    col = (90, 255, 140) if connected else (255, 200, 90)
    d.rounded_rectangle((CANVAS_W-130, 4, CANVAS_W-10, 25), radius=10, fill=(27, 51, 48) if connected else (57, 43, 38))
    d.text((CANVAS_W - 70, 14), badge, font=font(12), fill=col, anchor="mm")
    return img

def img_to_pixbuf(img):
    data = img.tobytes()
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(data), GdkPixbuf.Colorspace.RGB, False, 8, img.width, img.height, img.width * 3)

class App:
    def __init__(self):
        self.win = Gtk.Window(title="The Afterlight Garden")
        self.win.set_default_size(854, 480)
        self.win.set_resizable(False)
        self.win.set_decorated(False)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.win.connect("destroy", Gtk.main_quit)
        self.win.connect("key-press-event", self.on_key)
        css = Gtk.CssProvider()
        css.load_from_data(b"""
        window { background: #10162e; }
        label { color: #ecedff; }
        button { background: #263455; color: #fbf1ff; border: 1px solid #566187;
                 box-shadow: none; text-shadow: none; border-radius: 7px; }
        button:hover { background: #3d5077; }
        button:active { background: #596a93; }
        """)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.version = -1
        self.legend = False
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.win.add(vbox)
        self.image = Gtk.Image()
        eb = Gtk.EventBox()
        eb.add(self.image)
        eb.connect("button-press-event", self.on_click)
        vbox.pack_start(eb, False, False, 0)
        me = "Mote (teal sprite)" if ROLE == "mote" else "Wick (amber lantern)"
        self.hud = Gtk.Label(label=f"You are {me}  •  Arrows/WASD move  •  Space/P: Place  •  G: Signal  •  T: Tend  •  L: Legend")
        vbox.pack_start(self.hud, False, False, 0)
        self.event_label = Gtk.Label(label="Welcome!")
        self.event_label.set_line_wrap(True)
        vbox.pack_start(self.event_label, False, False, 0)
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        hbox.set_margin_start(12)
        hbox.set_margin_end(12)
        vbox.pack_start(hbox, False, False, 0)
        for label, fn in [("◀ Left", lambda _: self.move(-1, 0)), ("▲ Up", lambda _: self.move(0, -1)),
                          ("▼ Down", lambda _: self.move(0, 1)), ("▶ Right", lambda _: self.move(1, 0)),
                          ("✿ Place", lambda _: self.act("place")), ("◎ Signal", lambda _: self.act("signal")),
                           ("♥ Tend", lambda _: self.act("tend")), ("✦ Legend", lambda _: self.toggle_legend())]:
            b = Gtk.Button(label=label)
            b.connect("clicked", fn)
            b.set_focus_on_click(False)
            hbox.pack_start(b, True, True, 0)
        self.win.show_all()
        self.win.grab_focus()
        GLib.timeout_add(75, self.refresh)
        self.refresh()
    def refresh(self):
        try:
            with state.lock:
                if self.version == state.version:
                    return True
                self.version = state.version
                players, marks = state.players, state.marks
                ev, bloom, connected = state.event, state.bloom, state.connected
                tended = len(state.tended)
            self.image.set_from_pixbuf(img_to_pixbuf(render(players, marks, bloom, connected, self.legend)))
            heart = "Heartseed BLOOMED!" if bloom else f"Care: {tended}/2"
            self.event_label.set_text(f"Gardeners: {len(players)}/2  •  Marks: {len(marks)}  •  {heart}\n{ev}")
        except Exception:
            self.event_label.set_text("The garden could not redraw.")
        return True
    def move(self, dx, dy):
        send_msg({"type": "move", "dx": dx, "dy": dy})
    def act(self, kind):
        send_msg({"type": kind})
    def toggle_legend(self):
        self.legend = not self.legend
        self.version = -1
        self.refresh()
    def on_click(self, _w, ev):
        if ev.y < 30 or ev.button != 1:
            return False
        if self.legend and ev.y >= 272:
            return True
        # click a cell: move one step toward it
        gx = int(ev.x * GRID_W / CANVAS_W); gy = int((ev.y - 30) * GRID_H / (CANVAS_H - 30))
        with state.lock:
            p = state.players.get(ROLE)
        if p is None:
            return False
        dx = (gx > p["x"]) - (gx < p["x"]); dy = (gy > p["y"]) - (gy < p["y"])
        if dx or dy:
            self.move(dx, dy)
        else:
            self.act("place")
    def on_key(self, _w, ev):
        k = Gdk.keyval_name(ev.keyval) or ""
        kl = k.lower()
        m = {"left": (-1, 0), "a": (-1, 0), "right": (1, 0), "d": (1, 0),
             "up": (0, -1), "w": (0, -1), "down": (0, 1), "s": (0, 1)}
        if kl in m:
            self.move(*m[kl]); return True
        if kl in ("space", "p", "return"):
            self.act("place"); return True
        if kl == "g":
            self.act("signal"); return True
        if kl == "t":
            self.act("tend"); return True
        if kl == "l":
            self.toggle_legend(); return True
        return False

if __name__ == "__main__":
    threading.Thread(target=net_thread, daemon=True).start()
    App()
    Gtk.main()
