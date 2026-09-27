"""Render the observational reconstruction, sound stems, and QA sheet."""
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

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
PROJECT = yaml.safe_load((ROOT / "project.yaml").read_text(encoding="utf-8"))
DURATION = float(PROJECT["target_duration_seconds"])
FPS, SR = 24, 22050
SIZE = (960, 540)
FONT_PATH = r"C:\Windows\Fonts\STSONG.TTF"
INK = (35, 38, 37)
PAPER = (241, 236, 222)
AMBER = (226, 163, 92)


def ft(n: int):
    return ImageFont.truetype(FONT_PATH, n)


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x*x*(3-2*x)


def write_stereo(path: Path, left: array, right: array, peak: float = 0.85) -> None:
    top = max(max(left), max(right), abs(min(left)), abs(min(right)), 1e-6)
    scale = min(peak / top, 3.0)
    out = array("h")
    for a, b in zip(left, right):
        out.append(int(max(-32767, min(32767, a*scale*32767))))
        out.append(int(max(-32767, min(32767, b*scale*32767))))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(out.tobytes())


def make_ambience(path: Path) -> None:
    """Separate outdoor crowd air and workshop machinery room tone; no intelligible speech."""
    n = int(DURATION*SR); rng = random.Random(5019)
    left, right = array("f", [0.0])*n, array("f", [0.0])*n
    def weight(t: float) -> tuple[float, float]:
        shop = (0.0 <= t < 13) * 0.18 + (13 <= t < 31) * 0.40 + (31 <= t < 52) * 0.32 + (52 <= t < 70) * 0.62 + (70 <= t < 84) * 0.42 + (84 <= t) * 0.10
        workshop = 0.0 <= t < 13 or 31 <= t < 52 or 70 <= t < 84
        return float(shop), 1.0 if workshop else 0.0

    lo_l = lo_r = mid_l = mid_r = 0.0
    for i in range(n):
        t = i/SR
        a, b = rng.uniform(-1,1), rng.uniform(-1,1)
        lo_l += .003*(a-lo_l); lo_r += .003*(b-lo_r)
        mid_l += .032*(a-mid_l); mid_r += .032*(b-mid_r)
        event, inside = weight(t)
        fan = math.sin(2*math.pi*72*t)*.08 + math.sin(2*math.pi*144*t)*.024
        fade = min(1.0, t/.8, (DURATION-t)/1.8)
        left[i] = ((lo_l*.44 + mid_l*.22)*event + fan*inside*.06)*fade
        right[i] = ((lo_r*.44 + mid_r*.22)*event + fan*inside*.06)*fade
    write_stereo(path,left,right,peak=.16)


def make_event(path: Path) -> None:
    """Original, nonverbal event texture; never imitates an announcement or archive."""
    n = int(DURATION*SR); rng = random.Random(12)
    left, right = array("f", [0.0])*n, array("f", [0.0])*n
    def hit(at: float, length: float, hz: float, gain: float, pan: float):
        begin, count = int(at*SR), int(length*SR)
        lpan, rpan = math.sqrt((1-pan)*.5), math.sqrt((1+pan)*.5)
        for j in range(count):
            ix = begin+j
            if ix >= n: break
            x = j/SR
            env = min(1.0,x/.045)*math.exp(-2.2*x)
            noise = rng.uniform(-1,1)*.24
            val = (math.sin(2*math.pi*hz*x)+noise)*env*gain
            left[ix] += val*lpan; right[ix] += val*rpan

    for at, hz, gain, pan in [(1.3,136,.10,-.3),(3.8,185,.08,.3),(6.3,113,.11,-.2),
                               (14.1,470,.07,.3),(17.8,680,.06,-.4),(23.7,760,.07,.4),
                               (32.8,98,.09,-.3),(37.4,136,.08,.2),(48.5,72,.08,.1),
                               (53.1,115,.12,-.4),(56.4,147,.10,.4),(61.8,98,.12,-.3),
                               (67.3,73,.10,.3),(72.4,136,.08,-.2),(79.2,72,.07,.3),
                               (85.0,430,.06,0)]:
        hit(at,.30 if hz<200 else .14,hz,gain,pan)
    write_stereo(path,left,right,peak=.18)


def make_foley(path: Path) -> None:
    """Timed brush rotation, wheel/road roll, hose checks, glove and stance shifts."""
    n = int(DURATION*SR); left, right = array("f", [0.0])*n, array("f", [0.0])*n
    def add(at: float, length: float, hz: float, gain: float, pan: float, noisy=False):
        begin, count = int(at*SR), int(length*SR)
        lp, rp = math.sqrt((1-pan)*.5), math.sqrt((1+pan)*.5)
        rng = random.Random(int(at*1000)+39)
        for j in range(count):
            ix=begin+j
            if ix>=n: break
            x=j/SR; attack=min(1.0,x/.018)
            env=attack*math.exp(-x*(3.0 if noisy else 7.0))
            noise=rng.uniform(-1,1)*(.44 if noisy else .08)
            v=(math.sin(2*math.pi*hz*x)+noise)*env*gain
            left[ix]+=v*lp; right[ix]+=v*rp

    # Low wheel hum persists only while the illustrated vehicle is in motion.
    for start,end in [(0,13),(16,31),(52,70)]:
        for at in [start+k*.78 for k in range(int((end-start)/.78))]:
            pan=-.7+1.4*((at-start)/(end-start))
            add(at,.21,66,.034,pan,True)
        for at in [start+k*.24 for k in range(int((end-start)/.24))]:
            pan=-.7+1.4*((at-start)/(end-start))
            add(at,.085,190+16*math.sin(at*2),.018,pan,True)
    # Brush disks rotate in pulsed contact with the pavement.
    for start,end in [(1,13),(16,31),(53,70)]:
        for at in [start+k*.46 for k in range(int((end-start)/.46))]:
            pan=-.7+1.4*((at-start)/(end-start))
            add(at,.15,310,.024,pan,True)
    # A gloved check follows the visible tracing motion, then releases to room tone.
    for at,hz,pan,gain in [(33.4,850,-.25,.055),(35.8,690,.1,.05),(38.6,920,.28,.045),
                           (40.85,730,-.2,.045),(47.5,540,.24,.05),(73.2,820,-.18,.042),
                           (77.6,640,.25,.038),(82.0,460,0,.032)]:
        add(at,.12,hz,gain,pan,True)
    write_stereo(path,left,right,peak=.22)


def make_stems() -> None:
    ASSETS.mkdir(exist_ok=True)
    compose("guoqing", ASSETS/"music.wav")
    make_ambience(ASSETS/"ambience.wav")
    make_event(ASSETS/"event_sound.wav")
    make_foley(ASSETS/"sync_foley.wav")


def plate(path: Path, center: tuple[float,float]=(0.5,0.5)) -> Image.Image:
    im=Image.open(path).convert("RGB")
    im=ImageOps.fit(im,SIZE,method=Image.Resampling.LANCZOS,centering=center)
    return ImageEnhance.Color(ImageEnhance.Contrast(im).enhance(1.035)).enhance(.86)


def text(d,xy,s,size,fill=PAPER,anchor=None):
    d.text(xy,s,font=ft(size),fill=fill,anchor=anchor,stroke_width=0)


def load_sweeper(path:Path)->Image.Image:
    im=Image.open(path).convert("RGBA")
    alpha=im.getchannel("A").point(lambda v:255 if v>18 else 0)
    box=alpha.getbbox()
    if box: im=im.crop(box)
    return im


def passing_sweeper(base:Image.Image,sprite:Image.Image,t:float,start:float,end:float,
                    width_start:int,width_end:int,y_start:int,y_end:int)->None:
    """One anonymous vehicle completes a left-to-right pass along the open lane."""
    p=ease((t-start)/(end-start))
    w=int(width_start+(width_end-width_start)*p)
    h=max(1,round(sprite.height*w/sprite.width))
    im=sprite.resize((w,h),Image.Resampling.LANCZOS)
    x=int(-w+(SIZE[0]+w)*p)
    y=int(y_start+(y_end-y_start)*p)
    base.alpha_composite(im,(x,y))


def lower_caption(layer:Image.Image,t:float):
    d=ImageDraw.Draw(layer,"RGBA")
    if 4.8<t<12.8:
        d.text((50,462),"先经过的，是清扫车",font=ft(22),fill=(246,237,220,245),stroke_width=2,stroke_fill=(25,29,29,190))
    elif 15<t<20.8:
        d.text((50,465),"11 辆清扫车",font=ft(20),fill=(244,233,213,244),stroke_width=2,stroke_fill=(25,29,29,190))
    elif 36<t<43.5:
        d.text((50,465),"后来一次跟访：检查液压管路",font=ft(18),fill=(244,233,213,244),stroke_width=2,stroke_fill=(25,29,29,190))


def frame(t:float, avenue:Image.Image, convoy:Image.Image, shop:Image.Image,
          detail_a:Image.Image,detail_b:Image.Image,sprite:Image.Image)->Image.Image:
    if t<13:
        cx=.48+.025*math.sin(t*.19)
        base=ImageOps.fit(avenue,SIZE,method=Image.Resampling.LANCZOS,centering=(cx,.49))
    elif t<16:
        base=ImageOps.fit(convoy,SIZE,method=Image.Resampling.LANCZOS,centering=(.47,.50))
    elif t<31:
        cx=.48+.035*math.sin(t*.23)
        base=ImageOps.fit(avenue,SIZE,method=Image.Resampling.LANCZOS,centering=(cx,.49))
    elif 31<=t<35 or 45<=t<52 or 70<=t<74:
        cx=.54+.035*math.sin(t*.25)
        base=ImageOps.fit(shop,SIZE,method=Image.Resampling.LANCZOS,centering=(cx,.50))
    elif (35<=t<42.6) or (74<=t<79.3):
        a=ImageOps.fit(detail_a,SIZE,method=Image.Resampling.LANCZOS,centering=(.5,.49))
        b=ImageOps.fit(detail_b,SIZE,method=Image.Resampling.LANCZOS,centering=(.5,.49))
        if t<52:
            p=1.0 if t>=40.85 else 0.0
        else:
            p=1.0 if t>=77.6 else 0.0
        base=Image.blend(a,b,p)
    elif (42.6<=t<45) or (79.3<=t<84):
        base=ImageOps.fit(detail_b,SIZE,method=Image.Resampling.LANCZOS,centering=(.5,.49))
    elif t<70:
        cx=.52-.07*ease((t-52)/18)
        base=ImageOps.fit(avenue,SIZE,method=Image.Resampling.LANCZOS,centering=(cx,.49))
    else:
        base=Image.new("RGB",SIZE,(24,27,27))
    base=base.convert("RGBA")
    layer=Image.new("RGBA",SIZE,(0,0,0,0))

    if t<13:
        passing_sweeper(base,sprite,t,0,12.99,315,355,154,160)
    elif 16<=t<31:
        passing_sweeper(base,sprite,t,16,30.99,285,340,155,162)
    elif 52<=t<70:
        passing_sweeper(base,sprite,t,52,69.99,305,365,150,160)

    d=ImageDraw.Draw(layer,"RGBA")
    if t>=84:
        d.rectangle((0,0,960,540),fill=(24,27,27,242))
        d.line((72,96,178,96),fill=AMBER,width=3)
        text(d,(72,128),"情境画面重构 · 非现场档案",26,PAPER)
        text(d,(72,181),"事实依据：新华社人物报道，2019 年 12 月 27 日",18,(220,215,202,238))
        text(d,(72,218),"无真实人物肖像、现场录音或仪式音频",18,(220,215,202,210))
        text(d,(72,251),"旁白为合成配音；车辆与检修动作均为 AI 重构",18,(220,215,202,210))
        text(d,(72,458),"先经过的，是清扫车",20,(229,174,105,235))

    lower_caption(layer,t)
    base.alpha_composite(layer)
    return base.convert("RGB")


def render():
    ASSETS.mkdir(exist_ok=True)
    make_stems()
    avenue=plate(ASSETS/"avenue-empty.png",(.48,.48))
    convoy=plate(ASSETS/"sweeper-line.png",(.48,.50))
    shop=plate(ASSETS/"workshop-reconstruction.png",(.52,.49))
    detail_a=plate(ASSETS/"workshop-closeup.png",(.51,.49))
    detail_b=plate(ASSETS/"workshop-closeup-next.png",(.51,.49))
    sprite=load_sweeper(ASSETS/"sweeper-cutout.png")
    audio=[ASSETS/"music.wav",ASSETS/"sync_foley.wav",ASSETS/"ambience.wav",ASSETS/"event_sound.wav"]
    voice_starts=[.55,6.85,14.25,32.2,53.0,77.4]
    for i,start in enumerate(voice_starts,1): audio.append(ASSETS/f"narration_{i}.wav")
    fparts=["[1:a]volume=.43[m]","[2:a]volume=.82[f]","[3:a]volume=.82[amb]","[4:a]volume=.68[e]"]
    labels=["[m]","[f]","[amb]","[e]"]
    for i,start in enumerate(voice_starts):
        ix=5+i; label=f"[v{i+1}]"; delay=round(start*1000)
        fparts.append(f"[{ix}:a]volume=.96,adelay={delay}|{delay}{label}")
        labels.append(label)
    fparts.append("".join(labels)+f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,afade=t=out:st=88:d=2,alimiter=limit=.91[a]")
    graph=";".join(fparts)
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-y","-f","rawvideo","-pixel_format","rgb24",
         "-video_size",f"{SIZE[0]}x{SIZE[1]}","-framerate",str(FPS),"-i","-"]
    for a in audio: cmd += ["-i",str(a)]
    cmd += ["-filter_complex",graph,"-map","0:v","-map","[a]","-t",str(DURATION),
            "-vf","scale=1920:1080:flags=lanczos,format=yuv420p","-c:v","libx264","-preset","fast","-crf","18",
            "-c:a","aac","-b:a","192k","-movflags","+faststart",str(ROOT/"final.mp4")]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    review=[]
    try:
        for i in range(int(DURATION*FPS)):
            t=i/FPS; im=frame(t,avenue,convoy,shop,detail_a,detail_b,sprite)
            if i%(5*FPS)==0: review.append(im.resize((480,270)))
            proc.stdin.write(im.tobytes())
        proc.stdin.close(); err=proc.stderr.read().decode("utf-8","replace"); code=proc.wait()
        if code: raise RuntimeError(err[-4000:])
    except BaseException:
        if proc.poll() is None: proc.kill()
        raise
    cols=4; rows=math.ceil(len(review)/cols)
    sheet=Image.new("RGB",(cols*480,rows*270),(17,19,19))
    for i,im in enumerate(review): sheet.paste(im,((i%cols)*480,(i//cols)*270))
    sheet.save(ROOT/"review.jpg",quality=91)
    print(f"Rendered {ROOT/'final.mp4'} ({DURATION:.0f}s, 1920x1080, 24fps)")


if __name__=="__main__":
    render()
