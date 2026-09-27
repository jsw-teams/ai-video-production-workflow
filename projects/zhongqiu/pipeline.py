"""Render the Mid-Autumn line-animation short with timed speech and action Foley."""
from __future__ import annotations

from array import array
import math
import random
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
import yaml

from score_engine import compose

ROOT=Path(__file__).resolve().parent
ASSETS=ROOT/"assets"
P=yaml.safe_load((ROOT/"project.yaml").read_text(encoding="utf-8"))
DURATION=float(P["target_duration_seconds"])
FPS=24
SIZE=(960,540)
SR=22050
FONT_PATH=r"C:\Windows\Fonts\STSONG.TTF"


def font(sz): return ImageFont.truetype(FONT_PATH,sz)


def make_stereo(path: Path,left: array,right: array,peak=.7):
    mx=max(max(left),max(right),abs(min(left)),abs(min(right)),1e-6)
    gain=min(peak/mx,3.0)
    out=array("h")
    for a,b in zip(left,right):
        out.append(int(max(-32767,min(32767,a*gain*32767))))
        out.append(int(max(-32767,min(32767,b*gain*32767))))
    with wave.open(str(path),"wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(out.tobytes())


def make_foley(path: Path, events: list[tuple[float,float,float,float,float]], seed=2):
    n=int(DURATION*SR); l=array("f",[0.0])*n; r=array("f",[0.0])*n; rng=random.Random(seed)
    for start,length,hz,amp,pan in events:
        i0=int(start*SR); count=min(int(length*SR),n-i0)
        if count<=0: continue
        pl=math.sqrt((1-pan)*.5); pr=math.sqrt((1+pan)*.5)
        for j in range(count):
            t=j/SR; env=min(1,t/.015)*math.exp(-t*(4 if hz<220 else 9))
            noise=rng.uniform(-1,1)*(.44 if hz>350 else .16)
            s=(math.sin(2*math.pi*hz*t)+.31*math.sin(2*math.pi*hz*2.3*t)+noise)*env*amp
            l[i0+j]+=s*pl; r[i0+j]+=s*pr
    make_stereo(path,l,r,.38)


def make_room(path: Path):
    n=int(DURATION*SR); l=array("f",[0.0])*n; r=array("f",[0.0])*n
    rng=random.Random(815); a=b=0.0
    for i in range(n):
        a+=.011*(rng.uniform(-1,1)-a); b+=.011*(rng.uniform(-1,1)-b)
        t=i/SR; fade=min(1,t/1.5,(DURATION-t)/1.5)
        # A slightly busier room during the gathering, with morning quiet at either end.
        activity=.25 if t<10 or t>82 else (.48 if t<51 else .62)
        l[i]=a*activity*fade*.052; r[i]=b*activity*fade*.052
    make_stereo(path,l,r,.10)


def make_stems():
    ASSETS.mkdir(exist_ok=True)
    compose("zhongqiu",ASSETS/"music.wav")
    make_room(ASSETS/"ambience.wav")
    make_foley(ASSETS/"sync_foley.wav",[
        (11.8,.16,135,.14,-.15),(17.2,.11,220,.12,.18),(24.4,.13,180,.13,-.22),
        (32.1,.10,920,.12,.12),(36.8,.10,132,.14,-.22),
        (42.85,.08,170,.18,.10),(43.62,.08,170,.18,.10),(44.36,.08,170,.18,.10),
        (48.5,.12,780,.12,-.1),(53.7,.12,310,.14,.14),(57.5,.09,520,.13,-.16),
        (66.1,.10,740,.11,.12),(70.3,.18,260,.16,-.25),(74.2,.11,195,.13,.18),
        (85.0,.08,960,.14,-.2),(88.0,.10,620,.10,.16)
    ],seed=21)


def fit_bg() -> Image.Image:
    im=Image.open(ASSETS/"kitchen-scene.png").convert("RGB")
    return ImageOps.fit(im,SIZE,method=Image.Resampling.LANCZOS)


def smooth(v):
    v=max(0,min(1,v)); return v*v*(3-2*v)


def text(d,xy,s,sz,col,anchor=None): d.text(xy,s,font=font(sz),fill=col,anchor=anchor)


def mouth_at(t,start,dur,states):
    rel=t-start
    if rel<0 or rel>dur: return "closed"
    k=min(len(states)-1,int(rel/dur*len(states)))
    return states[k]


def person(d,x,base,kind,t,activity="work",mouth="closed",look=1):
    """Two stable, hand-drawn profiles with changing arms, gaze, brows and mouth shapes."""
    s=1.12 if kind=="adult" else .91
    line=(72,56,44,238); light_line=(91,71,53,155); skin=(222,184,148,224)
    shirt=(125,143,124,224) if kind=="adult" else (198,159,91,232)
    dir=1 if look>=0 else -1
    bob=1.8*math.sin(t*2.0+(0 if kind=="adult" else 1.4))
    def pt(dx,dy): return (x+dir*dx*s,base+dy*s+bob)
    # Shoulder, torso and apron sit behind the working surface.
    d.rounded_rectangle((x-36*s,base-151*s+bob,x+36*s,base-47*s),radius=19*s,fill=shirt,outline=line,width=2)
    d.line((x-9*s,base-146*s+bob,x+1*s,base-84*s),fill=(226,217,190,190),width=2)
    d.line((x-20*s,base-127*s+bob,x-31*s,base-95*s),fill=light_line,width=2)
    # One hand starts, makes contact, gives support, and releases.
    phase=math.sin(t*2.0+(0 if kind=="adult" else 1.1))
    if activity=="press":
        reach=.22+.78*smooth((t-42.38)/.62) if t<45 else 1-.55*smooth((t-45)/.65)
        hx=67*reach+8*phase; hy=-70-31*reach
    elif activity=="carry": hx=52+7*phase; hy=-82+6*math.sin(t*2.7)
    elif activity=="knead": hx=44+16*phase; hy=-67+5*math.cos(t*3.2)
    elif activity=="rest": hx=18; hy=-70
    else: hx=35+14*phase; hy=-70+5*math.sin(t*2.1)
    shoulder=pt(dir*16,-132); elbow=pt(dir*37,-101); wrist=pt(hx,hy)
    d.line([shoulder,elbow,wrist],fill=line,width=int(5*s),joint="curve")
    d.line([pt(dir*18,-130),pt(dir*38,-100),pt(hx-3,-70)],fill=(222,196,157,185),width=1)
    d.ellipse((wrist[0]-5*s,wrist[1]-4*s,wrist[0]+8*s,wrist[1]+4*s),fill=skin,outline=line,width=1)
    # Face profile: cheek and jaw remain visible as the mouth performs.
    hx0=x-35*s; hy0=base-235*s+bob
    d.ellipse((hx0,hy0,hx0+70*s,hy0+82*s),fill=skin,outline=line,width=2)
    hair=(53,45,39,245)
    d.arc((hx0-3,hy0-10*s,hx0+75*s,hy0+76*s),180,354,fill=hair,width=int(8*s))
    if kind=="adult":
        d.ellipse((x-32*s,base-251*s+bob,x+28*s,base-214*s+bob),fill=hair,outline=line,width=1)
        d.ellipse((x-45*s,base-235*s+bob,x-26*s,base-216*s+bob),fill=hair)
        # a few silver strands and loose hair at the temple
        d.line((x-19*s,base-246*s+bob,x-7*s,base-242*s+bob),fill=(191,177,147,210),width=1)
        d.line((x+22*s,base-228*s+bob,x+27*s,base-212*s+bob),fill=hair,width=2)
    else:
        d.ellipse((x+24*s,base-238*s+bob,x+48*s,base-220*s+bob),fill=hair,outline=line,width=1)
        d.line((x-24*s,base-248*s+bob,x-7*s,base-239*s+bob),fill=light_line,width=1)
    eye_x=x+dir*15*s; eye_y=base-196*s+bob
    blink=(int(t*2.1+(0 if kind=="adult" else 2))%19)==0
    d.line((eye_x-2*s,eye_y,eye_x+3*s,eye_y),fill=line,width=1 if blink else 2)
    brow_y=eye_y-9*s
    tilt=3*s if kind=="child" and 34.8<t<37.05 else (-1*s if kind=="adult" and 37.2<t<40.45 else 0)
    d.line((eye_x-5*s,brow_y+tilt,eye_x+6*s,brow_y-tilt),fill=line,width=2)
    # A short nose, cheek wash and jaw establish a readable side view.
    d.line([pt(28,-194),pt(38,-188),pt(29,-184)],fill=line,width=2)
    cheek_x=x-29*s if dir<0 else x+7*s
    d.arc((cheek_x,base-190*s+bob,cheek_x+22*s,base-157*s+bob),10,95,fill=(191,121,91,110),width=2)
    mx=x+dir*28*s; my=base-171*s+bob
    if mouth=="round": box=(mx-4*s,my-6*s,mx+6*s,my+7*s)
    elif mouth=="open": box=(mx-3*s,my-3*s,mx+7*s,my+8*s)
    elif mouth=="teeth":
        d.line((mx,my,mx+dir*7*s,my+1*s),fill=(94,56,47,250),width=2); box=None
    else:
        d.line((mx,my,mx+dir*5*s,my),fill=(94,56,47,230),width=2); box=None
    if box: d.ellipse(box,fill=(91,49,41,250),outline=line,width=1)
    # Head angle follows the other speaker and then returns to the work.
    if kind=="adult" and 37.2<t<42.2:
        d.line((x-5*s,base-151*s+bob,x+dir*4*s,base-144*s+bob),fill=light_line,width=1)


def cake(d,cx,cy,r,phase=0,cut=False):
    d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=(187,125,66,255),outline=(78,52,39,255),width=4)
    d.ellipse((cx-r+7,cy-r+7,cx+r-7,cy+r-7),outline=(225,177,104,255),width=2)
    for j in range(8):
        a=math.pi*2*j/8+phase
        x1=cx+math.cos(a)*r*.25; y1=cy+math.sin(a)*r*.25
        x2=cx+math.cos(a)*r*.72; y2=cy+math.sin(a)*r*.72
        d.line((x1,y1,x2,y2),fill=(102,67,45,245),width=3)
    d.ellipse((cx-r*.23,cy-r*.23,cx+r*.23,cy+r*.23),outline=(102,67,45,245),width=2)
    if cut:
        d.line((cx,cy-r*.9,cx,cy+r*.88),fill=(240,219,178,245),width=2)


def frame(t,bg):
    base=bg.copy().convert("RGBA")
    layer=Image.new("RGBA",SIZE,(0,0,0,0)); d=ImageDraw.Draw(layer,"RGBA")
    ink=(66,53,44,250); paper=(244,231,204,240); gold=(210,156,82,250)
    if t<10:
        # The first image is the ordinary morning after; a round object takes a place at breakfast.
        d.ellipse((114,373,318,453),fill=(228,220,202,238),outline=ink,width=4)
        d.ellipse((130,377,301,432),fill=(151,131,105,230),outline=(98,81,63,230),width=2)
        cake(d,223,382,35,phase=.3,cut=True)
        if t<7:
            text(d,(51,66),"之后的一个月",30,(67,54,44,245))
        if t>4.2:
            text(d,(67,472),"节后的早餐",19,(67,54,44,220))
    elif t<27:
        person(d,360,489,"adult",t,"knead",look=1)
        # One basin and a line of dough portions anchor the work rather than a holiday icon.
        d.ellipse((383,363,612,457),fill=(238,226,204,240),outline=ink,width=4)
        d.arc((394,370,601,446),180,360,fill=(102,79,58,230),width=3)
        for j in range(6):
            x=416+j*30; y=350+int(3*math.sin(t*1.8+j))
            d.ellipse((x,y,x+18,y+14),fill=(222,194,151,255),outline=ink,width=1)
        if t>18:
            d.line((626,402,733,402),fill=(94,76,59,190),width=2)
            d.rounded_rectangle((654,374,760,398),radius=8,fill=(239,226,204,245),outline=ink,width=2)
    elif t<51:
        person(d,312,488,"child",t,"press",mouth=mouth_at(t,34.8,2.25,["round","open","teeth","open","round","open","teeth"]),look=1)
        person(d,667,488,"adult",t,"knead",mouth=mouth_at(t,37.2,3.25,["open","round","teeth","teeth","teeth","closed","open","teeth"]),look=-1)
        # The object visibly changes state during prepare -> press -> release.
        d.rounded_rectangle((380,378,534,424),radius=9,fill=(83,62,46,245),outline=ink,width=3)
        d.ellipse((399,365,518,409),fill=(228,204,169,245),outline=ink,width=3)
        press=smooth((t-42.45)/.50)
        d.ellipse((420,389-13*press,496,429-13*press),fill=(195,141,81,255),outline=ink,width=3)
        if t>=43.0:
            cake(d,458,405,30,phase=.1)
        if t>33.5 and t<41.5:
            pass
        # Brief listening beat; the adult's hand points to where the dough is supported.
        if 39.0<t<42.0:
            d.line((642,370,572,398),fill=(229,184,124,240),width=3)
    elif t<69:
        person(d,340,486,"child",t,"rest",look=1)
        person(d,655,486,"adult",t,"carry",look=-1)
        # More people arrive: plates travel hand-to-hand; no front-facing family portrait.
        for j in range(4):
            x=376+j*58; y=388+int(5*math.sin(t*1.4+j))
            d.ellipse((x,y,x+41,y+14),fill=(227,218,196,245),outline=ink,width=2)
            cake(d,x+20,y-1,9,phase=.2*j)
        d.arc((140,383,300,454),190,350,fill=(112,86,62,235),width=3)
        if t>59:
            # The adult is still moving while the rest of the table settles.
            d.line((x-18,397,x+18,397),fill=gold,width=2)
    elif t<82:
        person(d,616,488,"adult",t,"carry",look=-1)
        person(d,318,488,"child",t,"rest",look=1)
        for j in range(5):
            x=85+j*44; y=388-(j%2)*5
            d.rectangle((x,y,x+74,y+42),fill=(197,161,115,245),outline=ink,width=2)
            d.line((x,y+11,x+74,y+11),fill=(132,98,66,220),width=1)
            cake(d,x+37,y+6,8,phase=.15*j)
        if t>68:
            text(d,(72,83),"做得太多",30,(65,53,43,245))
    else:
        if t<90:
            person(d,430,490,"child",t,"rest",look=1)
            d.ellipse((125,380,323,454),fill=(235,225,205,240),outline=ink,width=4)
            cake(d,224,397,42,phase=.1,cut=True)
            d.line((374,407,405,400),fill=(85,64,50,245),width=5)
            if t>84:
                text(d,(58,75),"日常早饭",24,(67,54,44,240))
        else:
            d.rectangle((0,0,960,540),fill=(31,29,25,231))
            text(d,(55,92),"据《生活报》2006 年家庭回忆重构",26,paper)
            text(d,(55,143),"人物、画面、对白与声音均为创作演绎",21,(228,188,133,238))
            text(d,(55,195),"木模敲桌声：现场动作的原创拟声",19,(223,215,198,210))
    base.alpha_composite(layer)
    result=base.convert("RGB")
    # Cut in for the two speaking faces; then hold on working hands as the gesture changes.
    if 34.0<t<41.5:
        result=result.crop((102,36,858,462)).resize(SIZE,Image.Resampling.LANCZOS)
        sd=ImageDraw.Draw(result,"RGBA")
        subtitle="我这块又裂开了。" if t<37.15 else "先托着这里，别急。"
        sd.rounded_rectangle((208,455,752,508),radius=5,fill=(50,42,35,228))
        text(sd,(480,463),subtitle,24,(244,231,204,250),"ma")
    elif 42.4<t<45.6:
        result=result.crop((116,75,876,503)).resize(SIZE,Image.Resampling.LANCZOS)
    return result


def render():
    ASSETS.mkdir(exist_ok=True); make_stems(); bg=fit_bg(); review=[]
    audio=[ASSETS/"music.wav",ASSETS/"sync_foley.wav",ASSETS/"ambience.wav",
           ASSETS/"narration_open.wav",ASSETS/"child_line.wav",ASSETS/"adult_line.wav",ASSETS/"narration_surplus.wav"]
    graph=("[1:a]volume='if(between(t,33,45),0.25,0.42)'[m];[2:a]volume=0.85[f];[3:a]volume=0.52[r];"
           "[4:a]volume=0.90,adelay=600|600[v1];[5:a]volume=0.92,adelay=34800|34800[v2];"
           "[6:a]volume=0.92,adelay=37200|37200[v3];[7:a]volume=0.94,adelay=68500|68500[v4];"
           "[m][f][r][v1][v2][v3][v4]amix=inputs=7:duration=longest:dropout_transition=0:normalize=0,alimiter=limit=0.91[a]")
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-y","-f","rawvideo","-pixel_format","rgb24",
         "-video_size",f"{SIZE[0]}x{SIZE[1]}","-framerate",str(FPS),"-i","-"]
    for p in audio: cmd += ["-i",str(p)]
    cmd += ["-filter_complex",graph,"-map","0:v","-map","[a]","-t",str(DURATION),
            "-vf","scale=1920:1080:flags=lanczos,format=yuv420p","-c:v","libx264","-preset","fast","-crf","18",
            "-c:a","aac","-b:a","192k","-movflags","+faststart",str(ROOT/"final.mp4")]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for i in range(int(DURATION*FPS)):
            t=i/FPS; im=frame(t,bg)
            if i%(8*FPS)==0: review.append(im.resize((480,270)))
            proc.stdin.write(im.tobytes())
        proc.stdin.close(); err=proc.stderr.read().decode("utf-8","replace"); code=proc.wait()
        if code: raise RuntimeError(err[-4000:])
    except BaseException:
        if proc.poll() is None: proc.kill()
        raise
    cols=3; rows=math.ceil(len(review)/cols); sheet=Image.new("RGB",(cols*480,rows*270),(20,20,18))
    for i,im in enumerate(review): sheet.paste(im,((i%cols)*480,(i//cols)*270))
    sheet.save(ROOT/"review.jpg",quality=90)
    print(f"Rendered {ROOT/'final.mp4'} ({DURATION:.0f}s, 1920x1080, 24fps)")


if __name__=="__main__": render()
