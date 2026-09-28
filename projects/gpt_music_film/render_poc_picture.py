"""Render the lyric-timed GPT POC as original moving office motion graphics."""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT = Path(__file__).resolve().parent
ASSETS = PROJECT / "assets"
WIDTH, HEIGHT, FPS = 1920, 1080, 24
INK = "#272821"
RED = "#C44332"
PAPER = "#F1EBDD"
MUTED = "#827A68"
RULE = "#D4CCB8"


def font_path(bold: bool = False, mono: bool = False) -> str:
    root = Path(r"C:\Windows\Fonts")
    if mono:
        name = "consolab.ttf" if bold else "consola.ttf"
    else:
        name = "arialbd.ttf" if bold else "arial.ttf"
    path = root / name
    if not path.is_file():
        raise FileNotFoundError(f"Required system font is missing: {path}")
    return str(path)


FONTS: dict[tuple[int, bool, bool], ImageFont.FreeTypeFont] = {}


def get_font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold, mono)
    if key not in FONTS:
        FONTS[key] = ImageFont.truetype(font_path(bold, mono), size)
    return FONTS[key]


def ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def smooth_pulse(t: float, beats: list[float], width: float = 0.16) -> float:
    if not beats:
        return 0.0
    nearest = min(abs(t - beat) for beat in beats)
    return max(0.0, 1.0 - nearest / width)


def lyric_word(lines: list[dict], value: str) -> dict | None:
    wanted = re.sub(r"[^a-z0-9']", "", value.lower())
    for line in lines:
        for word in line.get("words", []):
            actual = re.sub(r"[^a-z0-9']", "", str(word.get("text", "")).lower())
            if actual == wanted and float(word.get("start_seconds", -1)) >= 0:
                return word
    return None


def lyric_progress(lines: list[dict], value: str, t: float) -> float | None:
    word = lyric_word(lines, value)
    if not word:
        return None
    start = float(word["start_seconds"])
    end = max(start + 0.04, float(word["end_seconds"]))
    if t < start or t > end:
        return None
    return ease((t - start) / (end - start))


def draw_pencil(draw: ImageDraw.ImageDraw, tip_x: int, tip_y: int) -> None:
    draw.polygon(((tip_x, tip_y), (tip_x + 246, tip_y - 70), (tip_x + 269, tip_y - 48), (tip_x + 23, tip_y + 22)), fill="#B64836")
    draw.polygon(((tip_x, tip_y), (tip_x + 24, tip_y - 16), (tip_x + 31, tip_y + 5)), fill="#493D30")
    draw.line((tip_x + 72, tip_y - 20, tip_x + 225, tip_y - 63), fill="#E59D82", width=5)


def paper_surface(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], seed: int, tint: str = PAPER) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0 + 12, y0 + 16, x1 + 12, y1 + 16), radius=14, fill="#B7AD98")
    draw.rounded_rectangle(box, radius=14, fill=tint, outline="#C5BCA9", width=2)
    rng = random.Random(seed)
    for _ in range(95):
        x = rng.randint(x0 + 22, x1 - 22)
        y = rng.randint(y0 + 20, y1 - 18)
        shade = rng.choice(("#E8E1D2", "#F5F0E5", "#DED7C7"))
        draw.line((x, y, x + rng.randint(2, 19), y), fill=shade, width=1)


def draw_word_line(
    draw: ImageDraw.ImageDraw,
    line: dict,
    t: float,
    x: int,
    y: int,
    max_width: int,
    size: int,
    bar_times: list[float],
) -> None:
    words = line.get("words", [])
    if not words:
        return
    face = get_font(size, bold=True)
    space = draw.textlength(" ", font=face)
    cursor_x = x
    row_y = y
    active_word = -1
    for index, word in enumerate(words):
        word_text = str(word.get("text", ""))
        bounds = draw.textbbox((0, 0), word_text, font=face)
        word_w = bounds[2] - bounds[0]
        if cursor_x + word_w > x + max_width and cursor_x > x:
            cursor_x = x
            row_y += size + 17
        start = float(word.get("start_seconds", -1))
        end = float(word.get("end_seconds", -1))
        is_active = start <= t <= end and end > start
        color = RED if is_active else INK
        draw.text((cursor_x, row_y), word_text, font=face, fill=color)
        if is_active:
            active_word = index
            baseline = row_y + size + 4
            pulse = smooth_pulse(t, bar_times)
            draw.line((cursor_x, baseline, cursor_x + word_w, baseline), fill=RED, width=4 + int(3 * pulse))
        cursor_x += word_w + space
    line_start = float(line.get("start_seconds", -1))
    line_end = float(line.get("end_seconds", -1))
    if active_word < 0 and line_start <= t <= line_end and line_end > line_start:
        progress = ease((t - line_start) / (line_end - line_start))
        draw.line((x, row_y + size + 10, x + int(max_width * progress), row_y + size + 10), fill=RED, width=3)


def active_line(lines: list[dict], t: float) -> dict | None:
    for line in lines:
        start = float(line.get("start_seconds", -1))
        end = float(line.get("end_seconds", -1))
        if start <= t <= end and end > start:
            return line
    return None


def doc_rules(draw: ImageDraw.ImageDraw, x: int, y: int, widths: list[int], gap: int = 27, color: str = RULE) -> None:
    for index, width in enumerate(widths):
        yy = y + index * gap
        draw.line((x, yy, x + width, yy), fill=color, width=2)


def checkbox(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, active: bool, pulse: float = 0.0) -> None:
    edge = RED if active else "#605C4E"
    weight = 4 if active or pulse > 0.2 else 2
    draw.rectangle((x, y, x + size, y + size), outline=edge, width=weight)
    if active:
        draw.line((x + 6, y + size // 2, x + size // 2 - 2, y + size - 7, x + size - 5, y + 5), fill=RED, width=5, joint="curve")


def setup_redline(canvas: Image.Image, t: float, local_beats: list[float], lines: list[dict]) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill="#E4DDCF")
    draw.rectangle((0, 0, WIDTH, 95), fill="#D8D0C1")
    draw.text((104, 34), "SOURCE CHECK / WORKING COPY", font=get_font(25, bold=True, mono=True), fill=INK)
    draw.text((WIDTH - 428, 35), "REV. 04     08:59", font=get_font(22, mono=True), fill=MUTED)

    paper_surface(draw, (105, 148, 1260, 974), seed=21)
    draw.text((165, 196), "CLIENT DECK  /  BEFORE IT SHIPS", font=get_font(31, bold=True), fill=INK)
    doc_rules(draw, 165, 260, [700, 844, 610, 755, 470], gap=36)
    draw.text((165, 474), "SOURCE NOTES", font=get_font(20, bold=True, mono=True), fill=MUTED)
    draw.text((165, 520), "claim  /  page  /  date  /  version", font=get_font(24, mono=True), fill=INK)
    date_progress = lyric_progress(lines, "date", t)
    if date_progress is not None:
        label_font = get_font(24, mono=True)
        date_x = 165 + int(draw.textlength("claim  /  page  /  ", font=label_font))
        date_w = int(draw.textlength("date", font=label_font))
        draw.rounded_rectangle((date_x - 4, 516, date_x + date_w + 5, 552), radius=3, outline=RED, width=3)
    for row, word in enumerate(("FIGURE  4.2", "QUOTE   11:14", "REVISION  B")):
        yy = 602 + row * 72
        checkbox(draw, 171, yy - 4, 28, active=row == 0 and t > 1.0, pulse=smooth_pulse(t, local_beats))
        draw.text((222, yy), word, font=get_font(22, mono=True), fill=INK)
        if row == 0 and lyric_progress(lines, "math", t) is not None:
            draw.rounded_rectangle((214, yy - 9, 412, yy + 34), radius=5, outline=RED, width=3)

    draw.text((165, 820), "INITIAL HERE", font=get_font(20, bold=True, mono=True), fill=MUTED)
    draw.line((315, 842, 645, 842), fill="#867B66", width=2)
    initial_progress = lyric_progress(lines, "initial", t)
    if initial_progress is not None:
        stroke = [(420, 839), (435, 816), (447, 852), (464, 824), (478, 848), (493, 820), (510, 843), (530, 831)]
        points_to_draw = max(2, int(initial_progress * len(stroke)))
        draw.line(stroke[:points_to_draw], fill=RED, width=5, joint="curve")
    if date_progress is not None:
        pencil = (165 + int(draw.textlength("claim  /  page  /  ", font=get_font(24, mono=True))), 538)
    elif lyric_progress(lines, "math", t) is not None:
        pencil = (194, 628)
    elif initial_progress is not None:
        pencil = (420 + int(80 * initial_progress), 839)
    else:
        beat = max((b for b in local_beats if b <= t), default=0.0)
        pencil = (int(780 + 150 * math.sin(beat * 0.45)), int(800 + 14 * math.sin(beat)))
    draw_pencil(draw, *pencil)

    # The proof is sliding toward the meeting room, not zooming as a still.
    slide = int(70 * ease((t - local_beats[-1]) / max(0.001, local_beats[-1] - local_beats[0]))) if local_beats else 0
    paper_surface(draw, (1320 + slide, 228, 1788 + slide, 865), seed=43, tint="#E9E1D0")
    draw.text((1372 + slide, 279), "CHECK BEFORE SEND", font=get_font(22, bold=True, mono=True), fill=INK)
    doc_rules(draw, 1372 + slide, 339, [310, 280, 334, 255, 303], gap=48, color="#CCC2AD")
    checkbox(draw, 1378 + slide, 644, 32, active=t > (local_beats[len(local_beats) // 2] if local_beats else 0.0))
    draw.text((1436 + slide, 648), "verified?", font=get_font(25, bold=True), fill=RED)
    draw.text((105, 1017), "SOURCE  →  CITATION  →  RESPONSIBILITY", font=get_font(18, mono=True), fill=MUTED)
    line = active_line(lines, t)
    if line:
        draw_word_line(draw, line, t, 166, 876, 1030, 42, local_beats)


def setup_meeting(canvas: Image.Image, t: float, local_beats: list[float], lines: list[dict]) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill="#C9C6BA")
    draw.rectangle((0, 0, WIDTH, 112), fill="#B9B8AC")
    draw.text((100, 38), "WEEKLY ALLOCATION / ROOM 3", font=get_font(24, bold=True, mono=True), fill=INK)
    draw.text((WIDTH - 355, 40), "09:00 → 09:00", font=get_font(23, mono=True), fill=RED)

    # A broad meeting table and a wall calendar establish a new room geometry.
    draw.polygon(((160, 495), (1725, 495), (1920, 895), (0, 895)), fill="#665D50")
    draw.polygon(((0, 892), (1920, 892), (1920, 1080), (0, 1080)), fill="#514C43")
    draw.rectangle((122, 172, 1796, 449), fill="#E8E2D4", outline="#555246", width=3)
    for col, label in enumerate(("TODAY", "TOMORROW", "CLIENT", "FORECAST", "REVIEW")):
        x = 160 + col * 319
        draw.line((x, 218, x, 435), fill="#C4BBA8", width=2)
        draw.text((x + 17, 190), label, font=get_font(18, bold=True, mono=True), fill=MUTED)
        checkbox(draw, x + 18, 260, 26, active=col < 2 and t > 0.25)
        doc_rules(draw, x + 18, 316, [194, 236, 169], gap=40, color="#C8BFAE")

    # The direction of the request visibly crosses the table from manager to worker.
    travel = ease((t - (local_beats[0] if local_beats else 0.0)) / max(0.001, (local_beats[-1] - local_beats[0]) if len(local_beats) > 1 else 1.0))
    card_x = int(1290 - 760 * travel)
    paper_surface(draw, (card_x, 520, card_x + 485, 779), seed=58, tint="#F4EBD7")
    draw.text((card_x + 34, 548), "NEW REQUEST", font=get_font(20, bold=True, mono=True), fill=RED)
    draw.text((card_x + 34, 610), "DECK / FORECAST / SOURCES", font=get_font(21, bold=True), fill=INK)
    checkbox(draw, card_x + 36, 691, 30, active=travel > 0.76, pulse=smooth_pulse(t, local_beats))
    draw.text((card_x + 90, 692), "OWNER: YOU", font=get_font(23, bold=True, mono=True), fill=INK)

    # File packets keep moving as the saved-time calendar fills.
    for index in range(5):
        packet_t = (t * 0.24 + index / 5) % 1.0
        x = int(-210 + packet_t * 2240)
        y = 838 - (index % 2) * 43
        draw.rectangle((x, y, x + 302, y + 84), fill=("#D7C8A9" if index % 2 else "#E8DCC5"), outline="#564F43", width=2)
        draw.line((x + 27, y + 27, x + 247, y + 27), fill="#94866D", width=3)
        draw.line((x + 27, y + 49, x + 201, y + 49), fill="#B4A78D", width=2)
    draw.text((98, 976), "SAVED MINUTES   →   ASSIGNED WORK", font=get_font(18, mono=True), fill="#F2EBDD")
    line = active_line(lines, t)
    if line:
        draw_word_line(draw, line, t, 310, 790, 1190, 45, local_beats)


def setup_workflow(canvas: Image.Image, t: float, local_beats: list[float], lines: list[dict]) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill="#D9D2C4")
    draw.polygon(((0, 0), (780, 0), (650, HEIGHT), (0, HEIGHT)), fill="#BEB7A8")
    draw.polygon(((780, 0), (1920, 0), (1920, HEIGHT), (650, HEIGHT)), fill="#E9E1D2")

    draw.text((98, 68), "DELIVERABLE ROUTE", font=get_font(26, bold=True, mono=True), fill=INK)
    # Folder depth creates a moving office corridor rather than another desk plate.
    phase = t * 0.21
    for index in range(7):
        z = (index / 7 + phase) % 1.0
        scale = 0.35 + z * 0.95
        cx = int(855 + z * 870)
        cy = int(300 + z * 430)
        w = int(292 * scale)
        h = int(187 * scale)
        x, y = cx - w // 2, cy - h // 2
        fill = ("#C9B998", "#D9CCB4", "#E4D8C0")[index % 3]
        draw.rounded_rectangle((x, y, x + w, y + h), radius=max(4, int(9 * scale)), fill=fill, outline="#594F40", width=max(1, int(3 * scale)))
        label = ("DECK", "FIGURES", "SOURCES", "FORECAST", "CLIENT COPY", "EMAIL", "SIGN-OFF")[index]
        draw.text((x + max(10, int(17 * scale)), y + max(10, int(25 * scale))), label, font=get_font(max(10, int(19 * scale)), bold=True, mono=True), fill=INK)
        line_w = int(w * 0.64)
        draw.line((x + int(17 * scale), y + int(66 * scale), x + int(17 * scale) + line_w, y + int(66 * scale)), fill="#A69A83", width=max(1, int(2 * scale)))

    # A progress track advances; its final stop remains a human name and signature line.
    draw.rounded_rectangle((142, 334, 584, 903), radius=15, fill="#F1EBDD", outline="#595449", width=3)
    draw.text((188, 374), "STATUS / ROUTE", font=get_font(21, bold=True, mono=True), fill=INK)
    tasks = ("DECK READY", "FIGURES CHECKED", "SOURCE ADDED", "REVIEW: YOU")
    for index, label in enumerate(tasks):
        yy = 450 + index * 94
        checkbox(draw, 193, yy, 29, active=index < 3 and t > index * 0.34, pulse=smooth_pulse(t, local_beats))
        draw.text((244, yy + 4), label, font=get_font(17, bold=True, mono=True), fill=(RED if index == 3 else INK))

    sign_x = 1310
    sign_y = 831
    draw.line((sign_x, sign_y, 1817, sign_y), fill=RED, width=4)
    draw.text((sign_x, sign_y + 20), "NAME ON THE FILE", font=get_font(23, bold=True, mono=True), fill=INK)
    draw.rounded_rectangle((1450, 868, 1775, 960), radius=11, fill="#E7DECE", outline="#5C564A", width=3)
    draw.text((1507, 893), "SUBMIT", font=get_font(26, bold=True, mono=True), fill=MUTED)
    draw.rounded_rectangle((630, 49, 1842, 255), radius=14, fill="#B8AE9B", outline="#594F40", width=2)
    draw.rounded_rectangle((619, 38, 1831, 244), radius=14, fill="#F1EBDD", outline="#594F40", width=2)
    draw.text((664, 61), "REQUEST / FOLLOW-UP", font=get_font(17, bold=True, mono=True), fill=RED)
    draw.line((664, 91, 1786, 91), fill=RULE, width=2)
    events = [
        ("open", (845, 344)), ("read", (1005, 420)), ("run", (1198, 382)),
        ("build", (1368, 546)), ("add", (1530, 664)), ("mark", (1220, 764)),
        ("draft", (1020, 570)), ("required", (1506, 844)), ("submission", (1415, 882)),
    ]
    timed_events = [(lyric_word(lines, name), point) for name, point in events]
    timed_events = [(word, point) for word, point in timed_events if word]
    if timed_events:
        cx, cy = timed_events[0][1]
        for index, (word, point) in enumerate(timed_events):
            start = float(word["start_seconds"])
            end = float(word["end_seconds"])
            next_start = float(timed_events[index + 1][0]["start_seconds"]) if index + 1 < len(timed_events) else end + 0.35
            if t >= start:
                fraction = ease((t - end) / max(0.12, next_start - end))
                next_point = timed_events[index + 1][1] if index + 1 < len(timed_events) else point
                cx = int(point[0] + (next_point[0] - point[0]) * fraction)
                cy = int(point[1] + (next_point[1] - point[1]) * fraction)
            else:
                break
        if lyric_progress(lines, "submission", t) is not None or lyric_progress(lines, "required", t) is not None:
            cx, cy = (1415, 882)
    else:
        cx, cy = 1100, 600
    draw.polygon(((cx, cy), (cx + 20, cy + 58), (cx + 30, cy + 42), (cx + 45, cy + 61), (cx + 57, cy + 51), (cx + 41, cy + 34), (cx + 61, cy + 28)), fill="#FAF7EF", outline=INK)
    draw.text((99, 986), "EXECUTION COMPLETE   /   SIGNATURE STILL HUMAN", font=get_font(18, mono=True), fill=INK)
    line = active_line(lines, t)
    if line:
        draw_word_line(draw, line, t, 664, 123, 1110, 42, local_beats)


def render(timeline_path: Path, output_path: Path) -> None:
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    duration = float(timeline["duration_seconds"])
    chorus_at = float(timeline["chorus2_start_seconds"])
    middle_bar = float(timeline["chorus2_middle_seconds"])
    bar_starts = [float(value) for value in timeline.get("bar_starts_seconds", [])]
    beat_times = [float(value) for value in timeline.get("beat_times_seconds", [])]
    lyric_lines = timeline.get("lines", [])
    if not duration or not bar_starts or not lyric_lines:
        raise ValueError("Timeline must include a measured duration, bar grid, and aligned lyric lines.")

    ffmpeg = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}",
        "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264", "-preset", "slow",
        "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_path),
    ]
    process = subprocess.Popen(ffmpeg, stdin=subprocess.PIPE, cwd=PROJECT)
    assert process.stdin is not None
    frame_count = math.ceil(duration * FPS)
    for frame_index in range(frame_count):
        t = frame_index / FPS
        canvas = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
        if t < chorus_at:
            scene_lines = [line for line in lyric_lines if line.get("section") == "Pre-Chorus 2"]
            setup_redline(canvas, t, beat_times, scene_lines)
        elif t < middle_bar:
            scene_lines = [line for line in lyric_lines if line.get("section") == "Chorus 2"]
            setup_meeting(canvas, t, beat_times, scene_lines)
        else:
            scene_lines = [line for line in lyric_lines if line.get("section") == "Chorus 2"]
            setup_workflow(canvas, t, beat_times, scene_lines)
        if frame_index and frame_index % 96 == 0:
            print(f"Rendered {frame_index}/{frame_count} frames", flush=True)
        process.stdin.write(canvas.tobytes())
    process.stdin.close()
    code = process.wait()
    if code:
        raise RuntimeError(f"FFmpeg picture render exited with code {code}.")
    print(f"Rendered visual source: {output_path.relative_to(PROJECT)} ({duration:.3f}s; no audio embedded)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render one music-aligned office motion-graphics POC source.")
    parser.add_argument("--timeline", type=Path, default=ASSETS / "poc_timeline.json")
    parser.add_argument("--output", type=Path, default=ASSETS / "poc_picture.mp4")
    args = parser.parse_args()
    render(args.timeline.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
