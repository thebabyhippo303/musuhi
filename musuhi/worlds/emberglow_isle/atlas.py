"""The living field chart of Emberglow Isle, painted at native window size."""
import math
import random
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont
from illustrations import sprite


@lru_cache(None)
def font(size=13, style="body"):
    file = {"title":"dejavu/DejaVuSerif-Bold","body":"dejavu/DejaVuSans",
            "bold":"dejavu/DejaVuSans-Bold","mono":"dejavu/DejaVuSansMono"}[style]
    return ImageFont.truetype("/usr/share/fonts/truetype/"+file+".ttf", size)


def text(d, xy, s, size=13, color="#faf1db", style="body", anchor="lm"):
    d.text(xy, str(s), font=font(size,style), fill=color, anchor=anchor)


def pos(x,y):
    return 43+32*x+2*(y-5), 87+24*y


def cell(px,py):
    y=round((py-87)/24)
    return round((px-43-2*(y-5))/32),y


def tree(d,x,y):
    d.ellipse((x-13,y-3,x+14,y+6),fill="#263f49")
    d.rectangle((x-3,y-13,x+3,y+1),fill="#75565d")
    for dx,dy,w,h,c in [(1,-15,13,17,"#244454"),(-2,-22,12,18,"#326359"),
                        (0,-29,9,15,"#4a8771"),(-1,-35,5,8,"#74aa83")]:
        x1,y1=x+dx,y+dy
        d.polygon([(x1,y1-h//2),(x1+w,y1+h//2),(x1+4,y1+h//2-1),
                   (x1,y1+h//2+2),(x1-w,y1+h//2)],fill=c)


def bell(d,x,y):
    d.ellipse((x-18,y-5,x+18,y+7),fill="#384a54")
    d.polygon([(x-16,y-1),(x+13,y-2),(x+18,y+2),(x-13,y+4)],fill="#afa18c")
    for k in [-12,11]:
        d.rectangle((x+k-2,y-25,x+k+1,y-1),fill="#513e4e")
        d.line((x+k-2,y-24,x+k-2,y-2),fill="#bb8269")
    d.polygon([(x-20,y-24),(x-14,y-28),(x,y-33),(x+17,y-28),(x+20,y-25),(x+3,y-25),(x-10,y-22)], fill="#7c5866")
    d.line((x-17,y-26,x,y-32,x+17,y-27), fill="#e0bc88",width=2)
    d.rectangle((x-1,y-25,x+1,y-21),fill="#fad894"); d.ellipse((x-6,y-22,x+6,y-9),fill="#ebb568")
    d.polygon([(x-5,y-17),(x+5,y-17),(x+8,y-9),(x-8,y-9)],fill="#daa55e")
    d.ellipse((x-8,y-11,x+8,y-8),fill="#f9d88b"); d.ellipse((x-2,y-9,x+2,y-6),fill="#875763")


@lru_cache(maxsize=5)
def base(tiles, sky):
    im=Image.new("RGB",(854,480),"#131e30")
    d=ImageDraw.Draw(im)
    rng=random.Random(23)
    top={"dusk":(51,63,102),"starlit":(42,57,97),"aurora":(53,90,106),"dawnsong":(109,80,108)}.get(sky,(51,63,102))
    for y in range(56,386):
        f=(y-56)/330
        c=tuple(int(a*(1-f)+b*f) for a,b in zip(top,(30,64,83)))
        d.line((0,y,853,y),fill=c)
    for i in range(640):
        x,y=rng.randrange(854),rng.randrange(56,386)
        d.line((x,y,x+rng.randrange(2,19),y), fill=rng.choice(("#416480","#426882","#3b5770")))
    if sky!="dusk":
        if sky in ("aurora","dawnsong"):
            veil=Image.new("RGBA",im.size);v=ImageDraw.Draw(veil)
            for x in range(854):
                shelf=66+8*math.sin(x/113)+7*math.cos(x/67)
                colors=((137,230,180),(135,171,219)) if sky=="aurora" else ((255,203,147),(250,155,164))
                for k,c in enumerate(colors):
                    h=12+int(8*math.sin(x/72+k)+5*math.cos(x/39))
                    v.line((x,int(shelf+6*k),x,int(shelf+6*k+h)),fill=(*c,40-k*12))
            im.paste(veil,(0,0),veil)
        for _ in range(50):
            x,y=rng.randrange(854),rng.randrange(58,111)
            d.point((x,y),fill="#ffdfb5")
    # Star compass in the margin.
    text(d,(829,75),"N",10,"#ccb9bd","mono","mm")
    d.polygon([(829,83),(825,99),(829,95),(833,99)], fill="#ccb9bd")
    for border,c in [(8,"#577c85"),(4,"#a59c92"),(1,"#514e60"),(0,None)]:
        for j,row in enumerate(tiles):
            for i,t in enumerate(row):
                if t=="~":continue
                x,y=pos(i,j)
                land={"s":["#c3ad8b","#c8b291"],"p":["#aa9380","#ae9684"]}.get(t,["#628d79","#658f7b","#67917d"])
                color=c or land[(i*7+j*11)%len(land)]
                d.rounded_rectangle((x-17-border,y-13-border,x+17+border,y+13+border),radius=5+border,fill=color)
    for j,row in enumerate(tiles):
        for i,t in enumerate(row):
            if t=="~":continue
            x,y=pos(i,j)
            for k in range(rng.randrange(2,5)):
                dx,dy=x+rng.randrange(-13,13),y+rng.randrange(-9,10)
                if t=='s' or t=='p':
                    d.line((dx,dy,dx+2,dy), fill="#d9c5a2" if t=="s" else "#c2ab97")
                else:
                    d.line((dx-2,dy-2,dx,dy,dx+1,dy-3),fill=rng.choice(("#84a888","#749d83","#537f70")))
    return im


def rock(d,x,y):
    d.ellipse((x-13,y-4,x+13,y+5),fill="#476a67")
    d.polygon([(x-12,y+1),(x-10,y-8),(x-3,y-14),(x+6,y-12),(x+12,y-4),(x+8,y+1)],fill="#536777")
    d.polygon([(x-11,y-5),(x-8,y-10),(x-2,y-14),(x+5,y-12),(x+2,y-8)],fill="#99aba7")


SPECIMENS={
    "dusk":("Hemrose","Five coral petals","#ffb3a4","#ffda91"),
    "starlit":("Starspool","A six-pointed star","#d8cefc","#fff6bd"),
    "aurora":("Tideglass","Three glass drops","#9de2cf","#d4f4b0"),
    "dawnsong":("Horn of day","A fluted trumpet","#ffcf79","#fff3b7"),
    "":("Unrecorded","Opening sky unknown","#e6b7bb","#fbe4a3"),
}


def plant(d,x,y,stage,hue=""):
    if stage==0:
        d.ellipse((x-4,y-2,x+4,y+2),fill="#695450"); d.point((x,y-1),fill="#fae0a1");return
    h=4+3*stage
    d.line((x,y,x,y-h),fill="#315d51",width=2)
    d.polygon([(x,y-3),(x-6,y-8),(x-1,y-7)],fill="#9cc774")
    d.polygon([(x,y-5),(x+6,y-10),(x+3,y-5)],fill="#b5db8d")
    if stage==2:d.ellipse((x-2,y-h-2,x+2,y-h+2),fill="#eca58f")
    if stage>=3:
        name,_,c,core=SPECIMENS.get(hue,SPECIMENS[""]);b=y-h
        if hue=="starlit":
            for dx,dy in [(0,-6),(5,-3),(5,3),(0,6),(-5,3),(-5,-3)]:
                d.polygon([(x-2,b-1),(x+dx,b+dy),(x+2,b+1)],fill=c)
        elif hue=="aurora":
            for dx,dy in [(-4,-1),(0,-4),(4,-1)]:
                d.polygon([(x,b+4),(x+dx-2,b+dy),(x+dx,b+dy-3),(x+dx+2,b+dy)],fill=c)
        elif hue=="dawnsong":
            d.polygon([(x-2,b+5),(x-6,b-4),(x-2,b-1),(x,b-6),(x+2,b-2),(x+6,b-5),(x+2,b+4)],fill=c)
            d.line((x-2,b+3,x,b+5,x+2,b+3),fill="#e5a16c")
        else:
            for dx,dy in [(0,-3),(3,-1),(2,3),(-2,3),(-3,-1)]:
                d.ellipse((x+dx-2,b+dy-2,x+dx+2,b+dy+2),fill=c)
        d.ellipse((x-1,b-1,x+1,b+1),fill=core)


@lru_cache(None)
def specimen_stamp(hue):
    im=Image.new("RGBA",(32,33));plant(ImageDraw.Draw(im),16,27,3,hue)
    return im.resize((96,99),Image.Resampling.NEAREST)


def herbarium(im,d,state):
    ink="#383c46";sub="#615e5a"
    d.rounded_rectangle((54,68,800,365),radius=11,fill="#f0e5c8",outline="#b69e77",width=3)
    text(d,(77,94),"PLATE  02      /      EMBERGLOW BOTANICAL SURVEY",10,sub,"mono")
    text(d,(77,128),"An almanac in petals",24,ink,"title")
    recalled=sum(bool(p.get("recalled")) and p["stage"]>=3 for p in state.get("plants",[]))
    caption=(f"{recalled} early colors were reconstructed by garden. All later opening skies were recorded at bloom."
             if recalled else "Each recorded blossom carries the shape of its opening sky.")
    text(d,(77,154),caption,13,sub)
    for i,(hue,(name,detail,c,_)) in enumerate(SPECIMENS.items()):
        x=78+i*141
        d.rounded_rectangle((x,174,x+128,310),radius=5,fill="#e3d9bb",outline="#cdbd9a")
        d.ellipse((x+28,182,x+100,247),fill="#c8c9a9")
        st=specimen_stamp(hue);im.paste(st,(x+16,165),st)
        count=sum(p["stage"]>=3 and (p.get("hue") or "")==hue for p in state.get("plants",[]))
        text(d,(x+64,258),name,13,ink,"bold","mm")
        text(d,(x+64,280),(hue or "no record").upper(),10,sub,"mono","mm")
        inferred=sum(p["stage"]>=3 and (p.get("hue") or "")==hue and bool(p.get("recalled")) for p in state.get("plants",[]))
        text(d,(x+64,298),f"{count:02d} · " + ("recalled" if inferred==count and count else "recorded" if not inferred else f"{inferred} recalled"),11,sub,"body","mm")
    text(d,(77,338),"Collected by looking; every blossom stays rooted.",12,sub)
    text(d,(773,338),"V · FIELD VERSES      ESC · CLOSE",11,sub,"mono","rm")


def verses(d,tiles,notes,page):
    left="#e8ddbd";right="#f2e8cc";ink="#393a43";sub="#645c59"
    d.rounded_rectangle((53,68,801,367),radius=12,fill="#142735",outline="#c1a474",width=2)
    d.rounded_rectangle((60,74,339,359),radius=8,fill=left)
    d.rounded_rectangle((332,74,794,359),radius=8,fill=right)
    d.rectangle((326,76,339,357),fill="#d5c6a8")
    text(d,(79,96),"EMBERGLOW   /   POCKET EDITION",10,sub,"mono")
    text(d,(79,129),"Field verses",27,ink,"title")
    text(d,(79,156),"A poem walked by two keepers.",13,sub)
    x0,y0=83,186
    d.rounded_rectangle((74,174,309,294),radius=5,fill="#486575")
    for j,row in enumerate(tiles):
        for i,t in enumerate(row):
            if t=="~":continue
            x,y=x0+i*9,y0+j*8
            d.rectangle((x,y,x+8,y+7),fill={"s":"#cfbd97","p":"#b89a86","T":"#71967c","#":"#879792","B":"#dfb86f"}.get(t,"#94aa8e"))
    for idx,n in enumerate(notes):
        x,y=x0+9*n["x"]+4,y0+8*n["y"]+3
        c="#facd7f" if n["by"]=="Wick" else "#a9dfb4"
        d.ellipse((x-4,y-4,x+4,y+4),fill=c if idx//4==page else sub,outline=ink)
    text(d,(79,318),"Tap a marked line to walk there.",13,ink)
    text(d,(79,341),"V / ESC  ·  CLOSE",10,sub,"mono")
    pages=max(1,(len(notes)+3)//4)
    text(d,(355,98),"COLLECTED ON FOOT",11,sub,"mono")
    text(d,(769,98),f"LEAF {page+1:02d} / {pages:02d}",11,sub,"mono","rm")
    for i,n in enumerate(notes[4*page:4*page+4]):
        y=119+49*i
        d.line((354,y,769,y),fill="#d6c8a7")
        text(d,(357,y+13),f"{4*page+i+1:02d}    {n['by'].upper()}     /     {chr(65+n['x'])}{n['y']+1}",10,sub,"mono")
        text(d,(357,y+32),n["text"],15,ink,"body")
    if not notes:text(d,(355,157),"The first page is waiting for a flag.",15,sub)
    d.line((354,316,769,316),fill="#cbbb99")
    text(d,(357,337),"‹  PREVIOUS",11,sub,"bold")
    text(d,(769,337),"NEXT  ›",11,sub,"bold","rm")


def render(side,tiles,state,myid,linked,now,notice,editing,draft,target,page=0):
    sky=state.get("sky","dusk")
    im=base(tuple(tiles),sky).copy();d=ImageDraw.Draw(im)
    players=state.get("players",[])
    lamps=state.get("lanterns",[])
    tint=Image.new("RGBA",im.size);g=ImageDraw.Draw(tint)
    for i,j in lamps:
        x,y=pos(i,j)
        for r,a in [(60,15),(40,20),(24,32),(14,48)]:
            g.ellipse((x-r,y-r*.72,x+r,y+r*.72),fill=(255,218,123,a))
    im.paste(tint,(0,0),tint);d=ImageDraw.Draw(im)
    if target:
        x,y=pos(*target);d.ellipse((x-9,y-4,x+9,y+4),outline="#ffdea4",width=2)
    # Row ordering allows bodies and canopies to pass behind one another.
    for j,row in enumerate(tiles):
        for i,t in enumerate(row):
            x,y=pos(i,j)
            if t=="T":tree(d,x,y+5)
            elif t=="#":rock(d,x,y+5)
            elif t=="B":bell(d,x,y+6)
        for item in state.get("plants",[]):
            if item["y"]==j:plant(d,*pos(item["x"],j),item["stage"],item.get("hue",""))
        for i,k in lamps:
            if k!=j:continue
            x,y=pos(i,j);d.line((x-4,y+3,x-4,y-16,x+2,y-16),fill="#5a484d",width=2)
            d.rectangle((x-1,y-14,x+6,y-5),fill="#8e684d",outline="#594958")
            d.rectangle((x,y-12,x+5,y-7),fill="#ffeb95")
        for item in state.get("notes",[]):
            if item["y"]!=j:continue
            x,y=pos(item["x"],j);d.line((x+7,y+4,x+7,y-11),fill="#725d50",width=2)
            d.polygon([(x+7,y-12),(x+18,y-12),(x+15,y-9),(x+18,y-6),(x+7,y-6)],fill="#f7d8a2")
        for p in players:
            if p["y"]!=j:continue
            x,y=pos(p["x"],j);s="p2" if p["role"]=="keeper" else "p1"
            if sum(q["x"]==p["x"] and q["y"]==j for q in players)>1:x+=(-9 if s=="p1" else 9)
            d.ellipse((x-14,y+1,x+14,y+8),fill="#486d67",outline="#f4dc98" if p["id"]==myid else None)
            sprite(im,x,y+7,s,int(now*2)%2)
            label={"glow":"✦","heart":"♥","dance":"♫","wave":"Hi!"}.get(p.get("emote"),"") or p["name"]
            if sum(q["x"]==p["x"] and q["y"]==j for q in players)>1:x+=(-13 if s=="p1" else 13)
            w=int(d.textlength(label,font=font(11,"bold"))/2)+6
            d.rounded_rectangle((x-w,y-48,x+w,y-32),radius=6,fill="#27323e")
            text(d,(x,y-40),label,11,"#ffde96" if s=="p2" else "#c6e8bb","bold","mm")
    for k,(i,j) in enumerate(state.get("fireflies",[])):
        x,y=pos(i,j);x+=int(8*math.sin(now+k));y+=int(4*math.cos(now+k))-13
        d.ellipse((x-1,y-1,x+1,y+1),fill="#fff4aa")
    d.rectangle((0,0,853,55),fill="#19283b")
    d.line((0,55,853,55),fill="#baa67e")
    text(d,(19,15),"N O C T U R N E    /    F I E L D   A T L A S",9,"#d6b887","mono")
    text(d,(18,38),"Emberglow Isle",23,"#fff0ce","title")
    text(d,(274,19),"GARDEN SKY",10,"#a0b6bc","mono")
    text(d,(274,38),sky.capitalize(),15,"#efcabb","bold")
    text(d,(388,19),"IN BLOOM",10,"#a0b6bc","mono")
    text(d,(388,38),f"{state.get('blooms',0):02d} flowers",14)
    text(d,(504,19),"KEEPER LIGHTS",10,"#a0b6bc","mono")
    text(d,(504,38),f"{len(lamps):02d} / 08",14)
    d.rounded_rectangle((690,13,838,42),radius=14,fill="#274d4e" if linked else "#514155")
    d.ellipse((701,24,708,31),fill="#9de2ae" if linked else "#c8a0a6")
    text(d,(717,28),"LAN Connected" if linked else "Finding island",13,"#e2f4dc","bold")
    d.rectangle((0,379,853,479),fill="#19283b"); d.line((0,379,853,379),fill="#b3a080")
    me=next((p for p in players if p["id"]==myid),{})
    distance=lambda n:abs(n['x']-me.get('x',-9))+abs(n['y']-me.get('y',-9))
    near=min((n for n in state.get("notes",[]) if distance(n)<=1),key=distance,default=None)
    message=notice or ((near["by"]+": "+near["text"]) if near else "") or (state.get("log") or [state.get("event") or "The island waits for its keepers."])[-1]
    text(d,(17,397),"FIELD WIRE",10,"#d3b885","mono")
    text(d,(99,397),message[:85],13)
    text(d,(836,397),("WICK  ·  KEEPER" if side=="p2" else "MOSS  ·  GARDENER"),10,"#c5cfcc","mono","rm")
    for idx,(key,label) in enumerate([("E","Lantern" if side=="p2" else "Plant"),("R","Ring bell"),("H","Emote"),("N","Note"),("J","Journal")]):
        x=16+idx*116
        d.rounded_rectangle((x,415,x+108,451),radius=7,fill="#344956",outline="#536974")
        d.rounded_rectangle((x+7,423,x+25,442),radius=4,fill="#203241");text(d,(x+16,433),key,11,"#ffe0a1","bold","mm")
        text(d,(x+32,433),label,13,"#fff1d7","bold")
    text(d,(616,425),"Click land to walk",14,"#f4ddb3","bold")
    text(d,(616,446),"or use arrows / WASD",12,"#c4d4d0")
    text(d,(18,466),"PLATE  01     •     Seed and lanternlight make a garden.",11,"#bdc7c4","mono")
    text(d,(635,466),"[ P ]   Petal key",12,"#d7e2ce","bold","rm")
    text(d,(836,466),"[ V ]   Field verses  ›",12,"#f1cea0","bold","rm")
    if editing=="verses":
        verses(d,tiles,state.get("notes",[]),page)
    elif editing=="petals":herbarium(im,d,state)
    elif editing:
        d.rounded_rectangle((118,91,736,338),radius=14,fill="#203240",outline="#dec494",width=2)
        text(d,(145,122),"Keeper's journal" if editing=="journal" else "Leave a field note",22,"#ffe3b1","title")
        if editing=="note":
            text(d,(145,166),"Pin a line of up to 40 characters to this spot.",14)
            d.rounded_rectangle((145,189,705,236),radius=7,fill="#132632")
            text(d,(155,213),draft+"▏",16)
            text(d,(145,290),"Enter to pin   ·   Esc to close",13,"#c2d0c8")
        else:
            lines=(state.get("log") or [])[-4:]
            for idx,line in enumerate(lines):text(d,(146,160+idx*24),line[:73],13)
            text(d,(145,268),(state.get("event") or "Listen for the island bell.")[:73],13,"#eecb95")
            text(d,(145,311),"V · Field verses     /     Click or press J to close",12,"#bacbc8")
    return im
