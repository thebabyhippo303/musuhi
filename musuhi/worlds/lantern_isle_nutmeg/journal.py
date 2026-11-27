"""Local, illustrated pages unlocked by exploration of the shared island."""
import math
from art import INK, MOSS, PAPER, GOLD, txt, sprite

PLATES = [
    ("salt", "The tide line", "walk", "Stand on the sandy shore.",
     ("Sand records a boot print for exactly one tide.",
      "Look back: the garden is smaller from here.")),
    ("flower", "Four sisters", "flower", "Approach a fully opened flower.",
     ("Plum, peach, buttercup, pearl: the island soil",
      "chooses a different colour for every plot.")),
    ("lamp", "Borrowed daylight", "lantern", "Visit a lantern after nightfall.",
     ("Three petals steeped in oil make a little sun.",
      "Nearby seedlings forget to go to sleep.")),
    ("rain", "Needle rain", "water", "Catch a passing rain shower.",
     ("The drops fall slantwise, like tiny stitches.",
      "Every leaf gets watered by the same cloud.")),
    ("fox", "The seed courier", "fox", "Send a heart to the fox nearby. [H]",
     ("There is always a burr in this fox's tail.",
      "Sometimes it is a seed for a friendly keeper.")),
    ("aurora", "Polar silk", "aurora", "See a sky woven with 100 harmony.",
     ("Two keepers mended the sky with a garden.",
      "Pull one thread gently: the whole isle rings.")),
]


def fox(d,x,y,mood):
    coat="#c96d37"; tip="#fff1ce"; dark="#58403a"
    d.ellipse((x-9,y-2,x+8,y+2),fill="#708766")
    if mood=="nap":
        d.ellipse((x-8,y-9,x+6,y+1),fill=coat,outline=dark)
        d.polygon([(x-8,y-4),(x-12,y-7),(x-10,y),(x-3,y+1),(x+1,y-2)],fill=tip)
        d.polygon([(x+1,y-6),(x+2,y-12),(x+5,y-9),(x+7,y-11),(x+8,y-5),(x+5,y-2)],fill=coat,outline=dark)
        d.line((x+4,y-6,x+6,y-6),fill=dark)
    else:
        d.polygon([(x-3,y-6),(x-9,y-9),(x-12,y-13),(x-13,y-8),(x-10,y-4),(x-4,y-2)],fill=coat,outline=dark)
        d.polygon([(x-12,y-13),(x-13,y-8),(x-10,y-7),(x-9,y-9)],fill=tip)
        d.ellipse((x-7,y-8,x+6,y-1),fill=coat,outline=dark)
        d.rectangle((x-5,y-3,x-3,y+1),fill=dark)
        d.rectangle((x+3,y-3,x+5,y+1),fill=dark)
        d.polygon([(x+1,y-7),(x+1,y-15),(x+4,y-12),(x+8,y-15),(x+9,y-8),(x+12,y-7),(x+8,y-4),(x+4,y-4)],fill=coat,outline=dark)
        d.polygon([(x+5,y-7),(x+11,y-7),(x+8,y-4)],fill=tip)
        d.point((x+7,y-10),fill=dark)
    if mood=="happy": txt(d,x-3,y-24,"♥",10,"#c65c58")
    elif mood=="nap": txt(d,x+7,y-23,"z",10,INK,"bold")


def discover(state,p,rows):
    if not p or not rows: return set()
    x,y=p["x"],p["y"]
    near=lambda obj: max(abs(obj["x"]-x),abs(obj["y"]-y))<=2
    kinds={o["k"] for o in state["objs"] if near(o)}
    found=set()
    if rows[y][x]=="s": found.add("salt")
    if "flower" in kinds: found.add("flower")
    if state["night"] and "lantern" in kinds: found.add("lamp")
    if state.get("rain"): found.add("rain")
    if p.get("emote")=="heart" and any(near(c) and c.get("mood")=="happy" for c in state.get("critters",[])): found.add("fox")
    if state.get("aurora"): found.add("aurora")
    return found


def star_shape(d,x,y,r,col):
    d.polygon([(x,y-r),(x+1,y-1),(x+r,y),(x+1,y+1),
               (x,y+r),(x-1,y+1),(x-r,y),(x-1,y-1)],fill=col)


def star_pos(i):
    return (83+(i%10)*37, 224+int(49*math.sin((i%10)*2.13+.28)))


def sky_page(d,sky,chosen):
    d.rounded_rectangle((49,132,665,354),7,fill="#183b42")
    d.rectangle((454,132,455,354),fill="#577369")
    txt(d,61,145,"N O C T U R N E   /   STAR CHART",10,"#bdd3c1","mono")
    for i in range(75):
        x=55+(i*127)%389; y=165+(i*197)%151
        d.point((x,y),fill="#74948b")
    first=chosen//10*10
    pts=[star_pos(i) for i in range(first,min(len(sky),first+10))]
    if len(pts)>1: d.line(pts,fill="#789c92",width=1)
    for i,(x,y) in enumerate(pts,first):
        star_shape(d,x,y,6 if i==chosen else 4,GOLD if i==chosen else PAPER)
        txt(d,x,y+11,f"{i+1:02d}",9,"#b3c9bf","mono","mt")
        if i==chosen: d.ellipse((x-11,y-11,x+11,y+11),outline="#a8ad7e")
    txt(d,60,330,"Click a star   ·   ↑ ↓ browse",11,"#bacdbf")
    if sky:
        item=sky[chosen]
        txt(d,470,151,f"STAR  /  {chosen+1:02d}",10,GOLD,"mono")
        txt(d,470,176,item["name"][:24],12 if len(item["name"])>17 else 15,PAPER,"serif")
        txt(d,470,200,"Named by "+item["by"],11,"#bdd3c1")
        txt(d,470,229,"A light held after the",12,PAPER)
        txt(d,470,248,"aurora faded.",12,PAPER)
    else:
        txt(d,470,155,"An unwritten sky",15,PAPER,"serif")
    txt(d,470,290,"During an aurora, speak",11,"#bdd3c1")
    txt(d,470,307,"a name into the sky.",11,"#bdd3c1")
    if sky: txt(d,470,331,"[R]  Rename this star",11,GOLD,"bold")


def page(d,seen,index,name,log,sky,chosen):
    d.rounded_rectangle((35,70,684,406),10,fill="#586a5b")
    d.rounded_rectangle((32,66,681,402),10,fill="#f6efd8",outline="#66785e",width=2)
    d.line((47,121,666,121),fill="#a9ad90")
    txt(d,50,78,"Keeper’s notebook",22,INK,"serif")
    txt(d,51,106,f"{name.upper()}   /   {len(seen)} OF 6 PLATES STAMPED",10,MOSS,"mono")
    txt(d,659,87,"J  ×",12,MOSS,"bold","rt")
    if index<2:
        for i,(key,title,icon,hint,lines) in enumerate(PLATES[index*3:index*3+3]):
            y=133+i*77
            have=key in seen
            d.rounded_rectangle((49,y,104,y+58),4,fill="#dce2c6" if have else "#e8e5d0",outline="#b1b499")
            if have:
                if icon=="fox": fox(d,77,y+33,"happy")
                elif icon=="aurora":
                    for line,col in enumerate(["#619985","#a295ad","#cda467"]):
                        d.arc((57,y+14+line*4,96,y+40+line*4),185,341,fill=col,width=3)
                else: sprite(d,icon,77,y+36)
            else: txt(d,77,y+16,"?",23,"#a5aa91","serif","mt")
            txt(d,116,y+1,f"0{index*3+i+1}    {title}",15,INK,"serif")
            txt(d,117,y+23,lines[0] if have else hint,12,MOSS)
            txt(d,117,y+41,lines[1] if have else "Field plate awaiting observation.",11,"#717f6f")
    elif index==2:
        sky_page(d,sky,chosen)
    else:
        txt(d,53,138,"Overheard on the isle",15,INK,"serif")
        for i,line in enumerate(log[-6:]):
            txt(d,55,169+i*29,"·   "+line[:77],12,INK)
    labels=["I   Coast & garden","II   Weather & wild","III   Star chart","IV   Island voices"]
    for i,label in enumerate(labels):
        x=49+i*155
        d.rounded_rectangle((x,367,x+149,391),4,fill=INK if i==index else "#e4dfc8")
        txt(d,x+75,374,label,11,PAPER if i==index else MOSS,"bold","mt")
