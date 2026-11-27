"""Hand-drawn miniatures for the Lantern Isle field atlas."""
from functools import lru_cache
import math
import random
from PIL import Image, ImageDraw, ImageFont


@lru_cache(maxsize=40)
def font(size, face="sans"):
    names = {"serif": "DejaVuSerif", "sans": "DejaVuSans",
             "bold": "DejaVuSans-Bold", "mono": "DejaVuSansMono"}
    return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/" + names[face] + ".ttf", size)


def text(d, xy, s, size, color, face="sans", anchor=None):
    d.text(xy, str(s), fill=color, font=font(size, face), anchor=anchor)


def star(d, x, y, r, c):
    d.polygon([(x,y-r),(x+1,y-1),(x+r,y),(x+1,y+1),
               (x,y+r),(x-1,y+1),(x-r,y),(x-1,y-1)], fill=c)


def keeper(d, x, y, side, me, tick):
    a, b = (("#f5a678", "#a44d51") if side=="p1" else ("#9fe8db", "#327685"))
    if me:
        d.ellipse((x-11,y+5,x+11,y+12),fill="#4b7670",outline="#fff1a6")
    else:
        d.ellipse((x-9,y+6,x+9,y+11),fill="#4b7670")
    d.rectangle((x-5,y+5,x-2,y+9),fill="#333c4a")
    d.rectangle((x+2,y+5,x+5,y+9),fill="#333c4a")
    d.polygon([(x-4,y-5),(x+4,y-5),(x+8,y+6),(x,y+5),(x-8,y+6)],fill=b)
    d.polygon([(x-3,y-4),(x+3,y-4),(x+5,y+3),(x-1,y+1),(x-5,y+3)],fill=a)
    d.rectangle((x-4,y-11,x+4,y-5),fill="#efc59b")
    d.point((x+2,y-8),fill="#37454f")
    d.polygon([(x-7,y-10),(x-4,y-14),(x+1,y-18),(x+5,y-12),(x+7,y-10)],fill=b)
    d.line((x-7,y-10,x+6,y-10),fill=a,width=2)
    d.ellipse((x-1,y-18,x+2,y-16),fill="#ffe5a1")


def lantern(d, x, y, tick=0):
    d.ellipse((x-9,y+5,x+8,y+9),fill="#576b5e")
    d.rectangle((x-1,y-8,x+1,y+6), fill="#59475a")
    d.line((x-4,y+7,x+4,y+7),fill="#413c4b",width=2)
    d.polygon([(x-5,y-10),(x+5,y-10),(x+4,y-3),(x,y-1),(x-4,y-3)],fill="#ffbe67")
    d.rectangle((x-2,y-9,x+2,y-4),fill="#fff6b1")
    d.polygon([(x-7,y-10),(x,y-15),(x+7,y-10)],fill="#644353")
    d.line((x-5,y-11,x+5,y-11),fill="#ad6f5e")
    star(d,x+8,y-9-int(math.sin(tick)*2),2,"#ffe8a4")


def bloom(d,x,y,stage,watered,variant=0):
    d.ellipse((x-9,y+3,x+9,y+8),fill="#5e6453" if watered else "#846747")
    d.line((x-6,y+6,x+6,y+6),fill="#93b4a5" if watered else "#b99b6c")
    h=[4,9,15,18][min(3,max(0,stage))]
    d.line((x,y+5,x,y+5-h),fill="#355d4c",width=2)
    d.polygon([(x,y+2),(x-6,y-3),(x-6,y+1)],fill="#578556")
    d.polygon([(x,y),(x+6,y-5),(x+5,y-1)],fill="#3c7957")
    if stage>=2:
        yy=y+4-h
        col=["#ffd688","#f7a9a2","#c4b7ef"][variant%3]
        for dx,dy in [(0,-3),(-3,0),(3,0),(-2,3),(2,3)]:
            d.ellipse((x+dx-2,yy+dy-2,x+dx+2,yy+dy+2), fill=col)
        d.rectangle((x-1,yy-1,x+1,yy+1),fill="#fff4bc")


def tree(d,x,y,k):
    d.ellipse((x-10,y+4,x+10,y+10),fill="#667951")
    d.rectangle((x-2,y-1,x+2,y+9),fill="#705944")
    for xx,yy,r in [(-5,-3,6),(4,-5,7),(0,-10,6)]:
        d.ellipse((x+xx-r,y+yy-r,x+xx+r,y+yy+r),fill="#406753")
        d.ellipse((x+xx-r+1,y+yy-r,x+xx+r-2,y+yy+r-4),fill="#58865b")
    for dx,dy in [(-4,-11),(3,-8),(-8,-4)]:
        d.line((x+dx,y+dy,x+dx+2,y+dy-1),fill="#98ae72",width=2)


def stone(d,x,y):
    d.polygon([(x-10,y+4),(x-7,y-3),(x-2,y-8),(x+5,y-6),(x+10,y+2),(x+6,y+6),(x-5,y+7)],fill="#5c7074")
    d.polygon([(x-9,y+1),(x-2,y-7),(x+5,y-5),(x+5,y-2),(x-3,y+2)],fill="#a6b4a0")
    d.line((x-7,y+7,x+5,y+7),fill="#78815f")


def heron(d,x,y,t):
    """A night heron in profile, silver mantle and a swept-back plume."""
    d.ellipse((x-11,y+7,x+12,y+11), fill="#647772")
    for xx,lean in [(x-2,2),(x+3,-2)]:
        d.line((xx,y-2,xx+lean,y+4,xx+lean,y+9,xx+lean+3,y+9), fill="#bc9863",width=2)
    d.polygon([(x-14,y),(x-8,y-5),(x+2,y-8),(x+7,y-6),(x+5,y+1),(x-2,y+4)],fill="#dce2ce")
    d.polygon([(x-15,y+1),(x-9,y-5),(x-1,y-8),(x+4,y-6),(x-1,y-1)],fill="#64798b")
    d.line((x-9,y-2,x-2,y-5,x+1,y-5),fill="#9fb8b8",width=2)
    b=round(math.sin(t*.75))
    d.line((x+4,y-3,x+8,y-10+b,x+6,y-15+b,x+10,y-19+b),fill="#ecedd8",width=4)
    d.ellipse((x+5,y-22+b,x+13,y-17+b),fill="#ebead3")
    d.line((x+12,y-21+b,x+8,y-23+b,x+2,y-20+b,x-1,y-21+b),fill="#415567",width=2)
    d.polygon([(x+12,y-20+b),(x+22,y-19+b),(x+12,y-17+b)],fill="#dfae63")
    d.point((x+11,y-20+b),fill="#2a363f")


def koi(d,x,y,t,i):
    s=1 if i%2==0 else -1
    y+=int(math.sin(t*3+i)*1.8)
    dx=lambda n:x+s*n
    d.arc((x-12,y-5,x+12,y+6),5,110,fill="#84b6ad")
    d.polygon([(dx(-4),y),(dx(-11),y-4),(dx(-9),y),(dx(-10),y+3)],fill="#ebba8c")
    d.ellipse((x-6,y-3,x+6,y+3),fill="#f3d9ab")
    d.ellipse((min(dx(-4),dx(0)),y-3,max(dx(-4),dx(0)),y+1),fill="#d7785e")
    d.line((dx(3),y-2,dx(4),y+1),fill="#ce795d",width=2)
    d.point((dx(5),y-1),fill="#574752")


def waypost(d,x,y):
    d.ellipse((x-5,y+6,x+6,y+8),fill="#70816c")
    d.rectangle((x-1,y-5,x+1,y+7),fill="#785e45")
    d.polygon([(x-7,y-9),(x+4,y-9),(x+8,y-6),(x+4,y-3),(x-7,y-3)],fill="#deba7d",outline="#7c654f")
    d.line((x-4,y-6,x+3,y-6),fill="#89694a")


def base_map(rows, key):
    """Paint continuous contours first, then a deterministic scattering of details."""
    h,w=len(rows),len(rows[0])
    img=Image.new("RGB",(w*28,h*28),"#387884")
    d=ImageDraw.Draw(img)
    rng=random.Random(54)
    for _ in range(1020):
        x,y=rng.randrange(img.width),rng.randrange(img.height)
        n=rng.randrange(2,10)
        d.line((x,y,x+n,y),fill=rng.choice(["#43848d","#397d89","#4a8b94","#377582"]))
    land=[(i,j) for j,row in enumerate(rows) for i,v in enumerate(row) if key(v)!="sea"]
    # Overlapping rounded squares unite adjoining land while keeping chamfered corners.
    for pad,oy,c in [(7,2,"#599a9d"),(4,2,"#aed1b7"),(2,2,"#998d64"),(1,0,"#daca98"),(0,0,"#bbc58b")]:
        for i,j in land:
            x,y=i*28,j*28
            d.rounded_rectangle((x-pad,y-pad+oy,x+28+pad,y+28+pad+oy),radius=4+pad,fill=c)
    for i,j in land:
        k=key(rows[j][i]); x,y=i*28,j*28
        if k in ("soil","sand","path"):
            c={"soil":"#ba956e","sand":"#dbca98","path":"#d4c298"}[k]
            d.rounded_rectangle((x,y,x+27,y+27),4,fill=c)
        for _ in range(6):
            xx=x+rng.randrange(3,24); yy=y+rng.randrange(4,25)
            if k in ("grass","tree","rock") and rng.random()<.48:
                d.line((xx-1,yy-2,xx,yy,xx+2,yy-3),fill=rng.choice(["#9bac77","#a4b781"]))
            else:
                d.line((xx,yy,xx+2,yy),fill={"soil":"#a37e5e","sand":"#c5b386","path":"#b6a883"}.get(k,"#a8b782"))
        if k=="tree": tree(d,x+14,y+14,i+j)
        if k=="rock": stone(d,x+14,y+14)
    return img
