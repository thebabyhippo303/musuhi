"""Lantern Isle · an illustrated co-op field atlas."""
import argparse
import collections
import json
import math
import os
from pathlib import Path
import socket
import threading
import time
import gi
gi.require_version("Gtk","3.0")
gi.require_version("Gdk","3.0")
gi.require_version("GdkPixbuf","2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from PIL import Image, ImageDraw
from art import T, INK, MOSS, GOLD, PAPER, font, txt, terrain, sprite, night_tint
import journal
import music

OX, OY = 10, 58
TOOLS = ["walk","plant","water","harvest","path","lantern","clear"]
NAMES = ["Explore","Sow seed","Water","Harvest","Lay path","Lantern","Clear"]
HINTS = ["Click a tile to walk there.","Click empty grass to sow.","Click a plant to water.","Click a flower to harvest.",
         "Click a clear tile to pave.","Click a tile • costs 3 petals.","Click an object to clear."]
TOUR = [
    ((3,10),"The tide line","Stand on the sand where Bram and Wren first met the sea."),
    ((21,10),"Two Waves","Two paths joined; a wildflower sprang between two waves."),
    ((25,9),"The Pond Needle","A necklace of petals grew into the name of our first star."),
    ((21,14),"Flower piano","Five flower keys, one stone keybed. The valley song lives here."),
    ((16,4),"The northern stage","A petal earned by applause helped light this second lamp."),
]


def route(rows,start,end,radius):
    todo=collections.deque([start])
    parent={start:None}
    while todo:
        x,y = p = todo.popleft()
        if max(abs(x-end[0]),abs(y-end[1]))<=radius:
            while parent[p] is not None and parent[p]!=start:
                p=parent[p]
            return p
        for dx,dy in ((1,0),(-1,0),(0,-1),(0,1)):
            q=(x+dx,y+dy)
            if (q not in parent and 0<=q[1]<len(rows) and 0<=q[0]<len(rows[q[1]])
                    and rows[q[1]][q[0]] in ".s"):
                parent[q]=x,y
                todo.append(q)
    return None


class Fieldbook:
    def __init__(self,side):
        self.side=side
        self.name="Bram" if side=="p1" else "Wren"
        self.sock=None
        self.id=None
        self.running=True
        self.rows=[]
        self.state={}
        self.base=Image.new("RGB",(700,360),"#649c9a")
        self.tool=0
        self.goal=None
        self.lastmove=0
        self.chat=None
        self.renaming=None
        self.note=("",0)
        self.book=None
        self.stand=False
        self.tour=-1
        self.bells=music.Bells()
        self.star=0
        self.notepath=Path(os.environ.get("XDG_STATE_HOME",Path.home()/".local/state"))/"lantern-isle"/(side+"-plates.json")
        try: self.seen=set(json.loads(self.notepath.read_text()))
        except (OSError,ValueError,TypeError): self.seen=set()
        self.win=Gtk.Window(title="Lantern Isle — "+self.name)
        self.win.set_decorated(False)
        self.win.set_default_size(854,480)
        self.win.set_resizable(False)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.win.connect("destroy",self.close)
        self.win.connect("key-press-event",self.key)
        box=Gtk.EventBox()
        self.img=Gtk.Image()
        box.add(self.img)
        box.connect("button-press-event",self.click)
        self.win.add(box)
        self.draw()
        self.win.show_all()
        threading.Thread(target=self.connect,daemon=True).start()
        GLib.timeout_add(140,self.draw)

    def close(self,*_):
        self.running=False
        Gtk.main_quit()

    def connect(self):
        target=(os.environ.get("AAL_LAN_HOST", "localhost"),int(os.environ.get("AAL_LAN_PORT","18765")))
        while self.running:
            try:
                with socket.create_connection(target,timeout=4) as sock:
                    sock.settimeout(10)
                    sock.sendall((json.dumps({"t":"hello","name":self.name,"side":self.side})+"\n").encode())
                    with sock.makefile("rb") as f:
                        while self.running:
                            line=f.readline(256000)
                            if not line: break
                            GLib.idle_add(self.recv,json.loads(line),sock)
            except (OSError,ValueError): pass
            GLib.idle_add(self.offline)
            threading.Event().wait(1.2)

    def offline(self):
        self.sock=None
        self.id=None
        self.goal=None

    def recv(self,m,sock):
        if m.get("t")=="welcome":
            self.rows=m["tiles"]
            self.base=terrain(self.rows)
            self.id=str(m["id"])
            self.sock=sock
        elif m.get("t")=="state":
            self.state=m
            self.bells.hear(m.get("tune",[]))
            new=journal.discover(m,self.me(),self.rows)-self.seen
            if new:
                self.seen.update(new)
                try:
                    self.notepath.parent.mkdir(parents=True,exist_ok=True)
                    self.notepath.write_text(json.dumps(sorted(self.seen)))
                except OSError: pass
            self.advance()
        elif m.get("t")=="err":
            self.notice(m.get("msg","Try another plot."))

    def send(self,t,**data):
        if self.sock is None: return
        try: self.sock.sendall((json.dumps(dict(data,t=t))+"\n").encode())
        except OSError: self.offline()

    def notice(self,s):
        self.note=s,time.monotonic()+3.4

    def me(self):
        return self.state.get("players",{}).get(self.id,{})

    def advance(self):
        if not self.goal or not self.me(): return
        if time.monotonic()-self.lastmove < .14: return
        gx,gy,i=self.goal
        start=self.me()["x"],self.me()["y"]
        nxt=route(self.rows,start,(gx,gy),int(i!=0))
        if nxt and nxt!=start:
            self.send("move",dx=nxt[0]-start[0],dy=nxt[1]-start[1])
            self.lastmove=time.monotonic()
        else:
            self.goal=None
            if nxt is None: self.notice("No trail reaches that tile.")
            elif i: self.send("act",a=TOOLS[i],x=gx,y=gy)

    def next_stop(self):
        if not self.me(): return
        self.tour+=1
        self.goal=None
        self.chat=None
        self.book=None
        self.stand=False
        self.tool=0
        if self.tour>=len(TOUR):
            self.tour=-1
            self.notice("Walking tour complete. The stage is yours.")
        else:
            (x,y),_,_=TOUR[self.tour]
            self.goal=x,y,0
            self.advance()

    def click(self,_,ev):
        x,y=int(ev.x),int(ev.y)
        if self.stand and 29<=x<=690 and 234<=y<=412:
            if 331<=y<=373 and 45<=x<675:
                self.send("chime",n=min(4,(x-45)//126))
            elif y<270 and 506<=x<640: self.bells.sound=not self.bells.sound
            elif y<270 and x>=640: self.stand=False
        elif self.book is not None:
            if self.renaming is not None: return True
            if 367<=y<=391 and 49<=x<669:
                self.book=(x-49)//155
            elif self.book==2 and 455<=x<=665 and 320<=y<=354 and self.state.get("sky"):
                self.renaming=self.star
                self.chat=""
            elif self.book==2 and 49<=x<455 and 132<=y<354:
                first=self.star//10*10
                subset=range(first,min(first+10,len(self.state.get("sky",[]))))
                if subset: self.star=min(subset,key=lambda i: math.dist((x,y),journal.star_pos(i)))
            else: self.book=None
        elif 210<=x<455 and y<49:
            if 326<=x<386: self.next_stop()
            elif x>=386: self.stand=not self.stand
            else: self.book=0; self.stand=False
        elif self.tour>=0 and 23<=x<=421 and 354<=y<=408:
            self.next_stop()
        elif OX<=x<OX+700 and OY<=y<OY+360 and self.me():
            self.chat=None
            self.tour=-1
            self.goal=((x-OX)//T,(y-OY)//T,self.tool if ev.button==1 else 0)
            self.advance()
        elif 718<=x<=845 and 138<=y<138+7*29:
            self.tool=(y-138)//29
            self.goal=None
            self.tour=-1
        elif x>=718 and 349<=y<=379: self.send("emote",e="wave" if x<781 else "heart")
        elif x>=718 and 382<=y<=413: self.chat=""
        self.draw()
        return True

    def key(self,_,ev):
        name=Gdk.keyval_name(ev.keyval) or ""
        if self.chat is not None:
            if name=="Return":
                if self.chat.strip():
                    if self.renaming is not None: self.send("name_star",i=self.renaming,name=self.chat.strip()[:24])
                    else: self.send("say",text=self.chat.strip())
                self.chat=None
                self.renaming=None
            elif name=="Escape": self.chat=None; self.renaming=None
            elif name=="BackSpace": self.chat=self.chat[:-1]
            elif ev.string and ev.string.isprintable(): self.chat=(self.chat+ev.string)[:24 if self.renaming is not None else 60]
        elif name in ("m","M"):
            self.stand=not self.stand
            self.book=None
            self.goal=None
        elif name in ("g","G"):
            self.next_stop()
        elif name in ("F1","F2","F3","F4","F5"):
            self.send("chime",n=int(name[1:])-1)
        elif self.stand and name in ("s","S"):
            self.bells.sound=not self.bells.sound
        elif self.stand and name=="Escape": self.stand=False
        elif self.book is not None:
            if name in ("j","J","Escape","F1","Return"): self.book=None
            elif name in ("Right","Left","Tab"):
                self.book=(self.book+(-1 if name=="Left" else 1))%4
            elif self.book==2 and name in ("Up","Down"):
                self.star=(self.star+(-1 if name=="Up" else 1))%max(1,len(self.state.get("sky",[])))
            elif self.book==2 and name=="r" and self.state.get("sky"):
                self.renaming=self.star
                self.chat=""
        elif name in ("j","J"):
            self.book=0
            self.stand=False
            self.goal=None
        elif name in ("Left","Right","Up","Down","a","d","w","s"):
            self.tour=-1
            self.goal=None
            dx,dy={"Left":(-1,0),"Right":(1,0),"Up":(0,-1),"Down":(0,1),
                   "a":(-1,0),"d":(1,0),"w":(0,-1),"s":(0,1)}[name]
            self.send("move",dx=dx,dy=dy)
        elif name in tuple("1234567"):
            self.tool=int(name)-1
            self.goal=None
        elif name=="Return": self.chat=""
        elif name in ("v","h","l","k"): self.send("emote",e={"v":"wave","h":"heart","l":"laugh","k":"star"}[name])
        elif name=="space" and self.tool: self.send("act",a=TOOLS[self.tool])
        elif name=="Escape":
            self.tool=0
            self.goal=None
            self.tour=-1
        self.draw()
        return True

    def draw(self):
        s=self.state
        phase=s.get("time",.2)
        night=s.get("night",False)
        now=time.monotonic()
        scene=night_tint(self.base,phase)
        d=ImageDraw.Draw(scene)
        # Coastal ripples and shifting polar silk.
        for i in range(28):
            tx=(i*13+2)%35; ty=(i*5+1)%18
            if self.rows and self.rows[ty][tx]=="~" and math.sin(now*1.6+i)>.25:
                px=tx*T+4+int(3*math.sin(now*.65+i)); py=ty*T+10
                d.line((px,py,px+4,py),fill="#9bbdb6" if night else "#b0d4bf")
        if s.get("aurora"):
            veil=Image.new("RGBA",scene.size)
            v=ImageDraw.Draw(veil)
            for j,col in enumerate([(128,245,202,65),(193,167,240,62),(244,197,146,52)]):
                pts=[(x,int(15+7*j+12*math.sin(x/100+now*.22)+5*math.sin(x/51))) for x in range(-2,708,5)]
                v.polygon(pts+[(x,y+9) for x,y in reversed(pts)],fill=col)
            scene.paste(veil,(0,0),veil)
        sky=s.get("sky",[])
        if sky and night:
            for i in range(min(len(sky),40)):
                journal.star_shape(d,24+(i*107)%655,6+(i*7)%13,3+(i%2),"#fff0b7")
        objs=s.get("objs",[])
        if night:
            glows=Image.new("RGBA",scene.size)
            g=ImageDraw.Draw(glows)
            for o in objs:
                if o["k"]=="lantern":
                    px=o["x"]*T+10;py=o["y"]*T+7
                    for r,alpha in ((26,25),(19,35),(12,65)):
                        g.ellipse((px-r,py-r,px+r,py+r),fill=(255,209,94,alpha))
            scene.paste(glows,(0,0),glows)
        for o in objs:
            px=o["x"]*T+10;py=o["y"]*T+15
            sprite(d,o["k"],px,py,variant=o["x"]+o["y"])
            if o.get("wet") and o["k"] in ("sprout","bud","flower"):
                d.line((px+4,py+1,px+8,py+1),fill="#a4deda")
        for fx,fy in s.get("flies",[]):
            px=int(fx*T);py=int(fy*T)
            d.ellipse((px-1,py-1,px+1,py+1),fill="#ffffa7")
        for c in s.get("critters",[]):
            if c.get("k")=="fox":
                px=int(c["x"]*T+10); py=int(c["y"]*T+14)
                journal.fox(d,px,py,c.get("mood"))
                txt(d,px,py+3,c.get("name","Fox"),9,"#273e39","bold","mt")
        if s.get("rain"):
            for i in range(48):
                px=(i*101-int(now*23))%700;py=(i*71+int(now*85))%360
                d.line((px,py,px-2,py+5),fill="#afced1")
        if self.goal:
            x,y,_=self.goal
            d.rectangle((x*T+1,y*T+1,x*T+18,y*T+18),outline="#fff3c2",width=2)
        players=s.get("players",{})
        occupied=[]
        for pid,p in sorted(players.items(),key=lambda item:item[1]["y"]):
            px,py=p["x"]*T+10,p["y"]*T+14
            sprite(d,"player",px,py,color=tuple(p["color"]))
            lab=p["name"]+(" •" if pid==self.id else "")
            width=int(font(10,"bold").getlength(lab))+9
            lx,ly=px,py-35
            if any(abs(lx-a)<width+3 and abs(ly-b)<14 for a,b in occupied):
                ly-=15
                d.line((lx,ly+12,lx,py-20),fill=INK)
            occupied.append((lx,ly))
            d.rounded_rectangle((lx-width//2,ly,lx+width//2,ly+13),4,fill=INK)
            txt(d,lx,ly+2,lab,10,PAPER,"bold","mt")
            n=p.get("note",-1)
            if n in range(5):
                txt(d,px+11,py-21,"♫",16,music.COLS[n],"bold")
        for pid,p in players.items():
            words=p.get("say") or {"wave":"Hello!","heart":"♥","laugh":"Ha!","star":"✦"}.get(p.get("emote"),"")
            if words:
                px=p["x"]*T+10;py=max(2,p["y"]*T-40)
                ww=int(font(11).getlength(words))+12
                lx=min(max(2,px-ww//2),698-ww)
                d.rounded_rectangle((lx,py,lx+ww,py+17),4,fill=PAPER,outline=INK)
                txt(d,lx+6,py+2,words,11)
        im=Image.new("RGB",(854,480),PAPER)
        draw=ImageDraw.Draw(im)
        draw.rectangle((0,0,853,49),fill=INK)
        sprite(draw,"lantern",26,36)
        txt(draw,47,8,"Lantern Isle",26,PAPER,"serif")
        txt(draw,236,17,f"[J] NOTES {len(self.seen)}/6",11,"#c6d8b2","mono")
        txt(draw,328,17,"[G] WALK",10,"#c6d8b2","mono")
        txt(draw,389,17,"[M] REEDS",10,GOLD,"mono")
        harmony=s.get("harmony",0)
        txt(draw,471,10,f"CH.{s.get('chapter',1):02d}  HARMONY {harmony}%",10,PAPER,"mono")
        draw.rounded_rectangle((471,29,646,33),2,fill="#456258")
        if harmony: draw.rounded_rectangle((471,29,471+int(harmony*1.75),33),2,fill=GOLD)
        online=self.sock is not None and self.id in players
        draw.rounded_rectangle((688,12,841,37),12,fill="#2a5147",outline="#668577")
        draw.ellipse((700,21,707,28),fill="#bbdc96" if online else GOLD)
        txt(draw,716,18,"LAN Connected" if online else "Joining isle…",12,PAPER,"bold")
        im.paste(scene,(OX,OY))
        draw.rectangle((OX-1,OY-1,OX+700,OY+360),outline="#899a82")
        txt(draw,722,60,"KEEPER  /  "+self.side.upper(),10,MOSS,"mono")
        txt(draw,721,78,self.name,21,INK,"serif")
        p=self.me()
        txt(draw,722,107,f"{p.get('seeds',0)} seeds  ·  {p.get('petals',0)} petals",11,INK)
        draw.line((722,129,842,129),fill="#b6b89f")
        for i,(tool,label) in enumerate(zip(TOOLS,NAMES)):
            y=138+29*i
            chosen=i==self.tool
            draw.rounded_rectangle((719,y,842,y+25),5,fill="#d4dfbf" if chosen else "#e9e5d0",
                                   outline="#7e9776" if chosen else "#d8d6bf")
            sprite(draw,tool,732,y+17)
            txt(draw,746,y+6,label,12,INK,"bold" if chosen else "sans")
            txt(draw,831,y+7,str(i+1),10,MOSS,"mono","mt")
        for x,y,w,label in [(719,350,58,"V Wave"),(782,350,60,"H Heart"),(719,383,123,"↵   Speak")]:
            draw.rounded_rectangle((x,y,x+w,y+26),6,outline="#a8b09a")
            txt(draw,x+w//2,y+7,label,11,INK,"sans","mt")
        draw.line((10,426,842,426),fill="#afb49b")
        if self.chat is not None:
            txt(draw,13,435,("NAME STAR  ›  " if self.renaming is not None else "SAY  ›  ")+self.chat+"▏",15,INK,"bold")
            txt(draw,13,458,"Enter sends  •  Esc cancels",11,MOSS)
        else:
            last=self.note[0] if self.note[1]>now else (s.get("log") or ["Opening the field atlas…"])[-1]
            size=14
            while size>10 and font(size,"bold").getlength(last)>670: size-=1
            while len(last)>3 and font(size,"bold").getlength(last)>670: last=last[:-2]+"…"
            txt(draw,12,434,last,size,INK,"bold")
            txt(draw,12,457,HINTS[self.tool]+"   •   Arrows move   •   1–7 tools   •   Space uses tool here",11,MOSS)
        watch="Needle rain" if s.get("rain") else ("Night watch" if night else "Day watch")
        txt(draw,840,436,watch,13,INK,"serif","rt")
        txt(draw,840,458,f"{s.get('blooms',0)} blooms  /  {len(players)} keepers",10,MOSS,"mono","rt")
        if self.tour>=0 and not self.stand and self.book is None:
            _,title,caption=TOUR[self.tour]
            draw.rounded_rectangle((23,354,421,408),6,fill=INK,outline="#c7c598")
            txt(draw,34,361,f"ISLAND WALK   /   {self.tour+1} OF 5",9,GOLD,"mono")
            txt(draw,410,361,"[G]  "+("FINISH" if self.tour==4 else "NEXT")+"  ›",9,PAPER,"mono","rt")
            txt(draw,34,375,title,14,PAPER,"serif")
            txt(draw,34,393,caption,10,"#c2d5b8")
        if self.book is not None:
            self.star=min(self.star,max(0,len(sky)-1))
            journal.page(draw,self.seen,self.book,self.name,s.get("log",[]),sky,self.star)
        if self.stand: music.stand(draw,s.get("tune",[]),self.bells.sound)
        data=GLib.Bytes.new(im.tobytes())
        pb=GdkPixbuf.Pixbuf.new_from_bytes(data,GdkPixbuf.Colorspace.RGB,False,8,854,480,854*3)
        self.img.set_from_pixbuf(pb)
        return True


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--side",choices=["p1","p2"],default="p2")
    app=Fieldbook(ap.parse_args().side)
    Gtk.main()
