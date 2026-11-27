#!/usr/bin/env python3
"""The shared Lantern Isle chart and radio console."""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import queue
import select
import socket
import threading
import time
import gi
gi.require_version("Gtk","3.0")
gi.require_version("Gdk","3.0")
gi.require_version("GdkPixbuf","2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from atlas import W,H,MX,MY,T,TOOLS,paint

NAMES={"p1":"Coral","p2":"Tide","p3":"Lilac"}
WALK=set(".=*L")
class Client:
    def __init__(self,side):
        self.side=side;self.online=False;self.run=True
        self.state={};self.rows=["~"*40 for _ in range(20)];self.log=[]
        self.tx=queue.Queue();self.rx=queue.Queue();self.tool=0;self.hover=None
        self.expanded=False;self.scroll=0;self.notice="";self.notice_until=0
        self.dest=None;self.last_step=0;self.steps=0;self.prev=None
        win=self.win=Gtk.Window(title="Lantern Isle · Keeper "+side.upper())
        win.set_default_size(854,480);win.set_resizable(False);win.set_position(Gtk.WindowPosition.CENTER)
        fixed=Gtk.Fixed();win.add(fixed);image=self.image=Gtk.Image()
        area=self.area=Gtk.EventBox();area.set_can_focus(True);area.add(image)
        area.set_size_request(W,H);fixed.put(area,0,0)
        area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.POINTER_MOTION_MASK|Gdk.EventMask.SCROLL_MASK)
        area.connect("button-press-event",self.click);area.connect("motion-notify-event",self.motion)
        area.connect("scroll-event",self.wheel)
        entry=self.entry=Gtk.Entry();entry.set_width_chars(35);entry.set_size_request(697,33)
        entry.set_max_length(200);entry.set_placeholder_text("Message everyone on the isle…   [Enter]")
        entry.set_name("radioentry");entry.connect("activate",self.say);fixed.put(entry,68,438)
        send=Gtk.Button(label="Send  ↵");send.set_size_request(71,33);send.connect("clicked",self.say);send.set_name("radiosend");fixed.put(send,771,438)
        css=Gtk.CssProvider();css.load_from_data(b"""
          #radioentry {background:#213e47;color:#f3edd8; border:1px solid #597276;border-radius:5px;min-height:25px;padding:1px 9px;font:13px Sans;}
          #radiosend {background:#e1bc7d;color:#21383e;border:0;border-radius:5px;min-height:25px;padding:2px 5px;font:bold 13px Sans;}
        """)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win.connect("key-press-event",self.key);win.connect("destroy",self.close)
        win.show_all();area.grab_focus();self.render()
        GLib.timeout_add(125,self.tick)
        threading.Thread(target=self.network,daemon=True).start()

    def network(self):
        addr=(os.environ["AAL_LAN_HOST"],int(os.environ.get("AAL_LAN_PORT","18765")))
        while self.run:
            try:
                with socket.create_connection(addr,timeout=3) as s:
                    s.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                    def publish(m):s.sendall((json.dumps(m)+"\n").encode())
                    publish({"t":"hello","side":self.side,"name":NAMES[self.side]})
                    buf=b""
                    while self.run:
                        while not self.tx.empty():publish(self.tx.get_nowait())
                        if not select.select([s],[],[],.035)[0]:continue
                        data=s.recv(32768)
                        if not data:break
                        buf+=data
                        while b"\n" in buf:
                            msg,buf=buf.split(b"\n",1);self.rx.put(json.loads(msg))
            except (OSError,ValueError):pass
            self.rx.put({"t":"disconnected"})
            while not self.tx.empty():self.tx.get_nowait()
            if self.run:threading.Event().wait(1)

    def close(self,*_):self.run=False;Gtk.main_quit()
    def send(self,t,**kw):
        if self.online:self.tx.put(dict(t=t,**kw))
    def hint(self,s):
        self.notice=s;self.notice_until=time.monotonic()+3
    def say(self,*_):
        text=self.entry.get_text().strip()
        if text and self.online:
            self.send("chat",text=text);self.entry.set_text("");self.scroll=0
        elif text:self.hint("Radio waiting for a connection.");return
        self.area.grab_focus()
    def key(self,_,ev):
        k=Gdk.keyval_name(ev.keyval)
        if self.entry.is_focus():
            if k=="Escape":self.area.grab_focus();return True
            return False
        if k in ("Return","KP_Enter","slash","t"):self.entry.grab_focus();return True
        if k in ("Tab","ISO_Left_Tab"):self.expanded=not self.expanded;self.scroll=0;return True
        if k=="Escape":self.tool=0;self.expanded=False;self.dest=None;return True
        if k=="F9":
            self.save_chart();return True
        if k in "012345678" and len(k)==1:self.tool=int(k);self.dest=None;return True
        if k in ("F1","F2","F3","F4","F5","F6"):
            self.send("emote",e=["wave","heart","dance","sleep","!","?"][int(k[1:])-1]);return True
        if k in ("Page_Up","Page_Down"):
            self.scroll=max(0,min(self.scroll+(2 if k=="Page_Up" else -2),len(self.log)-1));return True
        moves={"w":(0,-1),"Up":(0,-1),"s":(0,1),"Down":(0,1),"a":(-1,0),"Left":(-1,0),"d":(1,0),"Right":(1,0)}
        if k in moves:
            self.dest=None;dx,dy=moves[k];self.send("move",dx=dx,dy=dy);return True
        return False
    def save_chart(self):
        if not self.online:self.hint("Join the isle before saving the chart.");return
        chart={"title":"Lantern Isle","version":1,"w":40,"h":20,
               "tiles":self.rows,"score":self.state.get("score",0),
               "sparks":self.state.get("sparks",[])}
        try:
            home=Path.home()/".local"/"share"/"lantern-isle";home.mkdir(parents=True,exist_ok=True)
            dest=home/(self.side+"-chart.json");tmp=dest.with_suffix(".tmp")
            tmp.write_text(json.dumps(chart,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            tmp.replace(dest);self.hint("Chart saved at this watch, including terrain and sparks.")
        except OSError:self.hint("Could not save this chart.")
    def wheel(self,_,ev):
        self.scroll=max(0,min(len(self.log)-1,self.scroll+(1 if ev.direction==Gdk.ScrollDirection.UP else -1)));return True
    def motion(self,_,ev):
        x,y=int(ev.x-MX)//T,int(ev.y-MY)//T
        self.hover=(x,y) if 0<=x<40 and 0<=y<20 else None
    def click(self,_,ev):
        self.area.grab_focus();a,b=ev.x,ev.y
        if self.expanded:
            self.expanded=False;self.scroll=0;return True
        if a>623 and 110<b<404:self.expanded=True;self.scroll=0;return True
        if MX<=a<MX+603 and 377<=b<=404:
            self.tool=min(8,int((a-MX)//67));self.dest=None;return True
        x,y=int((a-MX)//T),int((b-MY)//T)
        if 0<=x<40 and 0<=y<20:
            if self.tool or ev.button==3:
                self.dest=None;self.send("place",x=x,y=y,tile="." if ev.button==3 else TOOLS[self.tool][1])
            else:self.dest=(x,y);self.prev=None;self.steps=0
        return True
    def walk(self,tm):
        if not self.dest or tm-self.last_step<.19:return
        p=self.state.get("players",{}).get(self.side)
        if not p:return
        pos=(p["x"],p["y"])
        if pos==self.dest:self.dest=None;return
        if self.prev==pos:self.steps+=1
        else:self.steps=0
        if self.steps>4:self.hint("Route paused. Pick a clear tile.");self.dest=None;return
        self.prev=pos;self.last_step=tm
        q=deque([(pos,None)]);seen={pos}
        while q:
            (x,y),first=q.popleft()
            for dx,dy in [(0,-1),(1,0),(0,1),(-1,0)]:
                n=(x+dx,y+dy)
                if n in seen or not (0<=n[0]<40 and 0<=n[1]<20) or self.rows[n[1]][n[0]] not in WALK:continue
                step=first or (dx,dy)
                if n==self.dest:self.send("move",dx=step[0],dy=step[1]);return
                seen.add(n);q.append((n,step))
        self.hint("No walking route. Lay a path to cross water.");self.dest=None
    def tick(self):
        while not self.rx.empty():
            m=self.rx.get_nowait();t=m.get("t")
            if t=="welcome":
                if not self.online:print("PHASE: LAN CONNECTED",flush=True)
                self.online=True;self.rows=list(m["tiles"]);self.log=list(m.get("chat",[]));self.state=m;self.scroll=0
            elif t=="state":self.state.update(m)
            elif t=="tile":
                x,y=m["x"],m["y"];r=self.rows[y];self.rows[y]=r[:x]+m["tile"]+r[x+1:]
            elif t=="chat":
                self.log=(self.log+[m])[-160:]
                if self.scroll:self.scroll+=1
            elif t=="err":self.hint(m.get("text","Action unavailable."))
            elif t=="disconnected":self.online=False;self.dest=None
        tm=time.monotonic();self.walk(tm);self.render();return True
    def render(self):
        im=paint(self,time.monotonic())
        buf=GLib.Bytes.new(im.tobytes())
        pix=GdkPixbuf.Pixbuf.new_from_bytes(buf,GdkPixbuf.Colorspace.RGB,False,8,W,H,W*3)
        self.image.set_from_pixbuf(pix)

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--side",choices=NAMES,required=True)
    app=Client(ap.parse_args().side);Gtk.main()
