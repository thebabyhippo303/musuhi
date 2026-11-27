"""Lantern Garden: the Linux garden window."""
import argparse
import json
import math
import os
import queue
import random
import socket
import threading
import time

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from PIL import Image, ImageDraw, ImageFont

W, H = 854, 480
CAST = {
    "p1": ("Lantern", "lantern", "#68ded1"),
    "p2": ("Moth", "moth", "#ffbd68"),
    "p3": ("Prism", "prism", "#ff9487"),
    "p4": ("Kite", "kite", "#c997ff"),
}


def font(size, bold=False):
    name = "DejaVuSans" + ("-Bold" if bold else "") + ".ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


LABEL, SMALL, BODY, TITLE = font(11, True), font(12), font(14), font(20, True)


def motif(d, x, y, shape, color, t):
    x, y = int(x), int(y)
    def poly(points, fill, outline=None):
        d.polygon([(x+a, y+b) for a, b in points], fill=fill, outline=outline)
    if shape == "moth":
        a = round(2*math.sin(t*4))
        poly([(-1,-3),(-14,-10+a),(-11,1),(-4,6),(-1,2)],color)
        poly([(1,-3),(12,-8+a),(10,3),(5,7),(1,2)],color)
        d.line([(x-4,y-9),(x,y-4),(x+4,y-9)],fill="#fce6b9")
        d.line((x,y-4,x,y+5),fill="#ffe9b9",width=2)
    elif shape == "lantern":
        d.arc((x-4,y-12,x+4,y-3),180,360,fill=color,width=2)
        d.rounded_rectangle((x-7,y-6,x+7,y+8),3,fill=color,outline="#bffff2")
        d.rectangle((x-5,y-8,x+5,y-6),fill="#549d99")
        d.line((x,y-3,x,y+5),fill="#eaffdf",width=3)
    elif shape == "prism":
        poly([(0,-12),(-12,7),(10,9)],color, "#ffe1ce")
        d.line([(x,y-10),(x+2,y+3),(x-10,y+6)],fill="#fff0cb")
        d.line((x+2,y+3,x+9,y+8),fill="#ffdbc0")
    elif shape in ("diamond", "kite"):
        d.line([(x,y+7),(x+4,y+12),(x+1,y+16)], fill=color)
        poly([(0,-12),(10,-2),(0,9),(-10,-2)],color, "#eed7ff")
        d.line((x,y-10,x,y+8),fill="#f1dcff")
    else:
        d.ellipse((x-8,y-8,x+8,y+8),fill=color,outline="#fff1cc")


class Link:
    def __init__(self, side):
        self.side = side
        self.state = {}
        self.who = None
        self.live = False
        self.out = queue.Queue(32)
        threading.Thread(target=self.run, daemon=True).start()

    def send(self, kind, **data):
        if self.live and not self.out.full():
            self.out.put_nowait(dict(t=kind, **data))

    def run(self):
        endpoint = (os.environ["AAL_LAN_HOST"], int(os.environ.get("AAL_LAN_PORT","18765")))
        while True:
            try:
                with socket.create_connection(endpoint, timeout=4) as sock:
                    sock.settimeout(.045)
                    name, shape, color = CAST[self.side]
                    def send(obj):
                        sock.sendall((json.dumps(obj)+"\n").encode())
                    send(dict(t="hello", name=self.side.upper(), shape=shape,
                              color=list(bytes.fromhex(color[1:]))))
                    buf = b""
                    while True:
                        while not self.out.empty():
                            send(self.out.get_nowait())
                        try:
                            chunk = sock.recv(65536)
                        except socket.timeout:
                            continue
                        if not chunk:
                            break
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            msg = json.loads(line)
                            if msg.get("t") == "welcome":
                                self.who = msg["id"]
                            if msg.get("t") == "state":
                                self.state = msg
                                self.live = True
            except (OSError, ValueError, KeyError):
                pass
            self.live = False
            self.state = {}
            self.who = None
            while not self.out.empty():
                self.out.get_nowait()
            threading.Event().wait(1)


def landscape():
    im = Image.new("RGB",(W,H))
    d = ImageDraw.Draw(im)
    rng = random.Random(317)
    for y in range(H):
        f = y/H
        d.line((0,y,W,y),fill=(int(14+7*f),int(22+25*f),int(43+10*f)))
    for _ in range(150):
        x, y = rng.randrange(W), rng.randrange(45,300)
        c = rng.choice(["#51677a","#887e93","#4f677e","#b2a690"])
        d.point((x,y), fill=c)
        if rng.randrange(7)==0:
            d.line((x-1,y,x+1,y),fill=c)
    d.ellipse((719,63,753,97),fill="#cdd4ba")
    d.ellipse((712,59,747,93),fill="#10192e")
    for y0, height, col, freq in [(183,26,"#1a2a40",60),(212,22,"#203545",50),(233,19,"#183946",77)]:
        edge=[(x,int(y0+height*math.sin(x/freq)+10*math.cos(x/29))) for x in range(-4,W+8,4)]
        d.polygon(edge+[(W,H),(0,H)], fill=col)
    for k in range(15):
        pts=[(x,int(222+k*19+13*math.sin(x/110+k*.37)+6*math.cos(x/62))) for x in range(-5,W+12,5)]
        d.line(pts,fill="#20404b" if k%2 else "#213e48")
    for _ in range(420):
        x, y = rng.randrange(W), rng.randrange(242,H)
        tall = rng.randint(2,6)
        d.line([(x-2,y-tall),(x,y),(x+2,y-3)],fill=rng.choice(["#294c51","#2a4951","#305154"]))
    return im


class Garden:
    def __init__(self, side):
        self.side = side
        self.link = Link(side)
        self.base = landscape()
        self.target = None
        self.mouse = (-100,-100)
        self.chat = None
        self.win = win = Gtk.Window(title="Lantern Garden — "+side.upper())
        win.set_default_size(854, 480)
        win.set_resizable(False)
        win.set_position(Gtk.WindowPosition.CENTER)
        # Keep screenshot and world coordinates identical on both Linux machines.
        win.set_decorated(False)
        self.image = Gtk.Image()
        box = Gtk.EventBox()
        box.add(self.image)
        win.add(box)
        box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        box.connect("button-press-event",self.click)
        box.connect("motion-notify-event",self.hover)
        win.connect("key-press-event",self.key)
        win.connect("destroy",lambda *_: Gtk.main_quit())
        self.draw()
        win.show_all()
        GLib.timeout_add(95,self.draw)

    def hover(self, _, e):
        self.mouse = (e.x,e.y)

    def click(self, _, e):
        if e.y < 44:
            if 450 <= e.x <= 535:
                self.link.send("plant")
            return True
        self.link.send("move",x=round(e.x),y=round(e.y))
        self.target = (int(e.x),int(e.y),time.monotonic())
        return True

    def key(self, _, e):
        k = Gdk.keyval_name(e.keyval) or ""
        if self.chat is not None:
            if k == "Escape":
                self.chat = None
            elif k in ("Return","KP_Enter"):
                if self.chat.strip():
                    self.link.send("say",text=self.chat.strip())
                self.chat = None
            elif k == "BackSpace":
                self.chat = self.chat[:-1]
            else:
                c = Gdk.keyval_to_unicode(e.keyval)
                if 32 <= c < 127 and len(self.chat)<60:
                    self.chat += chr(c)
            return True
        dirs = {"Left":(-1,0),"a":(-1,0),"Right":(1,0),"d":(1,0),"Up":(0,-1),"w":(0,-1),"Down":(0,1),"s":(0,1)}
        if k in dirs:
            dx,dy = dirs[k]
            self.link.send("step",dx=dx,dy=dy)
            self.target = None
        elif k == "space":
            self.link.send("plant")
        elif k in ("Return","KP_Enter"):
            self.chat = ""
        return True

    def draw(self):
        im = self.base.copy()
        d = ImageDraw.Draw(im)
        now = time.monotonic()
        s = self.link.state
        glow = s.get("glow",0)
        pals = s.get("players",[])
        for i in range(min(glow,48)):
            x,y = (83+i*173)%W, 51+(i*71)%121
            d.line((x-1,y,x+1,y),fill="#a5b9aa")
        hit = None
        for seed in s.get("seeds",[]):
            x,y,c = int(seed["x"]),int(seed["y"]),tuple(seed["color"])
            d.ellipse((x-6,y-5,x+6,y+5),outline="#648081")
            d.line([(x-3,y-1),(x,y+2),(x+4,y-3)],fill=c,width=2)
            if math.dist(self.mouse,(x,y))<18:
                hit = "Seed  /  "+seed["name"]
        for b in s.get("blooms",[]):
            x,y,c = int(b["x"]),int(b["y"]),tuple(b["color"])
            lv = b["level"]
            names = b["names"]
            word = b.get("word", "")
            d.line([(x,y),(x-1,y+8),(x+3,y+11)],fill="#76aa94",width=2)
            for j in range(2*lv+1):
                a = math.tau*j/(2*lv+1)-1.57
                px,py=x+round((4+lv)*math.cos(a)),y+round((4+lv)*math.sin(a))
                d.ellipse((px-3,py-3,px+3,py+3),fill=c)
                n=names[j%len(names)].lower()
                if n in CAST:
                    d.point((px,py-1),fill=CAST[n][2])
            d.ellipse((x-2,y-2,x+2,y+2),fill="#fff1af")
            if lv>=4:
                for a in range(4):
                    xx=x+round(14*math.cos(a*math.pi/2))
                    yy=y+round(14*math.sin(a*math.pi/2))
                    d.line((xx-1,yy,xx+1,yy), fill="#ffecac")
                    d.line((xx,yy-1,xx,yy+1), fill="#ffecac")
            if word:
                w = int(d.textlength(word,font=LABEL))
                bx = min(max(4,x-w//2),W-w-4)
                by = y+13 if y < H-24 else y-25
                if not any(abs(p["x"]-x)<max(24,w//2+14) and abs(p["y"]-by)<24 for p in pals):
                    d.text((bx,by),word,font=LABEL,fill="#eadfbf",stroke_width=2,stroke_fill="#1b2935")
            if math.dist(self.mouse,(x,y))<18:
                hit = (word or ("Star bloom" if lv>=4 else "Bloom"))+"  /  "+" + ".join(names)
        if self.target and now-self.target[2]<2.2:
            x,y,_ = self.target
            d.ellipse((x-8,y-5,x+8,y+5),outline="#95a99b")
        for p in pals:
            x,y,c = int(p["x"]),int(p["y"]),tuple(p["color"])
            own = p["id"]==self.link.who
            d.ellipse((x-12,y+6,x+12,y+11),fill="#152f39")
            if own:
                d.arc((x-17,y-12,x+17,y+13),25,155,fill=c,width=2)
            motif(d,x,y,p["shape"],c,now)
            txt=p["name"]
            labelx=max(8,min(W-24,x-8))
            labely=y+13 if y<H-30 else y-25
            d.text((labelx,labely),txt,fill="#f6eed9",font=LABEL,stroke_width=2,stroke_fill="#182936")
        d.rectangle((0,0,W,43), fill="#101726")
        d.line((0,43,W,43), fill="#47616b")
        d.text((14,7),"Lantern Garden",font=TITLE,fill="#f4e8cb")
        d.text((200,15),f'{self.side.upper()}   /   {len(pals)} HERE   /   {glow} GLOW',font=LABEL,fill="#a4c1bc")
        d.rounded_rectangle((451,8,536,34),7,fill="#293444",outline="#5b6466")
        d.text((459,14),"Plant · Space",font=LABEL,fill="#f5d89e")
        d.text((548,15),"Click: walk   Enter: say",font=SMALL,fill="#b1c2c9")
        d.rounded_rectangle((704,8,842,34),12,fill="#193631",outline="#376b57")
        d.ellipse((714,18,721,25), fill="#89ecc3" if self.link.live else "#d09d68")
        d.text((728,14),"LAN Connected" if self.link.live else "Joining garden",font=LABEL,fill="#d7ecda")
        msgs = s.get("msgs",[])
        note = ("Say:  "+self.chat+"▏") if self.chat is not None else hit
        if note is None and msgs:
            last=msgs[-1]
            note=("✧  " if last["from"]=="*" else last["from"]+"   /   ")+last["text"]
        if note:
            length=min(W-26, max(110,int(d.textlength(note,font=SMALL))+18))
            d.rounded_rectangle((10,H-27,10+length,H-6),6,fill="#132430",outline="#3c555b")
            d.text((19,H-24),note,font=SMALL,fill="#e8deba")
        raw = GLib.Bytes.new(im.tobytes())
        pix = GdkPixbuf.Pixbuf.new_from_bytes(raw,GdkPixbuf.Colorspace.RGB,False,8,W,H,3*W)
        self.image.set_from_pixbuf(pix)
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--side",default="p2",choices=CAST)
    garden = Garden(ap.parse_args().side)
    Gtk.main()


if __name__ == "__main__":
    main()
