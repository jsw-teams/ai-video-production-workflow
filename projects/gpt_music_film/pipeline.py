"""Render the GPT audiovisual film, original score, Foley, and review sheet."""
from __future__ import annotations

from array import array
import math
import random
import subprocess
import sys
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
import yaml

from score_engine import compose

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
PROJECT = yaml.safe_load((ROOT / "project.yaml").read_text(encoding="utf-8"))
DURATION = float(PROJECT["target_duration_seconds"])
FPS = 24
SIZE = (960, 540)
SR = 22050
FONT_PATH = r"C:\Windows\Fonts\STSONG.TTF"


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def fit(path: Path) -> Image.Image:
    im = Image.open(path).convert("RGB")
    im = ImageOps.fit(im, SIZE, method=Image.Resampling.LANCZOS)
    return ImageEnhance.Color(ImageEnhance.Contrast(im).enhance(1.04)).enhance(0.82)


def write_stereo(path: Path, left: array, right: array, peak: float = 0.9) -> None:
    top = max(max(left), max(right), abs(min(left)), abs(min(right)), 1e-6)
    scale = min(peak / top, 3.0)
    out = array("h")
    for a, b in zip(left, right):
        out.append(int(max(-32767, min(32767, a * scale * 32767))))
        out.append(int(max(-32767, min(32767, b * scale * 32767))))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SR)
        wav.writeframes(out.tobytes())


def make_event_stem(path: Path, duration: float, events: list[tuple[float, float, float, float, float]], seed: int) -> None:
    n = int(duration * SR)
    left, right = array("f", [0.0]) * n, array("f", [0.0]) * n
    rng = random.Random(seed)
    for start, length, hz, gain, pan in events:
        begin, count = int(start * SR), min(int(length * SR), n - int(start * SR))
        if count <= 0:
            continue
        lpan, rpan = math.sqrt((1-pan)*0.5), math.sqrt((1+pan)*0.5)
        for j in range(count):
            x = j / SR
            env = math.sin(math.pi * min(1.0, x / 0.018)) if x < 0.018 else math.exp(-x * (8.0 if hz > 150 else 3.5))
            tone = math.sin(2*math.pi*hz*x) + 0.25*math.sin(2*math.pi*(hz*2.7)*x)
            noise = rng.uniform(-1.0, 1.0) * (0.32 if hz > 120 else 0.12)
            v = (tone + noise) * env * gain
            idx = begin + j
            left[idx] += v * lpan
            right[idx] += v * rpan
    write_stereo(path, left, right, peak=0.45)


def make_ambience(path: Path, duration: float) -> None:
    n = int(duration * SR)
    rng = random.Random(41028)
    left, right = array("f", [0.0]) * n, array("f", [0.0]) * n
    low_l = low_r = 0.0
    for i in range(n):
        a, b = rng.uniform(-1, 1), rng.uniform(-1, 1)
        low_l += 0.018 * (a - low_l)
        low_r += 0.018 * (b - low_r)
        t = i / SR
        level = 0.28 if t < 14 or t > 83 else 0.50
        fade = min(1.0, t / 1.0, (duration-t) / 1.7)
        left[i] = low_l * level * fade * 0.045
        right[i] = low_r * level * fade * 0.045
    write_stereo(path, left, right, peak=0.14)


def make_stems() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    compose("gpt_music_film", ASSETS / "music.wav")
    make_ambience(ASSETS / "ambience.wav", DURATION)
    make_event_stem(ASSETS / "sync_foley.wav", DURATION, [
        (0.22,.05,1650,.18,-.35),(0.43,.06,1200,.15,-.25),(13.6,.08,760,.13,.18),
        (14.0,.05,1520,.14,.18),(28.1,.07,950,.14,-.28),(42.2,.08,540,.13,.24),
        (56.9,.06,1440,.11,-.16),(57.35,.07,680,.16,.28),(83.4,.06,980,.10,-.3),
        (87.1,.05,1300,.12,.3),(94.2,.08,750,.11,-.12),(100.8,.06,1250,.16,.2),
    ], seed=4)
    make_event_stem(ASSETS / "event_sound.wav", DURATION, [
        (57.0,.18,420,.19,-.35),(60.7,.16,530,.16,.32),(64.4,.15,360,.15,-.18),
        (71.0,.10,310,.09,0),(83.0,.14,620,.11,.3),(89.2,.12,490,.10,-.3),
    ], seed=9)


def ease(v: float) -> float:
    v = max(0.0, min(1.0, v))
    return v*v*(3-2*v)


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int,int], text: str, size: int, fill: tuple[int,int,int], anchor=None) -> None:
    draw.text(xy, text, font=font(size), fill=fill, anchor=anchor, stroke_width=0)


def draw_caption(draw: ImageDraw.ImageDraw, t: float, section: int) -> None:
    # Research dates remain in project.yaml and the closing source line; the film
    # advances through changing work relations rather than chapter cards.
    return


def draw_spectrum(draw: ImageDraw.ImageDraw, t: float, y0: int, width: int, height: int, seed: int = 0) -> None:
    for i in range(42):
        x = 355 + i * (width / 42)
        phase = t*2.4 + i*.31 + seed
        h = 7 + (0.5 + .5*math.sin(phase)) * (height*.72)
        col = (221,159,96) if i % 5 == 0 else (217,211,194)
        draw.rounded_rectangle((int(x),int(y0+height-h),int(x+5),int(y0+height)),radius=2,fill=col)


def frame(t: float, side: Image.Image, overhead: Image.Image) -> Image.Image:
    if t < 14 or 28 <= t < 42 or 57 <= t < 83:
        base = side.copy()
    else:
        base = overhead.copy()
    # A restrained grade keeps generated plate detail, while the authored motion carries the argument.
    overlay = Image.new("RGBA", SIZE, (0,0,0,0))
    d = ImageDraw.Draw(overlay, "RGBA")
    charcoal, paper, amber, rust = (27,30,31,238), (239,231,214,245), (228,167,102,250), (177,101,67,245)

    # The opening line begins on an otherwise blank screen, then overruns it.
    if t < 14:
        d.rectangle((528,24,959,304),fill=(22,24,25,245))
        title_alpha = int(255 * (1-ease((t-3.5)/1.1))) if t > 3.5 else int(255*ease(t/1.0))
        if title_alpha > 0:
            draw_text(d,(48,365),"从一句话",44,(241,230,209,title_alpha))
            draw_text(d,(48,419),"到一项事",44,(228,167,102,title_alpha))
        prompt = "帮我修好这段代码里的错误"
        count = min(len(prompt),max(0,int((t-2.0)*2.0)))
        draw_text(d,(563,82),prompt[:count],22,(233,226,210,248))
        cursor_x = 564 + min(count*22, 340)
        d.rectangle((cursor_x,112,cursor_x+2,141),fill=amber)
        # One empty thread becomes a line of possible continuations.
        if t > 6:
            visible = min(4,int((t-6)*.55))
            for j in range(visible):
                yy = 166+j*27
                length = 85 + 24*((j+int(t*2))%4)
                d.line((564,yy,564+length,yy),fill=(198,190,174,170),width=2)
    elif t < 28:
        # A repeated pattern is copied onto paper, and the lines begin to branch.
        examples=["夜雨停了，","路口的水还亮着。","车灯经过以后，"]
        for j,line in enumerate(examples):
            start=14.7+j*3.1
            f=ease((t-start)/.48)
            if f>0:
                yy=254+j*34
                draw_text(d,(301,yy),line,max(13,int(17*f)),(49,49,44,int(190*f)))
                d.line((292,yy+23,422+int(46*f),yy+23),fill=(133,95,66,int(70*f)),width=1)
        progress=ease((t-16)/10)
        for j in range(3):
            x=319+j*36+int(8*math.sin(t*1.2+j))
            y=365+int(7*math.sin(t*1.7+j*.6))
            if t>17+j*1.4:
                d.ellipse((x,y,x+5,y+5),fill=(177,101,67,90+int(110*progress)))
                if j:
                    d.line((x-39,y-6,x,y+2),fill=(177,101,67,105),width=1)
    elif t < 42:
        # A reply is crossed out, altered, and returned; the computer stays in the room.
        d.line((550,58,550,259),fill=(228,167,102,125),width=2)
        exchanges=[("人","再试一次"),("模型","先看这一行"),("人","删掉多余部分"),("模型","现在能运行了")]
        for j,(label,txt) in enumerate(exchanges):
            yy=75+j*48
            appear=ease((t-(28.7+j*2.6))/.4)
            if appear>0:
                x=564+(18 if j%2 else 0)
                col=(230,180,119,230) if j%2==0 else (206,216,202,225)
                draw_text(d,(x,yy),label+" / ",14,col)
                draw_text(d,(x+61,yy),txt,18,(239,231,214,int(235*appear)))
                d.line((x+61,yy+25,x+149,yy+25),fill=(226,167,102,int(90*appear)),width=1)
        # The pencil stroke beneath the monitor changes direction with the exchange.
        x=130+int(290*ease((t-31)/9))
        d.line((116,361,x,342+int(12*math.sin(t*2))),fill=(177,101,67,205),width=3)
        d.line((x-11,350,x+4,334),fill=(42,42,38,230),width=3)
    elif t < 57:
        # The printed landscape, pencil marks and sound trace occupy one shared sheet.
        d.line((168,332,298,300),fill=(228,167,102,170),width=2)
        d.ellipse((163,327,173,337),fill=(228,167,102,210))
        for j in range(34):
            x=292+j*4.4
            y=306+16*math.sin((t-42)*2.1+j*.44)
            d.line((x,y-2,x,y+2+2*math.sin(j*.7)),fill=(79,95,79,205) if j%4 else (177,101,67,225),width=2)
        draw_text(d,(306,352),"图像　文字　声音",15,(82,76,65,220))
        # A broken orbit joins the modalities without turning them into boxed features.
        progress=ease((t-44)/11)
        d.arc((286,274,498,405),185,185+150*progress,fill=(177,101,67,125),width=1)
    elif t < 70:
        # A request reaches a tool, waits for its return, and resumes on the same screen.
        draw_text(d,(557,82),"请求",17,(239,231,214,230))
        draw_text(d,(728,82),"执行",17,(228,167,102,230))
        draw_text(d,(861,82),"返回",17,(239,231,214,230))
        d.line((590,140,754,140),fill=(232,225,210,185),width=2)
        d.line((772,140,888,140),fill=(232,225,210,185),width=2)
        d.polygon([(751,135),(760,140),(751,145)],fill=amber)
        d.polygon([(885,135),(894,140),(885,145)],fill=paper)
        for x in (577,741,850):
            d.ellipse((x,166,x+12,178),outline=amber,width=2)
        # The cursor leaves the display and runs along its lower edge.
        p=ease((t-58)/10)
        x=576+286*p
        d.ellipse((int(x),220,int(x+8),228),fill=amber)
        d.line((579,224,x+3,224),fill=(228,167,102,130),width=1)
    elif t < 83:
        draw_caption(d,t,5)
        # At 70 seconds the entire frame loses the beat; elements reorganize slowly.
        d.rectangle((500,0,960,325),fill=(21,23,24,248))
        if t < 73:
            d.rectangle((0,0,960,540),fill=(19,21,22,215))
        else:
            progress=ease((t-73)/9)
            for j in range(11):
                x=572+j*29
                y=85+int(70*math.sin(j*.62+t*.28)*(1-progress))
                d.line((x,95,x,220),fill=(228,167,102,110+int(110*progress)),width=2)
                d.ellipse((x-4,y,x+4,y+8),fill=paper)
            draw_text(d,(563,255),"等待 · 重新组织",16,(232,225,210,210))
    else:
        # Several steps now fit inside a task. Their trail crosses the laptop display,
        # returns to the paper, and ends in the human hand's short verification stroke.
        tasks=["读入","比对","执行","复核"]
        for j,task in enumerate(tasks):
            x=600+j*68; y=102+int(13*math.sin(t*1.1+j*.75))
            if t>84+j*2.2:
                draw_text(d,(x,y),task,13,(239,231,214,218))
                d.ellipse((x+19,y+25,x+24,y+30),fill=amber)
                if j<3:
                    d.line((x+35,y+7,x+60,y+7),fill=(228,167,102,175),width=1)
        progress=ease((t-92)/10)
        d.line((630,171,490-105*progress,231+110*progress),fill=(228,167,102,150),width=2)
        x=389+int(112*ease((t-94)/5))
        y=287+int(70*ease((t-94)/5))
        d.ellipse((x-3,y-3,x+3,y+3),fill=rust)
        if t>100:
            d.line((x-26,y+14,x+29,y-4),fill=(177,101,67,230),width=3)
            d.line((x-9,y+5,x+6,y+1),fill=(45,43,37,230),width=1)
        if t>102:
            draw_text(d,(56,478),"OpenAI 公开研究与产品资料｜画面及声音为创作重构",15,(73,68,59,210))

    # Fine grain and sparse labels integrate the authored graphics with the tactile plate.
    alpha = overlay.getchannel("A")
    base = base.convert("RGBA")
    base.alpha_composite(overlay)
    result=base.convert("RGB")
    return result


def render() -> None:
    ASSETS.mkdir(exist_ok=True)
    make_stems()
    side, overhead = fit(ASSETS/"worktable-side.png"), fit(ASSETS/"worktable-overhead.png")
    review=[]
    audio_paths=[ASSETS/"music.wav",ASSETS/"sync_foley.wav",ASSETS/"ambience.wav",ASSETS/"event_sound.wav"]
    graph=("[1:a]volume=0.52[m];[2:a]volume=0.92[f];[3:a]volume=0.72[r];[4:a]volume=0.72[e];"
           "[m][f][r][e]amix=inputs=4:duration=longest:dropout_transition=0:normalize=0,alimiter=limit=0.91[a]")
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-y","-f","rawvideo","-pixel_format","rgb24",
         "-video_size",f"{SIZE[0]}x{SIZE[1]}","-framerate",str(FPS),"-i","-"]
    for p in audio_paths: cmd += ["-i",str(p)]
    cmd += ["-filter_complex",graph,"-map","0:v","-map","[a]","-t",str(DURATION),
            "-vf","scale=1920:1080:flags=lanczos,format=yuv420p","-c:v","libx264","-preset","fast","-crf","18",
            "-c:a","aac","-b:a","192k","-movflags","+faststart",str(ROOT/"final.mp4")]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        total=int(DURATION*FPS)
        for i in range(total):
            t=i/FPS
            im=frame(t,side,overhead)
            if i % (5*FPS) == 0:
                review.append(im.resize((480,270)))
            proc.stdin.write(im.tobytes())
        proc.stdin.close()
        err=proc.stderr.read().decode("utf-8","replace")
        code=proc.wait()
        if code:
            raise RuntimeError(err[-4000:])
    except BaseException:
        if proc.poll() is None:
            proc.kill()
        raise
    cols=3
    rows=math.ceil(len(review)/cols)
    sheet=Image.new("RGB",(cols*480,rows*270),(18,20,21))
    for i,im in enumerate(review): sheet.paste(im,((i%cols)*480,(i//cols)*270))
    sheet.save(ROOT/"review.jpg",quality=90)
    print(f"Rendered {ROOT/'final.mp4'} ({DURATION:.0f}s, 1920x1080, 24fps)")


if __name__ == "__main__":
    render()
