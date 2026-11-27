"""Lantern Isle's tide chart. All the art is painted locally in pixels."""
from functools import lru_cache
from math import sin, pi
from PIL import Image, ImageDraw, ImageFont

W,H=854,480
MX,MY,T=12,67,15
INK="#142d34"; PALE="#e9edd6"; GOLD="#e9be75"; MUTE="#91ada7"
CREW={"p1":"#fd9779","p2":"#83dce7","p3":"#ccafff","sys":"#d9be7d"}
TOOLS=[("Walk","@"),("Grass","."),("Path","="),("Bloom","*"),("Lamp","L"),("Pool","~"),("Wall","#"),("Pine","T"),("Rock","^")]
EMOTES={"wave":"Hi!", "heart":"♥", "dance":"♪", "sleep":"Zz", "!":"!", "?":"?"}

@lru_cache(None)
def face(size,typ="sans"):
    fam={"sans":"DejaVuSans","bold":"DejaVuSans-Bold","serif":"DejaVuSerif","mono":"DejaVuSansMono"}[typ]
    return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/"+fam+".ttf",size)

def txt(d,xy,s,size=12,color=PALE,typ="sans",anchor=None):
    d.text(xy,str(s),font=face(size,typ),fill=color,anchor=anchor)

def tile(d,x,y,c,n,night=False):
    r=d.rectangle; p=d.polygon; l=d.line
    i=n%3
    soil=["#81a878","#83ab7a","#87ad7e"][i] if not night else ["#42665e","#46685e","#466b61"][i]
    if c=="~":
        r((x,y,x+14,y+14),fill=(["#356b78","#356b78","#386e79"] if not night else ["#284953","#284953","#2a4e57"])[i])
        if n%5<2:
            a=x+2+n%3; b=y+4+n%6
            l([(a,b),(a+2,b+1),(a+6,b+1),(a+8,b)],fill="#558992" if not night else "#3e656d")
        return
    r((x,y,x+14,y+14), fill=soil)
    if n%3!=0:
        a=x+2+n%8;b=y+3+n%7
        l([(a,b),(a+1,b+2),(a+3,b-1)],fill="#719366" if not night else "#3a5b54")
    if c=="=":
        r((x,y,x+14,y+14),fill="#cfb886" if not night else "#8b806b")
        for j in range(2):
            a=x+(n+j*4)%12;b=y+2+(n*3+j*7)%11
            l((a,b,a+2,b),fill="#ad986f" if not night else "#706e61")
    elif c=="L":
        if night: d.ellipse((x,y,x+14,y+14),fill="#7a825d")
        r((x+6,y+7,x+8,y+12),fill="#514947");r((x+4,y+12,x+10,y+13),fill="#5f5953")
        r((x+4,y+4,x+10,y+9),fill="#705644");r((x+5,y+5,x+9,y+8),fill="#ffdf87")
        l((x+7,y+5,x+7,y+8),fill="#fff2b7")
        p([(x+3,y+4),(x+7,y),(x+11,y+4)],fill="#614b4a")
    elif c=="T":
        r((x+6,y+9,x+8,y+13),fill="#785f47")
        p([(x+7,y),(x+12,y+8),(x+10,y+8),(x+14,y+12),(x+1,y+12),(x+4,y+7),(x+3,y+7)],fill="#285849")
        p([(x+7,y+1),(x+7,y+5),(x+5,y+6),(x+7,y+7),(x+4,y+10),(x+2,y+11)],fill="#50846a")
    elif c=="^":
        p([(x+1,y+10),(x+4,y+5),(x+9,y+3),(x+13,y+7),(x+14,y+11),(x+9,y+13),(x+3,y+13)],fill="#56666c")
        p([(x+2,y+10),(x+5,y+5),(x+9,y+4),(x+11,y+7),(x+7,y+10)],fill="#a3b1ab")
    elif c=="#":
        r((x,y+3,x+14,y+13), fill="#556268");r((x+1,y+3,x+7,y+6),fill="#abb0a1")
        r((x+9,y+3,x+14,y+6),fill="#98a397");r((x,y+8,x+3,y+11),fill="#8b978e")
        r((x+5,y+8,x+12,y+11),fill="#8f9e94")
    elif c=="*":
        for a,b in [(x+5,y+6),(x+10,y+10)]:
            l((a,b+1,a,b+4),fill="#427957")
            l((a-2,b,a+2,b),fill="#ffb49f");l((a,b-2,a,b+2),fill="#f8b1ae");d.point((a,b),fill="#ffe3a2")

@lru_cache(4)
def land(rows,night):
    im=Image.new("RGB",(600,300),"#386e79");d=ImageDraw.Draw(im)
    for j,row in enumerate(rows):
        for i,c in enumerate(row):
            x,y=i*T,j*T
            tile(d,x,y,c,(i*73856093 ^ j*19349663)%10037,night)
    for j,row in enumerate(rows):
        for i,c in enumerate(row):
            if c=="~":continue
            x,y=i*T,j*T
            for dx,dy,a,b,cc in [(0,-1,(x,y-1),(x+14,y-1),"#a7c8a8"),(-1,0,(x-1,y),(x-1,y+14),"#91b59e"),(0,1,(x,y+15),(x+14,y+15),"#588681"),(1,0,(x+15,y),(x+15,y+14),"#5f9085")]:
                ni,nj=i+dx,j+dy
                if 0<=ni<40 and 0<=nj<20 and rows[nj][ni]=="~":
                    d.line([a,b],fill=cc if not night else "#537774")
    return im

def star(d,x,y,r,color):
    d.polygon([(x,y-r),(x+1,y-1),(x+r,y),(x+1,y+1),(x,y+r),(x-1,y+1),(x-r,y),(x-1,y-1)],fill=color)

@lru_cache(500)
def lines(s,width):
    f=face(12);out=[];cur=""
    for w in s.split():
        test=(cur+" "+w).strip()
        if cur and f.getlength(test)>width:out.append(cur);cur=w
        else:cur=test
        while f.getlength(cur)>width:
            n=min(len(cur),max(1,int(len(cur)*width/f.getlength(cur))))
            out.append(cur[:n]);cur=cur[n:]
    return out+[cur]

def journal(d,box,msgs,scroll):
    x,y,r,b=box
    yy=b-3; buf=[]
    for m in reversed(msgs[max(0,len(msgs)-40):len(msgs)-scroll if scroll else None]):
        who=m.get("from","sys");tag=who.upper() if who in CREW and who!="sys" else "ISLE"
        ll=lines(m.get("text",""),r-x-12)
        top=yy-16*len(ll)-16
        if top<y and buf:break
        buf.append((max(y,top),tag,who,ll));yy=top-5
        if top<y:break
    for top,tag,who,ll in reversed(buf):
        txt(d,(x,top),tag,9,CREW.get(who,GOLD),"bold")
        for j,s in enumerate(ll):
            if top+14+j*16<=b-12:txt(d,(x,top+12+j*16),s,12)

def paint(v,tm):
    img=Image.new("RGB",(W,H),"#112a32"); d=ImageDraw.Draw(img)
    d.rectangle((0,0,W,54),fill="#1e3e46"); d.line((0,54,W,54),fill="#506663")
    # A copper lighthouse seal.
    d.ellipse((13,8,51,46),outline=GOLD,width=1)
    d.polygon([(23,38),(27,25),(36,25),(40,38)],fill="#dfc592");d.rectangle((27,19,36,24),fill="#ffd986")
    d.polygon([(23,19),(32,12),(40,19)],fill="#eea37f");d.line((18,38,45,38),fill="#9cbbaf")
    txt(d,(63,3),"Lantern Isle",26,PALE,"serif");txt(d,(65,37),"A   C O O P E R A T I V E   T I D E   A T L A S",9,MUTE,"bold")
    score=v.state.get("score",0); goal=v.state.get("goal",25) or 25
    star(d,358,26,8,GOLD);txt(d,(375,9),f"{score:02d}  /  {((score//goal)+1)*goal:02d}",15,PALE,"mono")
    txt(d,(375,32),"TEAM SPARKS",9,MUTE,"bold")
    night=v.state.get("clock",0)>.5
    txt(d,(536,11),"NIGHT WATCH" if night else "DAY WATCH",11,GOLD,"bold")
    txt(d,(536,29),f"KEEPER  {v.side.upper()}",10,CREW[v.side],"mono")
    d.rounded_rectangle((706,12,841,41),13,fill="#254d49" if v.online else "#584b3d",outline="#52796c")
    d.ellipse((718,24,724,30),fill="#a7e3b2" if v.online else GOLD)
    txt(d,(731,18),"LAN Connected" if v.online else "Joining isle…",12,PALE,"bold")
    d.rectangle((MX-2,MY-2,MX+601,MY+301),outline="#819788",width=2)
    img.paste(land(tuple(v.rows),night),(MX,MY))
    for x,y in v.state.get("sparks",[]):
        a,b=MX+x*T+7,MY+y*T+7;rad=4+int(1.5*(1+sin(tm*4+x)))
        star(d,a,b,rad+1,"#856a48");star(d,a,b,rad,"#ffe58e");d.point((a,b),fill="white")
    if v.dest:
        x,y=v.dest; a,b=MX+x*T+2,MY+y*T+2
        d.ellipse((a,b,a+10,b+10),outline=GOLD,width=2)
    players=v.state.get("players",{})
    for side,p in players.items():
        if not p.get("online",True):continue
        x,y=MX+p["x"]*T+7,MY+p["y"]*T+8;col=CREW.get(side,GOLD)
        d.ellipse((x-6,y+3,x+6,y+7),fill="#57715f")
        d.rectangle((x-3,y+2,x+3,y+5),fill="#354249")
        d.polygon([(x-3,y-2),(x+3,y-2),(x+5,y+3),(x-5,y+3)], fill=col,outline=INK)
        d.rectangle((x-2,y-7,x+2,y-3),fill="#e9bc8d")
        d.polygon([(x-5,y-6),(x-2,y-10),(x+2,y-10),(x+5,y-6)], fill=col,outline=INK)
        label=EMOTES.get(p.get("emote"),side.upper())
        ly=y-25 if y>MY+23 else y+7
        width=int(face(9,"bold").getlength(label))+7
        d.rounded_rectangle((x-width//2,ly,x+width//2,ly+12),3,fill=INK)
        txt(d,(x,ly+6),label,9,col,"bold","mm")
    if v.hover and not v.expanded:
        x,y=v.hover;a,b=MX+x*T,MY+y*T
        d.rectangle((a,b,a+14,b+14),outline="#f8dc95")
    # Crew and the field journal.
    sx=627
    txt(d,(sx,64),"SHIP'S COMPANY",10,GOLD,"bold")
    for ix,side in enumerate(CREW):
        if side=="sys":continue
        x=sx+ix*73;active=players.get(side,{}).get("online",False)
        d.ellipse((x,89,x+7,96),fill=CREW[side] if active else "#526469");txt(d,(x+12,83),side.upper(),13,PALE if active else MUTE,"bold")
    d.line((sx,109,841,109),fill="#466064")
    txt(d,(sx,117),"Crew journal",18,PALE,"serif");txt(d,(840,125),"[TAB]",10,MUTE,"mono","rm")
    journal(d,(sx,146,842,395),v.log,v.scroll)
    txt(d,(sx,405),"Scroll history   ·   Tab to enlarge",10,MUTE)
    for i,(name,c) in enumerate(TOOLS):
        x=MX+i*67
        d.rounded_rectangle((x,378,x+63,402),5,fill="#536456" if v.tool==i else "#23414a",outline=GOLD if v.tool==i else "#3d5b5e")
        if c=="@":txt(d,(x+4,382),"↗",12,GOLD)
        else:tile(d,x+4,383,c,3,night)
        txt(d,(x+21,383),name,11)
    txt(d,(MX,408),v.notice if tm<v.notice_until else "Click to walk   ·   1–8 tools   ·   Esc walk   ·   F1–6 emotes   ·   Enter chat",11,GOLD if tm<v.notice_until else MUTE)
    if v.expanded:
        d.rounded_rectangle((25,74,599,360),8,fill="#1a363f",outline=GOLD)
        txt(d,(41,84),"The crew journal",20,PALE,"serif");txt(d,(582,94),"SCROLL  /  TAB TO CLOSE",10,MUTE,"mono","rm")
        journal(d,(42,119,582,349),v.log,v.scroll)
    d.line((0,430,W,430),fill="#4c6769");txt(d,(12,447),"RADIO",11,GOLD,"bold")
    return img
