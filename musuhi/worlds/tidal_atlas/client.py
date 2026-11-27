"""Night Tidal Atlas • shared field instrument for two surveyors."""
import argparse
import json
import os
import queue
import random
import socket
import string
import threading
import time
from collections import deque

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from PIL import Image, ImageDraw, ImageFont


W, H = 854, 480
X, Y, CW, CH = 40, 77, 33, 23
SEA, INK, PAPER, MUTED = "#101f30", "#122332", "#f0ebd9", "#acbfbd"
GOLD, TEAL = "#ffc469", "#73ebcd"
BUTTONS = [("G", "Plant"), ("N", "Bury note"), ("L", "Light"), ("T", "Radio"), ("J", "Journal")]


def font(file, size):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVu" + file + ".ttf", size)
    except OSError:
        return ImageFont.load_default()


F = {s: font("Sans", s) for s in (10, 11, 12, 13, 14)}
FM = font("SansMono", 10)
FT = font("Serif", 26)


class Link:
    def __init__(self, side):
        self.side = side
        self.messages = queue.Queue()
        self.sock = None
        self.stop = threading.Event()
        self.out_lock = threading.Lock()
        threading.Thread(target=self.run, daemon=True).start()

    def send(self, kind, **fields):
        with self.out_lock:
            if self.sock:
                try:
                    self.sock.sendall((json.dumps(dict(t=kind, **fields)) + "\n").encode())
                except OSError:
                    pass

    def run(self):
        while not self.stop.is_set():
            try:
                with socket.create_connection((os.environ["AAL_LAN_HOST"], int(os.environ.get("AAL_LAN_PORT", "18765"))), timeout=3) as s:
                    s.settimeout(None)
                    self.sock = s
                    amber = self.side == "p2"
                    self.send("hello", name="Amber" if amber else "Teal", color="amber" if amber else "teal")
                    with s.makefile("rb") as inp:
                        for line in inp:
                            self.messages.put(json.loads(line))
            except (ValueError, KeyError, OSError):
                pass
            finally:
                self.sock = None
                self.messages.put({"t": "offline"})
            self.stop.wait(1.5)


def tile_center(x, y):
    return X + x * CW + CW // 2, Y + y * CH + CH // 2


def terrain(elev):
    """Spline-sampled plate with fine soundings; survey grid remains exact."""
    h, w = len(elev), len(elev[0])
    size = w*CW, h*CH
    field = Image.new("L", (w, h))
    field.putdata([min(255, int(v)*85) for row in elev for v in row])
    field = field.resize(size, Image.Resampling.BICUBIC if hasattr(Image, "Resampling") else Image.BICUBIC)
    colors = [
        (0, (23, 51, 69)), (14, (28, 61, 77)), (38, (35, 75, 85)),
        (52, (47, 87, 93)), (59, (119, 157, 148)), (65, (72, 106, 99)),
        (104, (76, 115, 100)), (127, (95, 135, 110)), (139, (79, 114, 95)),
        (174, (84, 124, 98)), (194, (111, 148, 112)), (203, (87, 123, 100)),
        (235, (100, 137, 109)), (251, (111, 145, 113)),
    ]
    lut = [next(c for k,c in reversed(colors) if v >= k) for v in range(256)]
    plate = Image.merge("RGB", tuple(field.point([c[n] for c in lut]) for n in range(3)))
    d = ImageDraw.Draw(plate)
    rng = random.Random(181)
    for i in range(1200):
        px, py = rng.randrange(size[0]), rng.randrange(size[1])
        if field.getpixel((px, py)) < 55:
            d.line([(px-2,py),(px+1,py),(px+3,py-1)], fill="#31596b")
        else:
            d.line([(px,py), (px+1, py-rng.randrange(1,4))], fill="#829e81")
    for x in range(1,w):
        for y in range(1,h):
            px, py = x*CW, y*CH
            d.line((px-1,py,px+1,py),fill="#78958f")
    return plate


class Atlas:
    def __init__(self, side):
        self.side = side
        self.link = Link(side)
        win = self.win = Gtk.Window(title="Night Tidal Atlas • " + ("Amber" if side == "p2" else "Teal"))
        win.set_default_size(854, 480)
        win.set_resizable(False)
        win.set_position(Gtk.WindowPosition.CENTER)
        win.set_decorated(False)
        self.image = Gtk.Image()
        self.box = Gtk.EventBox()
        self.box.add(self.image)
        win.add(self.box)
        self.box.connect("button-press-event", self.click)
        win.connect("key-press-event", self.key)
        win.connect("destroy", self.close)
        self.pid = None
        self.state = {}
        self.elev = []
        self.plate = None
        self.connected = False
        self.mode = None
        self.buffer = ""
        self.target = self.pending = None
        self.hint = ""
        self.hint_until = 0
        self.history = deque(maxlen=80)
        self.prevlog = []
        self.read_notes = set()
        self.scroll = 0
        win.show_all()
        GLib.timeout_add(100, self.refresh)

    def close(self, *_):
        self.link.stop.set()
        Gtk.main_quit()

    def me(self):
        return next((p for p in self.state.get("players", []) if p["id"] == self.pid), None)

    def notify(self, msg):
        self.hint, self.hint_until = msg, time.monotonic() + 3

    def refresh(self):
        while True:
            try:
                m = self.link.messages.get_nowait()
            except queue.Empty:
                break
            kind = m.get("t")
            if kind == "welcome":
                self.pid, self.elev = m["id"], m["elev"]
                self.plate = terrain(self.elev)
                self.connected = True
            elif kind == "state":
                self.state = m
                log = list(m.get("log", []))
                overlap = min(len(log), len(self.prevlog))
                while overlap and self.prevlog[-overlap:] != log[:overlap]:
                    overlap -= 1
                self.history.extend(log[overlap:])
                for n in m.get("notes", []):
                    tile = (n["x"], n["y"])
                    if tile not in self.read_notes:
                        self.read_notes.add(tile)
                        self.history.append(f'{string.ascii_uppercase[tile[0]]}{tile[1]+1} · {n["by"]}: {n["text"]}')
                self.prevlog = log
                self.step()
            elif kind == "offline":
                self.connected = False
                self.target = self.pending = None
            elif kind == "error":
                self.notify(m.get("msg", "Signal not received"))
        self.draw()
        return True

    def step(self):
        p = self.me()
        if not (p and self.target):
            return
        pos = (p["x"], p["y"])
        if pos == self.target:
            self.target = self.pending = None
            return
        if self.pending and pos == self.pending[0]:
            if time.monotonic() - self.pending[1] < 1.4:
                return
            self.target = self.pending = None
            self.notify("Route interrupted. Try the arrow keys.")
            return
        self.pending = None
        queue = deque([pos])
        first = {pos: (0,0)}
        solids = {(l["x"],l["y"]) for l in self.state["lights"]}
        tide = self.state["tide"]
        while queue and self.target not in first:
            ux,uy = queue.popleft()
            wet = int(self.elev[uy][ux]) < tide
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                vx,vy = ux+dx,uy+dy
                if (vx,vy) in first or (vx,vy) in solids or not (0 <= vx < 24 and 0 <= vy < 12):
                    continue
                height = int(self.elev[vy][vx])
                if height == 0 or (not wet and height < tide):
                    continue
                first[vx,vy] = (dx,dy) if (ux,uy)==pos else first[ux,uy]
                queue.append((vx,vy))
        if self.target not in first:
            self.target = None
            self.notify("No crossing here at this tide.")
            return
        dx,dy = first[self.target]
        self.link.send("move", dx=dx, dy=dy)
        self.pending = pos, time.monotonic()

    def action(self, k):
        if k == "J":
            self.mode = None if self.mode == "journal" else "journal"
            self.scroll = 0
        elif k in ("N", "T"):
            self.mode, self.buffer = ("note" if k == "N" else "say"), ""
            self.target = self.pending = None
        elif k in ("G", "L"):
            self.link.send("plant" if k == "G" else "light")
        self.draw()

    def click(self, box, e):
        x,y = int(e.x),int(e.y)
        if self.mode:
            if self.mode == "journal":
                self.mode = None
            return True
        if 383 <= y <= 416 and 15 <= x < 555:
            self.action(BUTTONS[(x-15)//108][0])
        elif X <= x < X+24*CW and Y <= y < Y+12*CH:
            self.target, self.pending = ((x-X)//CW, (y-Y)//CH), None
            self.step()
        return True

    def key(self, win, e):
        k = Gdk.keyval_name(e.keyval)
        if self.mode == "journal":
            if k == "Up":
                self.scroll = min(max(0, len(self.history)-1),self.scroll+1)
            elif k == "Down":
                self.scroll = max(0,self.scroll-1)
            else:
                self.mode = None
        elif self.mode:
            if k == "Escape":
                self.mode = None
            elif k in ("Return","KP_Enter"):
                if self.buffer.strip():
                    self.link.send(self.mode, text=self.buffer.strip())
                self.mode = None
            elif k == "BackSpace":
                self.buffer = self.buffer[:-1]
            else:
                c = Gdk.keyval_to_unicode(e.keyval)
                if c and chr(c).isprintable() and len(self.buffer)<80:
                    self.buffer += chr(c)
        elif k in ("Left","Right","Up","Down","w","a","s","d"):
            self.target = self.pending = None
            dx,dy = {"Left":(-1,0),"Right":(1,0),"Up":(0,-1),"Down":(0,1),
                     "a":(-1,0),"d":(1,0),"w":(0,-1),"s":(0,1)}[k]
            self.link.send("move", dx=dx, dy=dy)
        else:
            self.action(k.upper())
        self.draw()
        return True

    def draw(self):
        im = Image.new("RGB", (W,H), INK)
        d = ImageDraw.Draw(im)
        def text(x,y,s,fill=PAPER,face=F[12]):
            d.text((x,y),str(s),font=face,fill=fill)
        def box(rect,fill,line=None,r=5):
            d.rounded_rectangle(rect,r,fill,line)
        text(18,5,"Night Tidal Atlas",PAPER,FT)
        text(20,40,"FIELD STATION   /   TWO-KEEPER SURVEY",MUTED,FM)
        tide = float(self.state.get("tide",0))
        text(355,10,"TIDE     %0.1f" % tide,TEAL,FM)
        for i in range(15):
            d.rectangle((355+i*6,29,358+i*6,37),fill="#74c7bb" if i<5*tide else "#314958")
        text(478,10,"CHARTED",MUTED,FM)
        text(478,25,str(self.state.get("charted",0))+"%",PAPER,F[14])
        lights = self.state.get("lights",[])
        text(574,10,"BEACONS",MUTED,FM)
        text(574,25,f"{sum(bool(l['lit']) for l in lights)} / {len(lights)}",GOLD,F[14])
        box((693,12,836,40),"#1b3c40","#477d70",13)
        d.ellipse((705,22,712,29),fill=TEAL if self.connected else GOLD)
        text(721,17,"LAN Connected" if self.connected else "Seeking host",PAPER,F[12])
        d.line((18,56,836,56),fill="#385160")
        if self.plate:
            im.paste(self.plate,(X,Y))
        for x in range(24):
            text(tile_center(x,0)[0]-4,60,string.ascii_uppercase[x],MUTED,FM)
        for y in range(12):
            text(18,tile_center(0,y)[1]-6,f"{y+1:02}",MUTED,FM)
        d.rectangle((X-1,Y-1,X+24*CW,Y+12*CH),outline="#698389")
        for row,cells in enumerate(self.elev):
            for col,level in enumerate(cells):
                x,y = tile_center(col,row)
                if 0 < int(level) < tide:
                    d.line([(x-7,y+1),(x-4,y-1),(x,y+1),(x+3,y-1),(x+7,y)], fill="#93bac2")
                chart = self.state.get("chart")
                if chart and chart[row][col]=="1":
                    d.point((x-12,y+7),fill="#f0deaf")
                    d.line((x-11,y+8,x-9,y+6),fill="#e5d7b1")
        for garden in self.state.get("gardens",[]):
            x,y=tile_center(garden["x"],garden["y"])
            tint = next((GOLD if p["name"]=="Amber" else TEAL for p in self.state.get("players", []) if p["id"]==garden["owner"]), "#f4adb7")
            for i in range(garden.get("stage",0)+2):
                dx = (-7,-3,2,6,8)[i]
                by = y-2-(i%3)*3
                d.line((x,y+7,x+dx,by),fill="#b3d783",width=2)
                d.ellipse((x+dx-2,by-2,x+dx+2,by+2),fill=tint)
        for n in self.state.get("notes",[]):
            x,y=tile_center(n["x"],n["y"])
            d.rectangle((x+5,y+2,x+13,y+8),fill="#eadfb6",outline="#504a39")
            d.line((x+5,y+2,x+9,y+5,x+13,y+2),fill="#81715b")
        for l in lights:
            x,y=tile_center(l["x"],l["y"])
            if l["lit"]:
                d.polygon([(x,y-7),(x+24,y-13),(x+22,y-4)],fill="#ceb97b")
            d.polygon([(x-4,y+6),(x-2,y-5),(x+2,y-5),(x+4,y+6)],fill="#e6ddc6",outline="#2e4451")
            d.rectangle((x-3,y-9,x+3,y-5),fill=GOLD if l["lit"] else "#83939c",outline=INK)
            d.polygon([(x-5,y-10),(x,y-13),(x+5,y-10)],fill="#b67562")
        if self.target:
            x,y=tile_center(*self.target)
            d.ellipse((x-9,y-7,x+9,y+7),outline=PAPER)
        players = self.state.get("players",[])
        for p in sorted(players,key=lambda p:p["id"]==self.pid):
            x,y=tile_center(p["x"],p["y"])
            mine=p["id"]==self.pid
            if sum(q["x"]==p["x"] and q["y"]==p["y"] for q in players)>1:
                x += 6 if mine else -6
            col=GOLD if p.get("name")=="Amber" else TEAL
            d.ellipse((x-9,y+4,x+9,y+9),fill="#274047")
            d.polygon([(x-7,y+5),(x-3,y-5),(x+3,y-5),(x+7,y+5)],fill=col,outline=INK)
            d.ellipse((x-4,y-9,x+4,y-2),fill="#f6eaca",outline=INK)
            d.line((x-5,y-8,x+5,y-8),fill=INK,width=2)
            if mine:
                d.line((x-4,y-13,x,y-11,x+4,y-13),fill=PAPER,width=2)
        me = self.me()
        loc = string.ascii_uppercase[me["x"]]+str(me["y"]+1) if me else "—"
        text(18,359,("AMBER" if self.side=="p2" else "TEAL")+"  /  "+loc,GOLD if self.side=="p2" else TEAL,FM)
        hum=int(self.state.get("hum",0))
        text(158,359,"NOTE HUM   "+("●"*hum+"·"*(3-hum)),MUTED,F[11])
        msg = self.hint if time.monotonic()<self.hint_until else "Click a tile to travel   ·   Arrow keys to step"
        text(400,359,msg,PAPER,F[12])
        for i,(k,label) in enumerate(BUTTONS):
            a=15+i*108
            box((a,383,a+102,415),"#213b49","#466271")
            box((a+6,390,a+23,408),"#38525e",None,3)
            text(a+11,392,k,GOLD,FM)
            text(a+30,390,label,PAPER,F[12])
        text(606,393,"N I G H T   /   F O L I O   0 1",MUTED,FM)
        d.line((18,424,836,424),fill="#385160")
        lines=list(self.history)[-2:]
        if me:
            for note in self.state.get("notes",[]):
                if (me["x"],me["y"])==(note["x"],note["y"]):
                    lines=[f'OPEN LETTER  /  {note["by"]}  ·  {loc}', note["text"]]
                    break
        for i,s in enumerate(lines):
            text(20,430+20*i,"›   "+str(s)[:119],PAPER if i else MUTED,F[12])
        if self.mode in ("say","note"):
            box((14,348,839,469),"#1c3442","#8da29a",8)
            text(30,363,"BURIED FIELD NOTE" if self.mode=="note" else "TRANSMIT TO THE OTHER KEEPER",GOLD,FM)
            text(30,391,self.buffer[-90:]+"▏",PAPER,F[14])
            text(30,439,"Enter  /  seal and send      Esc  /  discard",MUTED,F[12])
        elif self.mode=="journal":
            box((70,81,785,359),"#1b3140","#97a99d",8)
            text(91,94,"Station journal",PAPER,FT)
            text(520,106,"↑ ↓ scroll   ·   any other key closes",MUTED,F[11])
            end=len(self.history)-self.scroll
            for j,s in enumerate(list(self.history)[max(0,end-9):end]):
                text(92,141+j*22,str(s)[:104],PAPER,F[12])
        buf = GLib.Bytes.new(im.tobytes())
        pix = GdkPixbuf.Pixbuf.new_from_bytes(buf,GdkPixbuf.Colorspace.RGB,False,8,W,H,W*3)
        self.image.set_from_pixbuf(pix)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", choices=("p1","p2"), required=True)
    app = Atlas(ap.parse_args().side)
    Gtk.main()
