#!/usr/bin/env python3
"""Tidal Lantern Isle • two-keeper chart table."""
import argparse
from collections import deque
import json
import math
import os
import queue
import select
import socket
import threading
import time

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from PIL import Image, ImageDraw
from atlas import base_map, bloom, font, keeper, lantern, star, text, heron, koi, waypost

W,H=854,480
X,Y,T=12,55,28
INK="#172e39"; DARK="#122732"; PANEL="#203d48"; PAPER="#f3e9ce"; QUIET="#b3c7bc"; GOLD="#f0c986"
TOOLS=("dig","fill","plant","harvest","lantern","unlantern")
LABEL=("Cut ditch","Fill ditch","Sow reed","Gather","Set lamp","Lift lamp")
KINDS={"w":"sea","s":"sand","g":"grass","r":"rock","c":"grass"}


class Link:
    def __init__(self,side):
        self.name=side.upper(); self.sock=None; self.state={}; self.id=None
        self.note="Finding the island…"; self.note_at=0
        self.out=queue.Queue(); self.stop=threading.Event()
        threading.Thread(target=self.work,daemon=True).start()

    def tell(self,t,**args):
        if self.sock is not None:
            self.out.put({"t":t,**args})

    def work(self):
        while not self.stop.is_set():
            try:
                target=(os.environ["AAL_LAN_HOST"],int(os.environ.get("AAL_LAN_PORT","18765")))
                with socket.create_connection(target,timeout=2) as s:
                    s.settimeout(3)
                    s.sendall((json.dumps({"t":"hello","name":self.name})+"\n").encode())
                    self.sock=s; buf=b""
                    while not self.stop.is_set():
                        while not self.out.empty():
                            s.sendall((json.dumps(self.out.get_nowait())+"\n").encode())
                        if not select.select([s],[],[],.035)[0]: continue
                        data=s.recv(65536)
                        if not data: break
                        buf+=data
                        while b"\n" in buf:
                            line,buf=buf.split(b"\n",1); msg=json.loads(line)
                            if msg["t"]=="state": self.state=msg
                            elif msg["t"]=="welcome": self.id=msg["id"]
                            elif msg["t"]=="note": self.note=msg["text"]; self.note_at=time.monotonic()
            except (OSError,KeyError,ValueError):
                pass
            self.sock=None; self.id=None; self.state={}
            while not self.out.empty(): self.out.get_nowait()
            self.stop.wait(1)


def icon(d,x,y,n,c):
    if n in (0,1):
        d.line((x-4,y+5,x+4,y-4),fill=c,width=2)
        d.polygon([(x-7,y+4),(x-4,y+1),(x-1,y+4),(x-4,y+7),(x-7,y+7)],fill=c)
        if n==1: d.line((x-6,y-3,x-1,y-3),fill=c)
    elif n==2:
        d.line((x,y-3,x,y+6),fill=c,width=2)
        d.polygon([(x,y),(x-6,y-4),(x-6,y),(x,y+2)],fill=c)
        d.polygon([(x,y-2),(x+5,y-6),(x+5,y-3)],fill=c)
    elif n==3:
        d.arc((x-6,y-7,x+6,y+5),335,165,fill=c,width=2)
        d.line((x-3,y+3,x-6,y+7),fill=c,width=2)
    else:
        d.polygon([(x-6,y-3),(x,y-7),(x+6,y-3)],fill=c)
        d.rectangle((x-4,y-2,x+4,y+4),outline=c,width=2)
        d.line((x-3,y+6,x+3,y+6),fill=c)


class Chart:
    def __init__(self,side):
        self.side=side; self.link=Link(side); self.tool=2; self.hover=None; self.route=[]
        self.next_step=0; self.prev=None; self.base=None; self.chat=None; self.help=False
        self.flash=""; self.flash_at=0
        self.labels=False; self.journal=False; self.sign_at=None; self.seen=set()
        self.win=Gtk.Window(title="Tidal Lantern Isle · "+side.upper())
        self.win.set_default_size(854,480); self.win.set_resizable(False)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.win.set_decorated(False)
        self.image=Gtk.Image(); box=Gtk.EventBox(); box.add(self.image); self.win.add(box)
        box.add_events(Gdk.EventMask.POINTER_MOTION_MASK|Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.LEAVE_NOTIFY_MASK)
        box.connect("button-press-event",self.click); box.connect("motion-notify-event",self.motion)
        box.connect("leave-notify-event",lambda *_:setattr(self,"hover",None))
        self.win.connect("key-press-event",self.key)
        self.win.connect("destroy",self.quit)
        self.frame(); self.win.show_all()
        GLib.timeout_add(100,self.frame)

    def quit(self,*_):
        self.link.stop.set(); Gtk.main_quit()

    def me(self,s):
        return next((p for p in s.get("players",[]) if p["id"]==self.link.id),{})

    def info(self,msg):
        self.flash=msg; self.flash_at=time.monotonic()

    def move(self,dx,dy):
        self.link.tell("move",dx=dx,dy=dy)

    def path(self,s,p,tx,ty):
        goals={(tx,ty)}; start=(p["x"],p["y"]); q=deque([start]); parent={start:None}
        blocked={(l["x"],l["y"]) for l in s["lanterns"]}
        blocked.update((q["x"],q["y"]) for q in s["players"] if q["id"]!=p["id"])
        def walk(x,y):
            return 0<=y<len(s["tiles"]) and 0<=x<len(s["tiles"][y]) and s["tiles"][y][x] in "gcs" and (x,y) not in blocked
        if not walk(tx,ty): goals={(tx+dx,ty+dy) for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))}
        while q:
            a=q.popleft()
            if a in goals:
                path=[]
                while parent[a] is not None: path.append(a); a=parent[a]
                self.route=list(reversed(path)); self.next_step=0; return
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                b=(a[0]+dx,a[1]+dy)
                if b not in parent and walk(*b): parent[b]=a; q.append(b)
        self.info("No trail to that tile.")

    def motion(self,box,e):
        x,y=int(e.x),int(e.y)
        self.hover=((x-X)//T,(y-Y)//T) if X<=x<X+616 and Y<=y<Y+364 else None

    def use(self,x,y):
        self.link.tell("act",a=TOOLS[self.tool],x=x,y=y)

    def click(self,box,e):
        x,y=e.x,e.y; s=self.link.state; p=self.me(s)
        if self.help or self.journal: self.help=self.journal=False; return True
        if self.chat is not None: return True
        if X<=x<X+616 and Y<=y<Y+364 and p:
            tx,ty=int((x-X)//T),int((y-Y)//T); self.route=[]
            if e.button==3 or max(abs(tx-p["x"]),abs(ty-p["y"]))>1: self.path(s,p,tx,ty)
            else: self.use(tx,ty)
        elif 642<=x<842 and 232<=y<322:
            self.tool=min(5,2*int((y-232)//30)+int(x>=742))
        elif 644<=x<839 and 344<=y<372:
            self.link.tell("emote",e="wave" if x<742 else "heart")
        elif 644<=x<839 and 377<=y<409:
            if x<742: self.chat=""
            else: self.help=True
        elif 312<=x<=540 and 8<=y<=43: self.journal=True
        return True

    def key(self,w,e):
        k=(Gdk.keyval_name(e.keyval) or "").lower()
        if self.help or self.journal: self.help=self.journal=False; return True
        if self.chat is not None:
            if k in ("return","kp_enter"):
                if self.sign_at:
                    self.link.tell("sign",x=self.sign_at[0],y=self.sign_at[1],text=self.chat.strip())
                elif self.chat.strip(): self.link.tell("chat",text=self.chat.strip())
                self.chat=None; self.sign_at=None
            elif k=="escape": self.chat=None; self.sign_at=None
            elif k=="backspace": self.chat=self.chat[:-1]
            else:
                u=Gdk.keyval_to_unicode(e.keyval)
                if u and chr(u).isprintable() and len(self.chat)<(24 if self.sign_at else 60): self.chat+=chr(u)
            return True
        if k=="m": self.labels=not self.labels; return True
        if k=="f2": self.journal=True; return True
        if k=="n":
            s=self.link.state; p=self.me(s)
            if p:
                self.sign_at=(p["x"],p["y"]); self.route=[]
                self.chat=next((q["text"] for q in s.get("signs",[]) if (q["x"],q["y"])==self.sign_at),"")
            return True
        if k in ("return","t"): self.chat=""; return True
        if k in ("question","slash","f1"): self.help=True; return True
        dirs={"a":(-1,0),"left":(-1,0),"d":(1,0),"right":(1,0),"w":(0,-1),"up":(0,-1),"s":(0,1),"down":(0,1)}
        if k in dirs: self.route=[]; self.move(*dirs[k])
        elif k in tuple("123456"): self.tool=int(k)-1
        elif k=="space":
            p=self.me(self.link.state)
            if p:
                dx,dy=p.get("face",[1,0]); self.use(p["x"]+dx,p["y"]+dy)
        elif k in ("e","h","b","v","z"): self.link.tell("emote",e={"e":"wave","h":"heart","b":"dance","v":"cheer","z":"zzz"}[k])
        elif k in ("g","j"): self.link.tell("give",item="seed" if k=="g" else "glow")
        return True

    def world(self,s,p,now):
        rows=tuple(s["tiles"])
        if self.prev!=rows:
            self.base=base_map(rows,KINDS.get); self.prev=rows
        m=self.base.copy(); d=ImageDraw.Draw(m)
        for y,row in enumerate(rows):
            for x,k in enumerate(row):
                if k!="c": continue
                a,b=x*T+14,y*T+14; wet=s["wet"][y][x]=="1"
                bank="#8e825e"; water="#4d9b9f" if wet else "#a98863"
                d.rounded_rectangle((a-9,b-9,a+9,b+9),5,fill=bank)
                d.rounded_rectangle((a-7,b-7,a+7,b+7),4,fill=water)
                for dx,dy in ((0,1),(0,-1),(1,0),(-1,0)):
                    xx,yy=x+dx,y+dy
                    if 0<=yy<len(rows) and 0<=xx<len(row) and rows[yy][xx] in "cw":
                        d.line((a,b,a+dx*14,b+dy*14),fill=water,width=13)
                d.line((a-4,b-1,a+2,b-1),fill="#a4cfbf" if wet else "#927453")
        # Blue veil at midnight, warm paper tones at dusk.
        night=(1-math.cos(2*math.pi*s.get("day",0)))/2
        m=Image.blend(m,Image.new("RGB",m.size,"#2b355d"),.10+night*.32)
        d=ImageDraw.Draw(m)
        for i in range(24):
            xx=(i*83+int(now*3))%616; yy=(i*47+7)%364
            if rows[yy//T][xx//T]=="w": d.line((xx,yy,xx+4,yy,xx+6,yy-1),fill="#86b0ab")
        for q in self.route[::2]: d.ellipse((q[0]*T+12,q[1]*T+12,q[0]*T+15,q[1]*T+15),fill=PAPER)
        if self.hover:
            a,b=self.hover; x,y=a*T,b*T
            for dx,dy in ((0,0),(1,0),(0,1),(1,1)):
                u=x+2+dx*23; v=y+2+dy*23
                d.line((u+(1-2*dx)*5,v,u,v,u,v+(1-2*dy)*5),fill="#fff1be",width=2)
        for l in s.get("lanterns",[]):
            a,b=l["x"]*T+14,l["y"]*T+14
            for r,alpha in [(24,14),(16,26),(11,32)]: ImageDraw.Draw(m,"RGBA").ellipse((a-r,b-r-4,a+r,b+r-4),fill=(255,211,103,alpha))
            lantern(d,a,b,now)
        for q in s.get("plants",[]):
            a,b=q["x"]*T+14,q["y"]*T+14
            bloom(d,a,b,q["stage"],True,q["x"]+q["y"])
            if q["stage"]==3: star(d,a+7,b-11,3,"#fff4aa")
        for q in s.get("flies",[]):
            a,b=int(q["x"]*T+14),int(q["y"]*T+14)
            star(d,a,b,2,"#ffeda3")
        for i,q in enumerate(s.get("critters",[])):
            a,b=round(q["x"]*T+14),round(q["y"]*T+14)
            if q["kind"]=="heron": heron(d,a,b,now)
            if q["kind"]=="koi": koi(d,a,b,now,i)
            self.seen.add(q["kind"])
        for q in s.get("signs",[]):
            waypost(d,q["x"]*T+14,q["y"]*T+14)
        for q in sorted(s["players"],key=lambda q:q["y"]):
            a,b=q["x"]*T+14,q["y"]*T+14
            keeper(d,a,b,"p2" if q["name"].upper()=="P2" else "p1",q["id"]==self.link.id,now)
            msg=q.get("say") or {"heart":"♥","wave":"Hello!","dance":"♪ ♫","cheer":"Hooray!","zzz":"z Z z"}.get(q.get("emote"))
            if msg:
                msg=msg[:46]; width=int(font(11,"bold").getlength(msg))+14
                left=max(3,min(613-width,a-width//2)); top=max(1,b-41)
                d.rounded_rectangle((left,top,left+width,top+17),6,fill=PAPER,outline=INK)
                text(d,(left+7,top+1),msg,11,INK,"bold")
        for q in s.get("signs",[]):
            if self.labels or self.hover==(q["x"],q["y"]):
                a,b=q["x"]*T+14,q["y"]*T+14
                width=int(font(11,"serif").getlength(q["text"]))+14
                left=max(2,min(613-width,a-width//2)); top=max(1,b-30)
                d.rounded_rectangle((left,top,left+width,top+15),4,fill="#f4e9cc",outline="#876f57")
                text(d,(left+7,top),q["text"],11,INK,"serif")
        return m

    def frame(self):
        s=self.link.state; p=self.me(s); now=time.monotonic()
        if p and self.route and now>=self.next_step:
            pos=(p["x"],p["y"])
            while self.route and self.route[0]==pos: self.route.pop(0)
            if self.route:
                dx=self.route[0][0]-pos[0]; dy=self.route[0][1]-pos[1]
                if abs(dx)+abs(dy)==1: self.move(dx,dy)
                else: self.route=[]
            self.next_step=now+.28
        im=Image.new("RGB",(W,H),DARK); d=ImageDraw.Draw(im)
        # Brass instrument crest and title masthead.
        d.ellipse((14,10,46,42),outline=GOLD,width=1); star(d,30,26,11,GOLD)
        text(d,(56,5),"Tidal Lantern Isle",28,PAPER,"serif")
        text(d,(320,20),f"F I E L D   A T L A S    /   {s.get('level',1):02}   [F2]",10,QUIET,"mono")
        d.line((12,48,842,48),fill="#57716f")
        d.rounded_rectangle((703,11,841,39),13,fill="#294e4c")
        d.ellipse((715,21,722,28),fill="#a2ddb5" if s else GOLD)
        text(d,(729,15),"LAN Connected" if s else "Linking…",13,PAPER,"bold")
        d.rectangle((X-1,Y-1,X+616,Y+364),outline="#70918a")
        if s: im.paste(self.world(s,p,now),(X,Y))
        else: text(d,(320,237),"Looking for the island…",23,PAPER,"serif","mm")
        d.rounded_rectangle((637,54,842,419),8,fill=PANEL)
        text(d,(649,61),"KEEPER  /  "+self.side.upper(),11,GOLD,"mono")
        text(d,(649,80),"Island light",18,PAPER,"serif")
        light=s.get("light",0); goal=s.get("goal",30)
        text(d,(830,84),f"{light}/{goal}",13,PAPER,"mono","ra")
        d.rounded_rectangle((649,107,830,113),3,fill=INK)
        if light: d.rounded_rectangle((649,107,649+int(181*min(1,light/max(1,goal))),113),3,fill=GOLD)
        tide=s.get("tide",0); text(d,(649,122),"TIDE",10,QUIET,"mono")
        text(d,(830,122),f"{round(100*tide)}%  ·  reach {s.get('reach',0)}",11,PAPER,"mono","ra")
        for i in range(28):
            v=(1+math.sin((i/27)*math.pi*2-1.57))/2
            d.line((650+i*6,159,650+i*6,156-int(v*13)),fill="#7cc9bc" if i/27<=tide else "#446b70",width=3)
        d.line((649,168,830,168),fill="#42616a")
        for i,(k,label,col) in enumerate([("seeds","SEEDS","#bad59a"),("glow","GLOW",GOLD)]):
            left=649+i*93; text(d,(left,180),p.get(k,"–"),21,col,"serif")
            text(d,(left+32,188),label,10,QUIET,"mono")
        text(d,(649,213),"GARDEN TOOLS",10,QUIET,"mono")
        for i,label in enumerate(LABEL):
            x=644+(i%2)*98; y=233+(i//2)*30; active=i==self.tool
            d.rounded_rectangle((x,y,x+94,y+25),5,fill="#e3cc97" if active else "#2d4b55")
            c=INK if active else PAPER; icon(d,x+11,y+12,i,c)
            text(d,(x+21,y+5),label,11,c,"bold" if active else "sans")
        text(d,(649,328),"SIGNALS",10,QUIET,"mono")
        for i,label in enumerate(["Wave  E","Heart  H","Chat  ↵","Guide  ?"]):
            x=644+i%2*98; y=345+i//2*33
            d.rounded_rectangle((x,y,x+94,y+26),5,outline="#4c6b70")
            text(d,(x+47,y+12),label,12,PAPER,"sans","mm")
        log=s.get("log",[])
        msg=log[-1] if log else "Welcome, keeper. Cut a channel from the sea and sow reeds beside it."
        if now-self.link.note_at<4: msg=self.link.note
        if now-self.flash_at<3: msg=self.flash
        text(d,(14,428),"FIELD NOTES",10,GOLD,"mono"); text(d,(102,424),msg[:90],14,PAPER)
        text(d,(14,453),"Click near: use    ·    Click far: walk    ·    1–6: tools    ·    N: name place    ·    M: map names    ·    F2: atlas    ·    ?: guide",12,QUIET)
        if self.chat is not None:
            d.rounded_rectangle((10,425,842,474),5,fill=PAPER)
            heading="WAYPOST   /   NAME THIS TILE   ·   ENTER TO CARVE   ·   EMPTY TO REMOVE" if self.sign_at else "RADIOGRAM   /   ENTER TO SEND"
            text(d,(20,430),heading+"   ·   ESC TO CANCEL",10,"#476262","mono")
            text(d,(20,447),self.chat+"▏",15,INK)
        if self.help:
            d.rounded_rectangle((113,66,740,413),14,fill=INK,outline=GOLD,width=2)
            text(d,(141,84),"Keeper’s field guide",27,GOLD,"serif")
            lines=["Cut a ditch from open sea. Water runs farther at high tide.",
                   "Sow reeds on grass beside water. Starred blossoms are ripe.",
                   "Gather ripe reeds for glow and seeds; two glow make one lamp.",
                   "Unripe reeds return only a seed. A lifted lamp returns its glow.",
                   "Walk: arrows, WASD, distant click, or right-click any tile.",
                   "Use: click an adjacent tile, or Space to work where you face.",
                   "1 Cut  ·  2 Fill  ·  3 Sow  ·  4 Gather  ·  5 Set lamp  ·  6 Lift lamp",
                   "E Wave  ·  H Heart  ·  B Dance  ·  V Cheer  ·  Z Rest  ·  Enter Chat",
                   "Stand near a friend: G shares a seed; J shares one glow."]
            for i,line in enumerate(lines): text(d,(142,138+i*25),line,14,PAPER)
            text(d,(142,365),"N: carve a waypost where you stand   ·   M: map names   ·   F2: atlas",13,GOLD)
            text(d,(142,386),"PRESS ANY KEY OR CLICK TO RETURN",10,QUIET,"mono")
        if self.journal:
            d.rounded_rectangle((87,57,766,417),10,fill="#f4eacf",outline="#a58c65",width=2)
            d.line((425,78,425,390),fill="#c5b793",width=2)
            text(d,(112,77),"THE KEEPERS’ FIELD ATLAS",10,"#7a6a54","mono")
            text(d,(112,99),"Island register",25,INK,"serif")
            text(d,(112,145),f"Chart {s.get('level',1):02}     {len(s.get('lanterns',[]))} lamps lit",13,"#566d62")
            signs=s.get("signs",[])
            if not signs: text(d,(112,178),"Press N on solid ground to name it.",13,"#756c58","serif")
            for i,q in enumerate(signs[:8]):
                yy=179+23*i; waypost(d,120,yy+4)
                text(d,(136,yy-5),q["text"],13,INK,"serif")
                text(d,(404,yy-3),f"{q['x']:02},{q['y']:02}",10,"#746c58","mono","ra")
            text(d,(450,77),"NATURAL HISTORY   /   SIGHTINGS",10,"#7a6a54","mono")
            for i,(kind,title,lines) in enumerate([
                ("koi","Lantern koi",("In the Moonwell at ebb; at flood","they explore the new channels.")),
                ("heron","Silver heron",("Five lamps around the well call","a watcher to the water’s edge."))]):
                yy=125+116*i
                if kind=="koi": koi(d,471,yy+10,now,0)
                else: heron(d,471,yy+10,now)
                text(d,(506,yy-10),title,18,INK,"serif")
                text(d,(506,yy+16),"OBSERVED" if kind in self.seen else "AWAITING SIGHTING",9,"#577965","mono")
                for j,line in enumerate(lines): text(d,(450,yy+42+j*17),line,13,"#596658")
            text(d,(112,385),"M  SHOW PLACE NAMES",10,"#776b57","mono")
            text(d,(450,385),"ANY KEY  CLOSE BOOK",10,"#776b57","mono")
        data=GLib.Bytes.new(im.tobytes())
        pix=GdkPixbuf.Pixbuf.new_from_bytes(data,GdkPixbuf.Colorspace.RGB,False,8,W,H,W*3)
        self.image.set_from_pixbuf(pix)
        return True


if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--side",choices=["p1","p2"],default="p2")
    Chart(parser.parse_args().side); Gtk.main()
