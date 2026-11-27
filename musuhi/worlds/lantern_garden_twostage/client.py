"""Lantern Garden | Mini PC field edition."""
import argparse
import json
import math
import os
import socket
import sys
import threading
from collections import deque
from functools import lru_cache

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from PIL import Image, ImageDraw, ImageFont

W, H = 854, 480
INK, IVORY, MIST, GOLD, MINT = "#0c2029", "#fff3cd", "#a0c1ba", "#ffbc72", "#74ecce"


@lru_cache(None)
def font(size, face="sans"):
    name = {"serif": "DejaVuSerif", "sans": "DejaVuSans", "bold": "DejaVuSans-Bold",
            "mono": "DejaVuSansMono"}[face]
    return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/" + name + ".ttf", size)


def word(d, xy, s, size=13, color=IVORY, face="sans", anchor=None):
    d.text(xy, s, font=font(size, face), fill=color, anchor=anchor)


def ranger(d, x, y, side, me, c):
    """A brimmed gardener and a hooded lamplighter, distinct even without color."""
    d.ellipse((x-10,y+5,x+10,y+10), fill="#162d34")
    d.line((x-3,y+4,x-4,y+8), fill="#dccaa0", width=2)
    d.line((x+3,y+4,x+4,y+8), fill="#dccaa0", width=2)
    d.polygon([(x-3,y-5),(x+3,y-5),(x+7,y+5),(x-7,y+5)], fill=c)
    d.ellipse((x-4,y-11,x+4,y-3),fill="#f6d4ad",outline=INK)
    if side == "p1":
        d.polygon([(x-9,y-8),(x-3,y-15),(x+2,y-15),(x+9,y-8)],fill=c,outline=INK)
    else:
        d.polygon([(x-6,y-8),(x-2,y-15),(x+4,y-14),(x+6,y-9),(x+2,y-10)],fill=c)
    if me:
        d.line((x-6,y+11,x+6,y+11),fill=IVORY,width=2)


def lantern(d, x, y, stage, owner, pulse, c):
    if stage < 2:
        d.line((x,y+5,x,y-1-stage*3),fill="#a1c785",width=2)
        d.ellipse((x-6,y-1,x,y+2),fill="#75b591")
        d.ellipse((x,y-4-stage*3,x+5,y-1-stage*3),fill=c)
        return
    if stage in (2, 3):
        d.line((x,y-4,x,y+6),fill="#99c792",width=2)
        if stage==2:
            d.ellipse((x-3,y-7,x+3,y-1),fill=c)
        else:
            for dx,dy in [(0,-4),(4,0),(-4,0),(0,4)]:
                d.ellipse((x+dx-3,y+dy-6,x+dx+3,y+dy),fill=c)
            d.ellipse((x-2,y-5,x+2,y-1),fill=IVORY)
        return
    r = 8 + int(pulse)
    d.ellipse((x-r,y-r-2,x+r,y+r-2), fill="#43534a" if owner=="p1" else "#285654")
    d.line((x,y-9,x,y+7),fill="#d4b888",width=2)
    if owner=="p1":
        d.polygon([(x,y-10),(x+6,y-4),(x,y+3),(x-6,y-4)],fill=c)
    else:
        d.rounded_rectangle((x-5,y-8,x+5,y+1),radius=3,fill=c)
    d.line((x,y-7,x,y-1),fill=IVORY,width=2)


LEFT, TOP, CW, CH = 37, 78, 30, 24
SAY = ["Hello, gardener!", "A bell for this place.", "Walk with me?", "Thank you for the light."]


def ground():
    im = Image.new("RGB",(W,H),INK)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((15,56,838,400),radius=12,fill="#142d35",outline="#395557")
    for y in range(13):
        for x in range(26):
            a,b = LEFT+x*CW, TOP+y*CH
            n = (x*43+y*61+x*y*17)%19
            soil = (45+n//4,67+n//3,65+n//3) if y != 6 else (63+n//4,77+n//4,68+n//4)
            d.rectangle((a,b,a+CW-2,b+CH-2),fill=soil)
            if n%3 == 1:
                px,py=a+3+n,b+10+n//3
                d.line((px-2,py-3,px,py,px+2,py-5),fill="#547567")
    for x in range(26):
        word(d,(LEFT+CW*x+CW//2,63),chr(65+x),10,MIST,"mono","mt")
    for y in range(13):
        word(d,(26,TOP+CH*y+CH//2),str(y+1),9,MIST,"mono","mm")
    word(d,(21,9),"Lantern Garden",30,IVORY,"serif")
    word(d,(281,16),"FIELD GUIDE   /   THE NIGHT PLOT",11,MIST,"mono")
    return im


class Garden:
    def __init__(self, side, name=None):
        self.side = side
        self.name = (name or side.upper()).strip()[:12]
        self.id = None
        self.state = {}
        self.sock = None
        self.target = None
        self.phrase = 0
        self.mode = ""
        self.text = ""
        self.notebook = False
        self.page = 0
        self.seen = {}
        self.notes = deque(maxlen=32)
        self.bg = ground()
        self.win = Gtk.Window(title="Lantern Garden | Field Guide")
        self.win.set_default_size(854,480)
        self.win.set_decorated(False)
        self.win.set_resizable(False)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.image = Gtk.Image()
        box = Gtk.EventBox()
        box.add(self.image)
        self.win.add(box)
        box.connect("button-press-event", self.click)
        self.win.connect("key-press-event", self.key)
        self.win.connect("destroy", Gtk.main_quit)
        self.draw()
        self.win.show_all()
        threading.Thread(target=self.network, daemon=True).start()
        GLib.timeout_add(200,self.draw)

    def network(self):
        peer=(os.environ["AAL_LAN_HOST"],int(os.environ.get("AAL_LAN_PORT","18765")))
        while True:
            try:
                with socket.create_connection(peer,timeout=4) as s:
                    s.settimeout(6)
                    s.sendall((json.dumps({"t":"join","name":self.name})+"\n").encode())
                    with s.makefile("rb") as f:
                        for line in f:
                            obj=json.loads(line)
                            if obj["t"]=="welcome":
                                self.id=obj["id"]
                            if obj["t"]=="state":
                                self.state=obj
                                self.sock=s
            except (OSError,ValueError):
                pass
            self.sock=None
            self.state={}
            threading.Event().wait(1.5)

    def send(self, t, **kw):
        s=self.sock
        if s is not None:
            try:
                s.sendall((json.dumps(dict(t=t,**kw))+"\n").encode())
            except OSError:
                pass

    def next_gap(self):
        st=self.state
        p=next((p for p in st.get("players",[]) if p["id"]==self.id),None)
        if not p: return None
        x,y=p["x"],p["y"]
        if any((pl["x"],pl["y"],pl["text"])==(x,y,"Third lamp is yours")
               for pl in st.get("plaques",[])) and y>0:
            return (x,y-1)
        return None

    def act(self):
        gap=self.next_gap()
        if gap:
            self.target=gap
            self.send("goto",x=gap[0],y=gap[1])
        else:
            self.send("act")

    def click(self, _, e):
        if self.mode: return True
        if self.notebook:
            if e.y>342 and e.y<384 and e.x>485 and e.x<727:
                self.page+= -1 if e.x<596 else 1
            else: self.notebook = False
            self.draw()
            return True
        if 275<=e.x<=675 and e.y<53:
            self.notebook=True
            return True
        if LEFT<=e.x<LEFT+CW*26 and TOP<=e.y<TOP+CH*13:
            x,y=int((e.x-LEFT)//CW),int((e.y-TOP)//CH)
            self.target=x,y
            self.send("goto",x=x,y=y)
        elif 405<=e.y<=449:
            if 493<=e.x<658:
                self.act()
            elif 665<=e.x<837:
                self.send("say",text=SAY[self.phrase])
                self.phrase=(self.phrase+1)%4
        return True

    def key(self, _, e):
        k=Gdk.keyval_name(e.keyval).lower()
        if self.mode:
            if k in ("return","kp_enter"):
                if self.mode=="name" or self.text.strip(): self.send(self.mode,text=self.text.strip())
                self.mode=""
            elif k=="escape": self.mode=""
            elif k=="backspace": self.text=self.text[:-1]
            else:
                ch=Gdk.keyval_to_unicode(e.keyval)
                if ch and chr(ch).isprintable() and len(self.text)<(24 if self.mode=="name" else 40):
                    self.text+=chr(ch)
            self.draw()
            return True
        if k=="f5":
            os.execv(sys.executable,[sys.executable]+sys.argv)
        if k=="j" or (k=="escape" and self.notebook):
            self.notebook=not self.notebook
            self.draw()
            return True
        if self.notebook and k in ("left","right","page_up","page_down"):
            self.page+= -1 if k in ("left","page_up") else 1
            self.draw()
            return True
        if k in ("n","t"):
            self.mode="name" if k=="n" else "say"
            self.text=""
            self.notebook=False
            self.draw()
            return True
        if self.notebook: return True
        ds={"left":(-1,0),"a":(-1,0),"right":(1,0),"d":(1,0),
            "up":(0,-1),"w":(0,-1),"down":(0,1),"s":(0,1)}
        if k in ds:
            dx,dy=ds[k]
            self.target=None
            self.send("move",dx=dx,dy=dy)
        elif k=="space": self.act()
        elif k in ("1","2","3","4"): self.send("say",text=SAY[int(k)-1])
        return True

    def draw(self):
        st=self.state
        im=self.bg.copy()
        d=ImageDraw.Draw(im)
        connected=self.sock is not None
        d.rounded_rectangle((683,15,835,43),radius=14,fill="#183e3e",outline="#406660")
        d.ellipse((697,25,704,32),fill=MINT if connected else GOLD)
        word(d,(713,19),"LAN Connected" if connected else "Joining garden",14)
        ps=st.get("players",[])
        me=next((p for p in ps if p["id"]==self.id),{})
        mx,my=me.get("x",-1),me.get("y",-1)
        if self.target and self.target != (mx,my):
            x,y=self.target
            a,b=LEFT+x*CW,TOP+y*CH
            d.rectangle((a+1,b+1,a+CW-3,b+CH-3),outline=IVORY)
        else: self.target=None
        here=None
        outage=None
        for plant in st.get("plants",[]):
            col,row=plant["x"],plant["y"]
            x,y=LEFT+CW*col+CW//2,TOP+CH*row+CH//2
            if (col,row)==(mx,my): here=plant
            if plant["stage"]==3 and [col,row]==st.get("wind_at"):
                outage=chr(65+col)+str(row+1)
                for i in range(3):
                    v=(st["tick"]+i*3)%14
                    d.line((x-15+v,y-7+i*5,x-9+v,y-9+i*5),fill="#b1d6d0")
            color=tuple(plant["color"])
            own="p1" if color[0]>color[2] else "p2"
            lantern(d,x,y,plant["stage"],own,math.sin(st["tick"]*.5+col),color)
            if 0<=plant["ring"]<10:
                r=9+plant["ring"]*2
                d.ellipse((x-r,y-r//2,x+r,y+r//2),outline=color)
                when=st["tick"]-plant["ring"]
                if self.seen.get((col,row))!=when:
                    self.seen[(col,row)]=when
                    note=(col+2*row)%7
                    self.notes.append((when,note,color,chr(65+col)+str(row+1)))
        for pl in st.get("plaques",[]):
            a,b=LEFT+CW*pl["x"],TOP+CH*pl["y"]
            d.line((a+5,b+11,a+5,b+19),fill="#d2b286",width=2)
            d.rectangle((a+1,b+7,a+10,b+12),fill="#e4cf9f",outline=INK)
        for p in ps:
            x,y=LEFT+CW*p["x"]+CW//2,TOP+CH*p["y"]+CH//2
            if sum(1 for q in ps if (q["x"],q["y"])==(p["x"],p["y"]))>1:
                x+=-6 if p["name"]=="P1" else 6
            ranger(d,x,y,p["name"].lower(),p==me,tuple(p["color"]))
            if p["say"]:
                length=d.textlength(p["say"],font=font(12))+16
                bx=max(18,min(W-18-length,x-length//2))
                d.rounded_rectangle((bx,y-35,bx+length,y-15),radius=7,fill=IVORY)
                word(d,(bx+8,y-34),p["say"],12,INK)
        score=st.get("glow",0)
        word(d,(23,408),"LANTERNS",10,MIST,"mono")
        word(d,(23,422),f"{score} / {st.get('goal',12)}",17,IVORY,"bold")
        word(d,(125,408),"SEED POUCH",10,MIST,"mono")
        word(d,(125,422),str(me.get("seeds","—")),17,IVORY,"bold")
        word(d,(229,408),"YOUR PLOT",10,MIST,"mono")
        tile=chr(65+mx)+str(my+1) if mx>=0 else "—"
        label= ["Seed","Sprout","Bud","Bloom","Lantern"][here["stage"]] if here else "Open soil"
        word(d,(229,423),tile+"  ·  "+label,15)
        word(d,(389,408),"NIGHT "+str(1+st.get("chapter",0)),10,MIST,"mono")
        word(d,(389,423),"Gust: "+outage if outage else "Quiet air",13,GOLD)
        act="Plant a seed" if not here else ("Light bloom" if here["stage"]==3 else "Ring bell" if here["stage"]==4 else "Tending…")
        if self.next_gap(): act="Enter gap ↑"
        for x,x2,s in [(493,658,act),(665,836,"Say  /  "+["Hello","A bell","Walk?","Thanks"][self.phrase])]:
            d.rounded_rectangle((x,405,x2,449),radius=7,fill="#214348",outline="#548078")
            word(d,((x+x2)//2,426),s,15,IVORY,"bold","mm")
        instruction="Click to walk  ·  Arrows to step  ·  Space to act  ·  T speak  ·  N plaque  ·  J notebook"
        word(d,(22,457),instruction,12,MIST)
        word(d,(833,457),"ED. 02",11,GOLD,"mono","rt")
        entries=st.get("plaques",[])
        plaque=next((pl for pl in entries if (pl["x"],pl["y"])==(mx,my)),None)
        if plaque:
            word(d,(281,30),plaque["text"][:37],14,GOLD,"serif")
        else:
            word(d,(281,32),"  ".join("CDEFGAB"[n] for _,n,_,_ in list(self.notes)[-9:]) or "J  /  Open your notebook",12,GOLD,"mono")
        if self.notebook:
            d.rounded_rectangle((108,71,746,391),radius=14,fill="#f5eaca",outline="#b4b093",width=3)
            word(d,(137,90),"The bell book",27,INK,"serif")
            word(d,(138,132),"RECENT RINGS   /   oldest → newest",11,"#42625f","mono")
            for i in range(5):
                d.line((139,164+7*i,716,164+7*i),fill="#abb7a4")
            for idx,(_,n,c,loc) in enumerate(list(self.notes)[-12:]):
                x=161+idx*48
                y=192-n*4
                d.ellipse((x-5,y-3,x+5,y+4),fill=c,outline=INK,width=2)
                d.line((x+5,y,x+5,y-20),fill=INK,width=2)
                word(d,(x,207),loc,10,INK,"mono","mt")
            pages=max(1,(len(entries)+5)//6)
            self.page%=pages
            word(d,(138,242),f"PLAQUE INDEX    {self.page+1} / {pages}",11,"#42625f","mono")
            for idx,pl in enumerate(entries[self.page*6:self.page*6+6]):
                a,b=138+(idx%2)*295,265+(idx//2)*24
                loc=chr(65+pl["x"])+str(pl["y"]+1)
                word(d,(a,b),loc,12,"#477769","mono")
                word(d,(a+38,b),pl["text"][:24],14,INK,"serif")
            if not entries: word(d,(138,265),"Press N on a plot to leave a name.",14,INK,"serif")
            word(d,(138,359),"J / Esc to return to the garden",11,"#42625f","mono")
            if pages>1:
                word(d,(505,355),"← Previous",13,INK)
                word(d,(630,355),"Next →",13,INK)
        if self.mode:
            d.rounded_rectangle((143,173,711,289),radius=12,fill="#f5eaca",outline="#a3baad",width=2)
            word(d,(163,191),"Inscription for "+tile if self.mode=="name" else "Say to the garden",20,INK,"serif")
            word(d,(163,227),self.text+"▏",15,INK)
            word(d,(163,263),"Enter to send   ·   Esc to cancel",11,"#42625f","mono")
        data=GLib.Bytes.new(im.tobytes())
        self.image.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_bytes(data,GdkPixbuf.Colorspace.RGB,False,8,W,H,W*3))
        return True


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--side",default="p2",choices=("p1","p2"))
    parser.add_argument("--name",help="Optional gardener name for a new arrival")
    args=parser.parse_args()
    Garden(args.side,args.name)
    Gtk.main()
