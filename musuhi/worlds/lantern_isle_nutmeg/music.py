"""A hand-played five-leaf instrument; the server supplies the shared score."""
import array
import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from art import txt, INK, PAPER, MOSS, GOLD

NOTES=("C","D","E","G","A")
LEAVES=("Reed","Dew","Petal","Wick","Star")
COLS=("#7caa88","#82b6c5","#dda0b2","#e4b267","#afa2ce")


class Bells:
    def __init__(self):
        self.sound=False
        self.player=shutil.which("pw-play") or shutil.which("aplay")
        self.tmp=None
        self.proc=[]
        self.prev=None

    def hear(self,tune):
        sig=tuple((el["n"],el["by"]) for el in tune)
        if self.sound and self.prev is not None and sig and sig!=self.prev and self.player:
            self.ring(sig[-1][0])
        self.prev=sig

    def ring(self,n):
        if n not in range(5): return
        if self.tmp is None: self.tmp=tempfile.TemporaryDirectory(prefix="isle-chimes-")
        path=Path(self.tmp.name)/f"{n}.wav"
        if not path.exists():
            frequency=(523.25,587.33,659.25,783.99,880)[n]
            samples=array.array("h")
            for i in range(13700):
                t=i/22050
                vol=min(1,t*110)*math.exp(-7*t)
                theta=math.tau*frequency*t
                samples.append(int(5500*vol*(math.sin(theta)+.22*math.sin(theta*2.01))))
            with wave.open(str(path),"wb") as f:
                f.setparams((1,2,22050,0,"NONE","not compressed"))
                f.writeframes(samples.tobytes())
        self.proc=[p for p in self.proc if p.poll() is None]
        if len(self.proc)<4:
            try: self.proc.append(subprocess.Popen([self.player,str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
            except OSError: self.sound=False


def stand(d,tune,sound):
    d.rounded_rectangle((29,234,690,412),9,fill="#153e40",outline="#f1d89e",width=2)
    txt(d,43,246,"The reed organ",19,PAPER,"serif")
    txt(d,231,251,"STAGE   /   LAST 8 NOTES",10,"#afd1b7","mono")
    txt(d,526,251,"S: Sound "+("on" if sound else "off"),10,PAPER)
    txt(d,675,251,"M  ×",11,PAPER,"bold","rt")
    for i in range(5):
        d.line((47,278+i*6,668,278+i*6),fill="#4d6e64")
    for i,el in enumerate(tune[-8:]):
        n=el["n"]
        if n not in range(5): continue
        x,y=76+i*76,303-n*6
        d.line((x+5,y,x+5,y-15),fill=COLS[n],width=2)
        d.ellipse((x-5,y-3,x+5,y+3),fill=COLS[n])
        txt(d,x,311,el["by"][:12],10,PAPER,"mono","mt")
    if not tune: txt(d,356,287,"The reeds are listening.",12,PAPER,"serif","mt")
    for i in range(5):
        x=45+i*126
        d.rounded_rectangle((x,331,x+116,373),10,fill=COLS[i])
        d.polygon([(x+10,355),(x+14,343),(x+24,340),(x+22,351),(x+13,356)],fill=INK)
        d.line((x+10,359,x+20,345),fill=PAPER)
        txt(d,x+33,338,f"F{i+1}  /  {NOTES[i]}",10,INK,"mono")
        txt(d,x+33,353,LEAVES[i],12,INK,"bold")
    txt(d,45,387,"Duet: play F1 → F5 in order, with a note from each keeper, to water the isle.",11,PAPER)
