#!/usr/bin/env python3
"""Emberglow Isle: a native, two-keeper LAN field atlas."""
import argparse
from collections import deque
import json
import os
import socket
import threading
import time

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from atlas import cell, render


class Atlas:
    def __init__(self, side):
        self.side=side
        self.endpoint=(os.environ.get("AAL_LAN_HOST", "localhost"),int(os.environ.get("AAL_LAN_PORT","18765")))
        self.sock=None
        self.tiles=[];self.state={};self.myid=None;self.linked=False
        self.notice="";self.until=0;self.edit="";self.draft="";self.emote=0;self.page=0
        self.path=deque();self.target=None;self.last_step=0
        self.stopped=threading.Event()
        win=Gtk.Window(title="Emberglow Isle — "+("Wick" if side=="p2" else "Moss"))
        win.set_default_size(854, 480)
        win.set_resizable(False)
        win.set_position(Gtk.WindowPosition.CENTER)
        win.set_decorated(False)
        self.image=Gtk.Image()
        box=Gtk.EventBox();box.add(self.image);win.add(box)
        box.connect("button-press-event",self.click)
        win.connect("key-press-event",self.key)
        win.connect("destroy",lambda *_:(self.stopped.set(),Gtk.main_quit()))
        self.win=win
        self.draw();win.show_all()
        GLib.timeout_add(95,self.draw)
        threading.Thread(target=self.network,daemon=True).start()

    def network(self):
        keeper=self.side=="p2"
        hello=dict(t="join",name="Wick" if keeper else "Moss",role="keeper" if keeper else "gardener",
                   kind="moth" if keeper else "golem",color="#5b2a6e" if keeper else "#6fbf5a")
        while not self.stopped.is_set():
            try:
                with socket.create_connection(self.endpoint,timeout=3) as s:
                    s.settimeout(None);s.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                    s.sendall((json.dumps(hello)+"\n").encode())
                    self.sock=s
                    with s.makefile("rb") as f:
                        for line in f:
                            GLib.idle_add(self.receive,json.loads(line))
                            if self.stopped.is_set():return
            except (OSError,ValueError):pass
            self.sock=None;GLib.idle_add(self.disconnect);self.stopped.wait(1.5)

    def receive(self,m):
        t=m.get("t")
        if t=="welcome":self.tiles=m["tiles"];self.myid=m["id"];self.linked=True
        elif t=="state":self.state=m
        elif t=="error":self.flash(m.get("msg","Try a different spot."))
        return False

    def disconnect(self):
        self.linked=False;self.path.clear();self.target=None
        return False

    def send(self,**msg):
        if self.sock and self.linked:
            try:self.sock.sendall((json.dumps(msg)+"\n").encode())
            except OSError:self.disconnect()

    def flash(self,message):
        self.notice=message;self.until=time.monotonic()+3.5

    def draw(self):
        now=time.monotonic()
        if self.path and now-self.last_step>.13:
            dx,dy=self.path.popleft();self.send(t="move",dx=dx,dy=dy);self.last_step=now
            if not self.path:self.target=None
        im=render(self.side,self.tiles,self.state,self.myid,self.linked,now,
                  self.notice if self.until>now else "",self.edit,self.draft,self.target,self.page)
        data=GLib.Bytes.new(im.tobytes())
        pix=GdkPixbuf.Pixbuf.new_from_bytes(data,GdkPixbuf.Colorspace.RGB,False,8,854,480,854*3)
        self.image.set_from_pixbuf(pix)
        return True

    def walkto(self,dest):
        p=next((p for p in self.state.get("players",[]) if p["id"]==self.myid),None)
        if not p:return
        self.path.clear();self.target=None
        x,y=dest
        if not (0<=y<len(self.tiles) and 0<=x<len(self.tiles[y]) and self.tiles[y][x] in ".sp"):
            self.flash("Choose grass, sand or a trail to walk.");return
        start=p["x"],p["y"];prev={start:None};q=deque([start])
        while q:
            a,b=q.popleft()
            if (a,b)==dest:break
            for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]:
                n=a+dx,b+dy;u,v=n
                if 0<=v<len(self.tiles) and 0<=u<len(self.tiles[v]) and self.tiles[v][u] in ".sp" and n not in prev:
                    prev[n]=(a,b);q.append(n)
        n=dest
        if n not in prev:return
        while prev[n] is not None:
            u,v=prev[n];self.path.appendleft((n[0]-u,n[1]-v));n=u,v
        self.target=dest if self.path else None

    def action(self,k):
        self.path.clear();self.target=None
        if k=="n":self.edit="note";self.draft=""
        elif k=="v":self.edit="verses";self.page=0
        elif k=="p":self.edit="petals"
        elif k=="j":self.edit="journal"
        elif k=="h":
            self.send(t="act",a="emote",e=("wave","heart","dance","glow")[self.emote%4]);self.emote+=1
        elif k=="r":self.send(t="act",a="ring")
        elif k in ("e","space"):self.send(t="act",a="primary")

    def click(self,_box,e):
        if self.edit:
            if self.edit=="verses":
                notes=self.state.get("notes",[])
                if 350<=e.x<=776 and 119<=e.y<315:
                    i=self.page*4+int((e.y-119)//49)
                    if i<len(notes):
                        self.edit="";self.walkto((notes[i]["x"],notes[i]["y"]))
                elif 315<=e.y<=352 and e.x>350:self.turn_page(1 if e.x>550 else -1)
                elif 75<=e.x<=306 and 174<=e.y<=294 and notes:
                    i=min(range(len(notes)),key=lambda i:(87+9*notes[i]["x"]-e.x)**2+(189+8*notes[i]["y"]-e.y)**2)
                    self.page=i//4;self.edit="";self.walkto((notes[i]["x"],notes[i]["y"]))
                else:self.edit=""
            elif self.edit=="petals":
                if e.y>319 and 540<e.x<690:self.action("v")
                else:self.edit=""
            elif self.edit=="journal":
                if e.y>296 and e.x<350:self.action("v")
                else:self.edit=""
            return True
        if 415<=e.y<=451:
            idx=int((e.x-16)//116)
            if 0<=idx<5 and (e.x-16)%116<=108:self.action("erhnj"[idx])
        elif 56<e.y<379:self.walkto(cell(e.x,e.y))
        elif e.y>=454 and e.x>=654:self.action("v")
        elif e.y>=454 and e.x>=520:self.action("p")
        return True

    def turn_page(self,n):
        last=max(0,(len(self.state.get("notes",[]))-1)//4)
        self.page=(self.page+n)%(last+1)

    def key(self,_win,e):
        k=(Gdk.keyval_name(e.keyval) or "").lower()
        if self.edit:
            if self.edit=="note":
                if k=="backspace":self.draft=self.draft[:-1]
                elif k in ("return","kp_enter"):
                    if self.draft.strip():self.send(t="act",a="note",text=self.draft)
                    self.edit=""
                elif k=="escape":self.edit=""
                elif len(self.draft)<40 and e.string and e.string.isprintable():self.draft+=e.string
            elif self.edit=="verses":
                if k in ("right","pagedown"):self.turn_page(1)
                elif k in ("left","pageup"):self.turn_page(-1)
                elif k=="p":self.action("p")
                elif k in ("v","escape","return"):self.edit=""
            elif self.edit=="petals":
                if k=="v":self.action("v")
                elif k in ("p","escape","return"):self.edit=""
            elif k=="v":self.action("v")
            elif k in ("j","escape","return"):self.edit=""
            return True
        dirs={"left":(-1,0),"a":(-1,0),"right":(1,0),"d":(1,0),
              "up":(0,-1),"w":(0,-1),"down":(0,1),"s":(0,1)}
        if k in dirs:
            self.path.clear();self.target=None;dx,dy=dirs[k];self.send(t="move",dx=dx,dy=dy)
        else:self.action(k)
        return True


if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("--side",choices=["p1","p2"],required=True)
    app=Atlas(cli.parse_args().side)
    Gtk.main()
