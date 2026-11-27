"""Illustrations for Lantern Isle's field atlas. Coordinates are map-local."""
import math
import random
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont

T = 20
INK = "#173935"
PAPER = "#f5efd9"
MOSS = "#4c7566"
GOLD = "#edb960"


@lru_cache(maxsize=48)
def font(size, family="sans"):
    path = {"serif": "dejavu/DejaVuSerif-Bold.ttf",
            "mono": "dejavu/DejaVuSansMono.ttf",
            "bold": "dejavu/DejaVuSans-Bold.ttf",
            "sans": "dejavu/DejaVuSans.ttf"}[family]
    return ImageFont.truetype("/usr/share/fonts/truetype/" + path, size)


def txt(d, x, y, s, size, col=INK, family="sans", anchor="lt"):
    d.text((x, y), str(s), font=font(size, family), fill=col, anchor=anchor)


def terrain(rows):
    im = Image.new("RGB", (700, 360), "#589d9c")
    d = ImageDraw.Draw(im)
    rng = random.Random(943)
    def tile(x, y):
        if 0 <= y < len(rows) and 0 <= x < len(rows[y]):
            return rows[y][x]
        return "~"
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            l, t = T*x, T*y
            if c == "~":
                shore = any(tile(x+dx, y+dy) != "~" for dx in (-1,0,1) for dy in (-1,0,1))
                d.rectangle((l,t,l+19,t+19), fill=rng.choice(
                    ["#6cacaa","#6eaeab","#6dacaa"] if shore else ["#549496","#559597","#569698"]))
                if rng.random() < .58:
                    wx, wy = l+rng.randint(1,9), t+rng.randint(4,15)
                    d.line((wx,wy,wx+5,wy,wx+7,wy-1,wx+9,wy-1),fill="#91c4ba")
                continue
            sand = c == "s"
            base = rng.choice(("#d9c991","#dfce97","#dfce98") if sand else
                              ("#9cb87b","#a0bb7d","#a2bc7e","#a0ba7b"))
            d.rectangle((l,t,l+19,t+19), fill=base)
            for _ in range(3):
                px,py=l+rng.randint(1,17),t+rng.randint(2,17)
                d.line((px,py,px+1,py),fill="#bbab78" if sand else "#819e67")
            if not sand and rng.random() < .25:
                d.line((l+6,t+12,l+7,t+14,l+9,t+10),fill="#749364")
            for dx,dy,edge in [(-1,0,(l,t,l,t+19)),(1,0,(l+19,t,l+19,t+19)),
                               (0,-1,(l,t,l+19,t)),(0,1,(l,t+19,l+19,t+19))]:
                if tile(x+dx,y+dy) == "~":
                    d.line(edge,fill="#f3e8b5",width=2)
    for y,row in enumerate(rows):
        for x,c in enumerate(row):
            px,py=x*T+10,y*T+14
            if c == "T":
                d.ellipse((px-7,py-2,px+8,py+3), fill="#738968")
                d.rectangle((px-2,py-7,px+2,py+2),fill="#67583c")
                for ox,oy,r,col in [(0,-10,9,"#375f4b"),(-4,-13,6,"#547758"),
                                    (3,-15,6,"#628858"),(-1,-17,5,"#73955e")]:
                    d.ellipse((px+ox-r,py+oy-r,px+ox+r,py+oy+r),fill=col)
                d.line((px-4,py-18,px-1,py-20,px+1,py-20),fill="#9ca96e")
            if c == "#":
                d.polygon([(px-9,py),(px-7,py-7),(px,py-11),(px+6,py-8),(px+9,py-1),(px+4,py+2),(px-6,py+2)],fill="#687d75")
                d.polygon([(px-7,py-6),(px,py-10),(px+5,py-7),(px,py-3)], fill="#afbb9e")
    return im


def sprite(d,k,x,y,color="#eea25e",variant=0):
    """Draw an object around its ground anchor."""
    if k=="path":
        for a,b in [(-3,-3),(4,-1),(0,4)]:
            d.rounded_rectangle((x+a-4,y+b-2,x+a+3,y+b+1),1,fill="#c8b395",outline="#9b917a")
    elif k in ("flower","sprout","bud","plant","harvest"):
        d.ellipse((x-6,y-2,x+6,y+2),fill="#817554")
        h=5 if k in ("sprout","plant") else 11
        d.line((x,y,x,y-h),fill="#436947",width=2)
        d.polygon([(x,y-2),(x-6,y-7),(x-2,y-7),(x,y-4)],fill="#46784c")
        d.polygon([(x,y-4),(x+5,y-9),(x+6,y-6),(x+2,y-3)],fill="#5e8b4f")
        if k == "bud":
            d.ellipse((x-2,y-h-3,x+2,y-h+1),fill="#e0aa9b")
        if k in ("flower","harvest"):
            for a,b in [(0,-3),(3,-1),(2,2),(-2,2),(-3,-1)]:
                d.ellipse((x+a-2,y-h+b-2,x+a+2,y-h+b+2),fill=["#f8c4be","#fff2c0","#d9c4f0","#eaaa83"][variant%4])
            d.rectangle((x-1,y-h-2,x+1,y-h),fill="#af7539")
    elif k=="lantern":
        d.ellipse((x-6,y-1,x+5,y+2), fill="#718164")
        d.rectangle((x-1,y-13,x+1,y+1),fill="#665c41")
        d.rectangle((x-4,y-14,x+4,y-7),fill="#ffdd88",outline="#785c43")
        d.line((x,y-13,x,y-8),fill="#fff7b4")
        d.polygon([(x-6,y-14),(x,y-19),(x+6,y-14)],fill=INK)
    elif k=="water":
        d.polygon([(x,y-13),(x-5,y-5),(x-4,y-1),(x,y+1),(x+4,y-1),(x+5,y-5)],fill="#5d9db5")
        d.point((x-2,y-4),fill="#f4edd2")
    elif k=="clear":
        d.line((x-5,y+1,x+5,y-11),fill="#936741",width=3)
        d.polygon([(x-7,y+1),(x-4,y-5),(x+1,y-1),(x-3,y+3)],fill="#738a85")
    elif k=="walk":
        d.ellipse((x-6,y-5,x-2,y+2),fill="#8a7458")
        d.ellipse((x+1,y-12,x+5,y-5),fill="#8a7458")
    elif k=="player":
        d.ellipse((x-7,y,x+8,y+4), fill="#677d66")
        d.rectangle((x-4,y-2,x-2,y+2),fill="#4f433b")
        d.rectangle((x+2,y-2,x+4,y+2),fill="#4f433b")
        d.rounded_rectangle((x-5,y-10,x+5,y-2),2,fill=INK)
        d.rectangle((x-4,y-9,x+4,y-3), fill=color)
        d.line((x-4,y-8,x+3,y-4),fill="#e9d1a3",width=2)
        d.rectangle((x-4,y-16,x+4,y-10),fill="#e9b789")
        d.point((x+2,y-13),fill=INK)
        d.rectangle((x-4,y-20,x+3,y-16),fill=color)
        d.rectangle((x-6,y-17,x+6,y-16),fill=INK)


def night_tint(im, phase):
    a = int(max(0,-math.sin(phase*math.tau))*105)
    if a: return Image.blend(im,Image.new("RGB",im.size,(28,38,81)),a/255)
    return im.copy()
