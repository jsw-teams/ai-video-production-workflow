from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
TIMELINE = ASSETS / "edit_timeline.json"
OUTPUT = ROOT / "final.mp4"
CAPTIONS = ASSETS / "captions.ass"
QA_PATH = ASSETS / "final_qa.json"
REVIEW = ROOT / "review.jpg"
FPS = 24
TARGET_FRAMES = 4545
TARGET_SECONDS = TARGET_FRAMES / FPS
NARRATION = ASSETS / "voiceover.wav"
MUSIC = ASSETS / "audio" / "mixkit-sun-and-his-daughter.mp3"

PARAGRAPH_WINDOWS = [
    (0.00, 27.70), (27.70, 49.94), (49.94, 77.34), (77.34, 100.94),
    (100.94, 122.08), (122.08, 144.38), (144.38, 162.12), (162.12, TARGET_SECONDS),
]
CHAPTERS = [
    "同一个节日 · 许多种动作", "农历八月十五", "节日逐渐形成", "月饼也有自己的时间",
    "厦门 · 博饼", "香港大坑 · 火龙 / 台湾 · 烤肉", "苏州与海外家庭", "同一天，不同的私人意义",
]


def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise SystemExit("FFmpeg is required. Use the available FFmpeg executable on PATH.")
    return path


def ffprobe_bin() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise SystemExit("FFprobe is required for final technical QA.")
    return path


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=capture)


def ass_time(seconds: float) -> str:
    value = max(0, round(seconds * 100))
    hours, rest = divmod(value, 360000)
    minutes, rest = divmod(rest, 6000)
    whole, centiseconds = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{whole:02d}.{centiseconds:02d}"


def split_lines(text: str, limit: int = 24) -> str:
    lines: list[str] = []
    current = ""
    for char in text.strip():
        current += char
        if len(current) >= limit:
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return r"\N".join(lines)


def write_captions() -> None:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", (ASSETS / "narration.txt").read_text(encoding="utf-8")) if p.strip()]
    if len(paragraphs) != len(PARAGRAPH_WINDOWS):
        raise SystemExit(f"Expected 8 narration paragraphs, found {len(paragraphs)}.")
    content = [
        "[Script Info]", "ScriptType: v4.00+", "WrapStyle: 2", "ScaledBorderAndShadow: yes",
        "PlayResX: 1920", "PlayResY: 1080", "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Caption,Microsoft YaHei,42,&H00FFFFFF,&H000000FF,&H900A151A,&H900A151A,0,0,0,0,100,100,0,0,3,1,0,2,150,150,56,1",
        "Style: Chapter,Microsoft YaHei,34,&H00FFFFFF,&H000000FF,&H700A151A,&H900A151A,0,0,0,0,100,100,0,0,3,1,0,7,82,82,64,1",
        "", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    for index, (paragraph, (start, end), chapter) in enumerate(zip(paragraphs, PARAGRAPH_WINDOWS, CHAPTERS)):
        content.append(f"Dialogue: 1,{ass_time(start)},{ass_time(min(end, start + 4.5))},Chapter,,0,0,0,,{chapter}")
        sentences = [x.strip() for x in re.split(r"(?<=[。！？；])", paragraph) if x.strip()]
        weights = [len(re.sub(r"\s", "", sentence)) + 2.3 for sentence in sentences]
        total_weight = sum(weights) or 1
        cursor = start
        for sentence, weight in zip(sentences, weights):
            sentence_end = cursor + (end - start) * weight / total_weight
            text = split_lines(sentence).replace("{", "\\{").replace("}", "\\}")
            content.append(f"Dialogue: 0,{ass_time(cursor)},{ass_time(sentence_end)},Caption,,0,0,0,,{text}")
            cursor = sentence_end
    CAPTIONS.write_text("\n".join(content) + "\n", encoding="utf-8-sig")


def load_sequence() -> list[dict]:
    plan = json.loads(TIMELINE.read_text(encoding="utf-8"))
    sequence = plan["sequence"]
    frame_total = sum(int(item["frames"]) for item in sequence)
    if frame_total != TARGET_FRAMES or int(plan["target_frames"]) != TARGET_FRAMES:
        raise SystemExit(f"Timeline is {frame_total} frames; expected {TARGET_FRAMES}.")
    for item in sequence:
        item["rendered"] = ASSETS / "rendered_scenes" / f"{sequence.index(item):02d}_{item['id']}.mp4"
        if not item["rendered"].is_file():
            raise SystemExit(f"Missing rendered scene {item['rendered'].name}; run render_2d_scenes.py first.")
    return sequence


def audio_sources() -> list[dict]:
    return [
        {"path": NARRATION, "kind": "voice", "gain": 0.0},
        {"path": MUSIC, "kind": "music", "gain": -18.0},
        {"path": ASSETS / "audio" / "rolling-dice.mp3", "kind": "foley", "gain": -12.0, "delay": 0, "duration": 4.0},
        {"path": ASSETS / "audio" / "ceramic-dish-clank.mp3", "kind": "foley", "gain": -14.0, "delay": 900, "duration": 0.75},
        {"path": ASSETS / "audio" / "ceramic-bowl-roll.mp3", "kind": "foley", "gain": -13.0, "delay": 118080, "duration": 4.8},
        {"path": ASSETS / "audio" / "cutting-pastry.mp3", "kind": "foley", "gain": -16.0, "delay": 82500, "duration": 7.8},
        {"path": ASSETS / "audio" / "mixkit-street-ambience-walking-people.mp3", "kind": "ambience", "gain": -25.0, "delay": 122000, "duration": 11.6},
        {"path": ASSETS / "audio" / "mixkit-frying-fish-hot-pan.mp3", "kind": "foley", "gain": -18.0, "delay": 133200, "duration": 15.0},
    ]


def validate_files(sequence: list[dict], stems: list[dict]) -> None:
    needed = [NARRATION, MUSIC, ASSETS / "narration.txt", CAPTIONS]
    needed.extend(item["rendered"] for item in sequence)
    needed.extend(item["path"] for item in stems)
    missing = [str(path) for path in needed if not Path(path).is_file()]
    if missing:
        raise SystemExit("Missing production inputs:\n" + "\n".join(missing))


def assemble(sequence: list[dict], stems: list[dict]) -> None:
    command = [ffmpeg_bin(), "-hide_banner", "-loglevel", "warning", "-y"]
    for item in sequence:
        command += ["-i", str(item["rendered"])]
    for stem in stems:
        command += ["-i", str(stem["path"])]

    graph: list[str] = []
    video_refs: list[str] = []
    for i in range(len(sequence)):
        graph.append(f"[{i}:v]fps={FPS},setsar=1,setpts=PTS-STARTPTS[v{i}]")
        video_refs.append(f"[v{i}]")
    graph.append("".join(video_refs) + f"concat=n={len(sequence)}:v=1:a=0[vbase]")
    graph.append("[vbase]ass=assets/captions.ass[vout]")

    voice_idx = len(sequence)
    graph.append(f"[{voice_idx}:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,volume=0dB[voice]")
    music_idx = voice_idx + 1
    graph.append(
        f"[{music_idx}:a]atrim=end=167.77,asetpts=PTS-STARTPTS,aresample=48000,"
        "aformat=sample_rates=48000:channel_layouts=stereo,volume=-18dB,afade=t=out:st=160:d=7.3[music]"
    )
    audio_refs = ["[voice]", "[music]"]
    for index, stem in enumerate(stems[2:], start=2):
        input_index = len(sequence) + index
        label = f"fx{index}"
        duration = float(stem["duration"])
        delay = int(stem["delay"])
        gain = float(stem["gain"])
        graph.append(
            f"[{input_index}:a]atrim=duration={duration},asetpts=PTS-STARTPTS,aresample=48000,"
            f"aformat=sample_rates=48000:channel_layouts=stereo,volume={gain}dB,adelay={delay}|{delay}[{label}]"
        )
        audio_refs.append(f"[{label}]")
    graph.append("".join(audio_refs) + f"amix=inputs={len(audio_refs)}:duration=first:dropout_transition=0:normalize=0,"
                 "alimiter=limit=0.94,loudnorm=I=-17:LRA=9:TP=-1.5[aout]")

    command += [
        "-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]",
        "-t", f"{TARGET_SECONDS:.5f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "256k",
        "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(OUTPUT),
    ]
    run(command)


def probe_video() -> dict:
    result = run([
        ffprobe_bin(), "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
        "-of", "json", str(OUTPUT),
    ], capture=True)
    return json.loads(result.stdout)


def make_review_sheet(duration: float) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise SystemExit("Pillow is required for the requested review/contact sheet.") from exc
    frames_dir = ASSETS / "qa_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    font = ImageFont.truetype(str(font_path), 23) if font_path.is_file() else ImageFont.load_default()
    cell_w, image_h, label_h = 480, 270, 32
    sheet = Image.new("RGB", (cell_w * 4, (image_h + label_h) * 4), (237, 228, 209))
    draw = ImageDraw.Draw(sheet)
    for i in range(16):
        seconds = duration * (i + 0.5) / 16
        still = frames_dir / f"frame_{i:02d}.jpg"
        run([
            ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{seconds:.3f}",
            "-i", str(OUTPUT), "-frames:v", "1", "-vf", f"scale={cell_w}:{image_h}", "-q:v", "3", str(still),
        ])
        with Image.open(still) as frame:
            frame = frame.convert("RGB")
            x, y = (i % 4) * cell_w, (i // 4) * (image_h + label_h)
            sheet.paste(frame, (x, y))
            draw.text((x + 10, y + image_h + 3), f"{i + 1:02d} · {seconds:05.1f}s", font=font, fill=(37, 46, 48))
    sheet.save(REVIEW, quality=90, optimize=True)


def technical_qa() -> dict:
    report = probe_video()
    streams = report.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    duration = float(report.get("format", {}).get("duration", 0))
    errors: list[str] = []
    if not video or (video.get("width"), video.get("height"), video.get("r_frame_rate")) != (1920, 1080, "24/1"):
        errors.append("Expected H.264 video at 1920x1080 and 24 fps.")
    if not audio or audio.get("sample_rate") != "48000" or audio.get("channels") != 2:
        errors.append("Expected 48 kHz stereo AAC audio.")
    if abs(duration - TARGET_SECONDS) > 0.12:
        errors.append(f"Duration {duration:.3f}s differs from {TARGET_SECONDS:.3f}s target.")

    decode = subprocess.run([ffmpeg_bin(), "-hide_banner", "-v", "error", "-i", str(OUTPUT), "-f", "null", "-"], cwd=ROOT, capture_output=True, text=True)
    if decode.returncode != 0:
        errors.append("Full-file FFmpeg decode failed: " + decode.stderr.strip()[-500:])

    volume = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", str(OUTPUT), "-vn", "-af", "volumedetect", "-f", "null", "-"], cwd=ROOT, capture_output=True, text=True)
    match_mean = re.search(r"mean_volume:\s*([\-\d.]+) dB", volume.stderr)
    match_peak = re.search(r"max_volume:\s*([\-\d.]+) dB", volume.stderr)
    audio_stats = {
        "mean_volume_dbfs": float(match_mean.group(1)) if match_mean else None,
        "max_volume_dbfs": float(match_peak.group(1)) if match_peak else None,
    }
    if match_peak and float(match_peak.group(1)) > -0.1:
        errors.append("Audio peak is too close to digital clipping.")
    result = {
        "status": "pass" if not errors else "fail",
        "output": "final.mp4",
        "duration_seconds": duration,
        "target_seconds": TARGET_SECONDS,
        "size_bytes": int(report.get("format", {}).get("size", 0)),
        "streams": streams,
        "full_decode": "pass" if decode.returncode == 0 else "fail",
        "audio_stats": audio_stats,
        "subjective_audio_review": "unavailable_in_current_agent_runtime; full decode, mean level and peak were measured",
        "review_sheet": "review.jpg",
        "errors": errors,
    }
    QA_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit("Final QA failed:\n- " + "\n- ".join(errors))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble the Mid-Autumn illustrated documentary, mix narration/music/Foley and run technical QA.")
    parser.add_argument("--skip-render-scenes", action="store_true", help="Reuse the already rendered scene clips.")
    args = parser.parse_args()
    if not args.skip_render_scenes:
        run([sys.executable, str(ROOT / "render_2d_scenes.py")])
    write_captions()
    sequence = load_sequence()
    stems = audio_sources()
    validate_files(sequence, stems)
    print(f"Assembling {len(sequence)} scenes at 24 fps for {TARGET_SECONDS:.3f}s.", flush=True)
    assemble(sequence, stems)
    preliminary = probe_video()
    duration = float(preliminary.get("format", {}).get("duration", TARGET_SECONDS))
    make_review_sheet(duration)
    qa = technical_qa()
    print(json.dumps(qa, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
