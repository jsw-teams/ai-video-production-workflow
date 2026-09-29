"""Assemble and review the illustrated documentary using local FFmpeg."""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT = Path(__file__).resolve().parent
ASSETS = PROJECT / "assets"
FRAMES = ASSETS / "generated"
RENDERS = PROJECT / "renders"
FPS = 24
W, H = 1920, 1080
FONT = r"C\:/Windows/Fonts/segoeui.ttf"
BOLD = r"C\:/Windows/Fonts/georgiab.ttf"

# The cut follows the pauses in the existing System.Speech narration. Intercut
# the historical illustrations with ordinary city life so the dates do not read
# as three isolated national title cards.
SCENES = [
    (0.00, 7.78, "private_days_04", "A DATE ON THE CALENDAR", "in"),
    (7.78, 12.63, "city_rhythms_01", "TAIWAN · OCTOBER 10", "right"),
    (12.63, 16.53, "date_origins_02", "WUCHANG UPRISING · 1911", "left"),
    (16.53, 18.33, "city_rhythms_03", "A DOCUMENT, A PUBLIC DATE", "right"),
    (18.33, 29.22, "date_origins_04", "JULY 4 · ADOPTED IN 1776", "in"),
    (29.22, 30.92, "city_rhythms_02", "SINGAPORE · AUGUST 9", "left"),
    (30.92, 38.60, "city_rhythms_02", "SEPARATION · INDEPENDENCE · 1965", "right"),
    (38.60, 44.30, "date_origins_01", "REVOLUTION · DECLARATION · SEPARATION", "out"),
    (44.30, 50.64, "city_rhythms_04", "ONE PUBLIC DATE · MANY PRIVATE DAYS", "right"),
    (50.64, 52.87, "private_days_01", "ROUTES TURN", "left"),
    (52.87, 56.12, "private_days_02", "THE WORK BEHIND THE EVENT", "right"),
    (56.12, 60.18, "private_days_03", "THE DAY KEEPS GOING AT HOME", "in"),
    (60.18, 63.64, "private_days_04", "A QUIET SIDE STREET", "right"),
    (63.64, 65.74, "city_rhythms_03", "SOME CELEBRATE", "in"),
    (65.74, 69.58, "private_days_03", "SOME WORK · SOME STAY HOME", "left"),
    (69.58, 75.9678, "private_days_03", "THE PUBLIC STORY SETS THE DATE", "out"),
]

# Sentence captions are timed to pauses in the supplied narration. They remain
# readable subtitles; dates and historical claims are typeset in the picture.
CAPTIONS = [
    (0.20, 3.35, "A date on the national calendar can look like a single mark."),
    (4.55, 6.72, "But it can stand for very different beginnings."),
    (7.84, 8.55, "In Taiwan,"),
    (9.15, 12.05, "October tenth commemorates the Wuchang Uprising,"),
    (12.72, 15.49, "the beginning of the 1911 Xinhai Revolution."),
    (16.62, 17.75, "In the United States,"),
    (18.42, 25.83, "July fourth is the day the Continental Congress adopted the Declaration of Independence in 1776."),
    (26.98, 28.68, "The parchment signing began later, in August."),
    (29.30, 29.88, "Singapore's"),
    (31.00, 37.49, "August ninth marks the 1965 separation from Malaysia and independence as a republic."),
    (38.69, 39.46, "Revolution."),
    (40.58, 41.33, "Declaration."),
    (42.47, 43.25, "Separation."),
    (44.40, 46.28, "These are not one historical template, and a public date"),
    (46.98, 49.58, "does not give everyone the same day."),
    (50.74, 51.85, "Traffic turns away."),
    (52.96, 55.02, "Crews bring out the chairs and cables."),
    (56.20, 59.12, "Families make dinner between the parade and the evening shift."),
    (60.27, 62.59, "Someone watches from a quiet side street."),
    (63.72, 64.70, "Some celebrate."),
    (65.84, 66.42, "Some work."),
    (67.56, 68.52, "Some stay home."),
    (69.68, 71.31, "The public story sets the date."),
    (72.43, 75.10, "People decide what that date does in ordinary time."),
]


def run(*args: str, cwd: Path = PROJECT) -> str:
    result = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def probe_duration(path: Path) -> float:
    raw = run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path))
    return float(raw)


def srt_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02},{milliseconds:03}"


def write_captions(path: Path, duration: float) -> None:
    lines = []
    for index, (start, end, caption) in enumerate(CAPTIONS, 1):
        # Clamp slightly if a regenerated voice file is a few frames shorter.
        end = min(end, duration - 0.12)
        if end <= start:
            continue
        lines.extend((str(index), f"{srt_timestamp(start)} --> {srt_timestamp(end)}", caption, ""))
    path.write_text("\n".join(lines), encoding="utf-8-sig")


def render_shot(index: int, scene: tuple[float, float, str, str, str], total_frames: int) -> Path:
    start, end, image_id, label, motion = scene
    image = FRAMES / f"{image_id}.jpg"
    if not image.exists():
        raise SystemExit(f"Required cropped storyboard frame is missing: {image}")
    first_frame = round(start * FPS)
    last_frame = min(total_frames, round(end * FPS))
    count = last_frame - first_frame
    if count < 1:
        raise SystemExit(f"Scene {index} is shorter than one frame.")

    if motion == "out":
        zoom = f"1.035-0.034*on/{count}"
    else:
        zoom = f"1.001+0.034*on/{count}"
    pan = {"left": 0.20, "right": 0.80, "in": 0.48, "out": 0.52}[motion]
    x = f"(iw-iw/zoom)*({pan:.2f}+0.08*on/{count})"
    y = f"(ih-ih/zoom)*(0.45+0.10*on/{count})"
    vf = (
        f"scale=2048:1152,crop=2048:1152,"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={FPS},"
        "drawbox=x=86:y=52:w=1040:h=126:color=0xf3ead9@0.91:t=fill,"
        "drawbox=x=86:y=52:w=11:h=126:color=0xb74d3e@0.98:t=fill,"
        f"drawtext=fontfile='{BOLD}':text='{label}':fontcolor=0x2e2a26:fontsize=33:x=126:y=91:"
        "alpha='min(1,t*2.8)',"
        "drawbox=x=126:y=151:w='min(690,max(0,t*900))':h=3:color=0xb74d3e@0.9:t=fill"
    )
    output = RENDERS / f"shot_{index:02}.mp4"
    run(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", str(FPS), "-i", str(image),
        "-frames:v", str(count), "-vf", vf, "-an", "-r", str(FPS),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        str(output),
    )
    return output


def make_review_sheet(path: Path, duration: float) -> None:
    samples = [min(duration - 0.15, (start + end) / 2) for start, end, *_ in SCENES]
    thumb_w, thumb_h, header_h, footer_h = 480, 270, 72, 34
    columns = 4
    rows = math.ceil(len(samples) / columns)
    sheet = Image.new("RGB", (columns * thumb_w, header_h + rows * (thumb_h + footer_h)), "#eee6d7")
    draw = ImageDraw.Draw(sheet)
    font_path = "C:/Windows/Fonts/segoeui.ttf"
    bold_path = "C:/Windows/Fonts/segoeuib.ttf"
    title_font = ImageFont.truetype(bold_path, 27)
    note_font = ImageFont.truetype(font_path, 17)
    draw.text((28, 20), "A DATE ON THE CALENDAR  /  REVIEW CONTACT SHEET", font=title_font, fill="#2c2925")

    for index, (timecode, scene) in enumerate(zip(samples, SCENES), 1):
        start, end, _, label, _ = scene
        frame_path = RENDERS / f"review_{index:02}.jpg"
        run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{timecode:.3f}", "-i", str(PROJECT / "final.mp4"),
            "-frames:v", "1", "-q:v", "3", str(frame_path))
        with Image.open(frame_path) as source:
            thumb = source.convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        col, row = (index - 1) % columns, (index - 1) // columns
        x, y = col * thumb_w, header_h + row * (thumb_h + footer_h)
        sheet.paste(thumb, (x, y))
        draw.rectangle((x, y + thumb_h, x + thumb_w, y + thumb_h + footer_h), fill="#f7f1e6")
        draw.text((x + 9, y + thumb_h + 7), f"{start:05.1f}–{end:05.1f}s  {label}", font=note_font, fill="#39332d")
    sheet.save(path, quality=91, optimize=True)


def main() -> None:
    manifest_path = PROJECT / "asset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    narration = ASSETS / "audio" / "narration.wav"
    scoreless_foley = ASSETS / "audio"
    traffic = scoreless_foley / "city-night-ambience.mp3"
    crowd = scoreless_foley / "parade-crowd.mp3"
    firework = scoreless_foley / "single-firework.mp3"
    for required in (narration, traffic, crowd, firework):
        if not required.is_file():
            raise SystemExit(f"Required local audio asset is missing: {required}")

    duration = probe_duration(narration)
    RENDERS.mkdir(exist_ok=True)
    total_frames = round(duration * FPS)
    clips = [render_shot(i, scene, total_frames) for i, scene in enumerate(SCENES, 1)]
    concat_file = RENDERS / "visual_concat.txt"
    concat_file.write_text("\n".join(f"file '{clip.as_posix()}'" for clip in clips), encoding="utf-8")
    picture = RENDERS / "picture.mp4"
    run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", str(picture))

    captions = RENDERS / "captions.srt"
    write_captions(captions, duration)
    subtitle_filter = (
        "subtitles=filename='renders/captions.srt':"
        "force_style='FontName=Segoe UI,FontSize=28,PrimaryColour=&H00FFF7E8,"
        "OutlineColour=&H8016100C,BackColour=&H8E1B1916,BorderStyle=3,Outline=0,"
        "Shadow=0,MarginV=64,Alignment=2'"
    )
    end = f"{duration:.3f}"
    audio_filter = (
        "[1:a]aresample=48000,aformat=channel_layouts=stereo,highpass=f=75,"
        "acompressor=threshold=-22dB:ratio=2.0:attack=16:release=230,"
        "loudnorm=I=-18:TP=-2:LRA=10[narr];"
        f"[2:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{end},volume=0.06,"
        f"afade=t=in:st=0:d=2,afade=t=out:st={max(0.0, duration-4):.3f}:d=4[city];"
        "[3:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:20,adelay=48000|48000,volume=0.10[people];"
        "[4:a]aresample=48000,aformat=channel_layouts=stereo,adelay=63500|63500,volume=0.12[firework];"
        "[narr][city][people][firework]"
        "amix=inputs=4:duration=first:dropout_transition=1:normalize=0,"
        "loudnorm=I=-16:TP=-1.5:LRA=9[aout]"
    )
    final = PROJECT / "final.mp4"
    run(
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-i", str(picture), "-i", str(narration), "-stream_loop", "-1", "-i", str(traffic),
        "-i", str(crowd), "-i", str(firework), "-filter_complex", f"[0:v]{subtitle_filter}[v];{audio_filter}",
        "-map", "[v]", "-map", "[aout]", "-t", end,
        "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(final),
    )

    probe = json.loads(run("ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_type,width,height,r_frame_rate,sample_rate,channels", "-of", "json", str(final)))
    streams = probe.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if video_stream is None:
        raise SystemExit("QA failed: the final has no video stream.")
    if audio_stream is None:
        raise SystemExit("QA failed: the final has no audio stream.")
    if (int(video_stream.get("width", 0)), int(video_stream.get("height", 0))) != (W, H):
        raise SystemExit("QA failed: the final video dimensions are not 1920x1080.")
    if int(audio_stream.get("channels", 0)) != 2:
        raise SystemExit("QA failed: final audio is not stereo.")
    encoded_duration = float(probe["format"]["duration"])
    if abs(encoded_duration - duration) > 0.15:
        raise SystemExit(f"QA failed: final duration {encoded_duration:.3f}s differs from narration {duration:.3f}s.")
    run("ffmpeg", "-hide_banner", "-v", "error", "-i", str(final), "-f", "null", "-")
    make_review_sheet(PROJECT / "review.jpg", encoded_duration)

    manifest["delivery"] = {
        "status": "rendered_local",
        "output_path": "final.mp4",
        "review_path": "review.jpg",
        "duration_seconds": round(encoded_duration, 3),
        "video": "1920x1080, 24 fps, H.264/yuv420p",
        "audio": "AAC stereo, 48 kHz; offline narration, CC0 city/crowd/firework sound",
        "music": "No music bed used in this render.",
        "qa": "ffprobe confirmed audio and video streams; full FFmpeg decode passed.",
        "provider_used": "FFmpeg 8.1.2 local assembly and motion graphics",
    }
    for asset in manifest.get("assets", []):
        if asset.get("id") == "narration":
            asset["status"] = "used"
            asset["provider_used"] = "Microsoft Zira Desktop via Windows System.Speech"
        elif asset.get("id") in {"city_ambience", "parade_crowd", "firework"}:
            asset["status"] = "used"
            asset["provider_used"] = "Freesound CC0 source preview"
        elif asset.get("id") == "score":
            asset["status"] = "not_used"
            asset["source_or_license"] = None
            asset["generation_method"] = "Not generated for this render."
            asset.pop("provider_used", None)
            asset.pop("output_path", None)
            asset["reason"] = "No project-specific instrumental was generated; this render uses narration and licensed environmental sound."
            for unused in ("generation_task_id", "prompt", "duration_seconds", "tempo_bpm", "key", "seed"):
                asset.pop(unused, None)
        elif asset.get("id") == "final_film":
            asset["status"] = "rendered_local_qa_pass"
            asset["provider_used"] = "FFmpeg 8.1.2 local assembly"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {final} ({final.stat().st_size:,} bytes; {encoded_duration:.3f}s) and {PROJECT / 'review.jpg'}")
    print("QA: video and audio streams present; full decode passed; narration/video durations match.")


if __name__ == "__main__":
    main()
