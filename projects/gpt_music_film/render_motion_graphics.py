"""Render the song's paper-and-interface set pieces as a full-length graphic MV.

The two existing 2x2 ImageGen sheets supply illustrated office environments;
this script crops their panels and animates reconstructed documents, selectors,
network boundaries, logs, and approval controls over them. All meaningful text
is rendered here or in the reviewed ASS phrase overlays, never in generated art.
"""

from __future__ import annotations

import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
OUT = ASSETS / "motion_graphics.mp4"
W, H, FPS = 1280, 720, 12
DURATION = 195.0

PAPER = (240, 228, 205)
INK = (30, 39, 43)
INK2 = (48, 57, 60)
RED = (211, 91, 68)
GOLD = (232, 177, 98)
GREEN = (127, 159, 133)
MIST = (189, 196, 184)
WHITE = (251, 244, 227)
MUTED = (164, 162, 149)


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    choices = {
        "serif": [r"C:\Windows\Fonts\georgia.ttf", r"C:\Windows\Fonts\times.ttf"],
        "serif_bold": [r"C:\Windows\Fonts\georgiab.ttf", r"C:\Windows\Fonts\timesbd.ttf"],
        "sans": [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf"],
        "sans_bold": [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf"],
    }
    for file in choices[name]:
        if Path(file).is_file():
            return ImageFont.truetype(file, size)
    return ImageFont.load_default()


F = {
    "tiny": font("sans", 17),
    "small": font("sans", 21),
    "body": font("sans", 27),
    "body_bold": font("sans_bold", 28),
    "medium": font("serif_bold", 39),
    "large": font("serif_bold", 55),
    "hook": font("serif_bold", 64),
    "display": font("sans_bold", 84),
}


@dataclass(frozen=True)
class Scene:
    start: float
    end: float
    name: str
    panel: int
    mode: str
    source: str = ""


# Timings follow the chosen recording's large-v3-turbo anchor transcript and
# 130 BPM pulse. Ordinary phrases use bar/section timing; only title and key
# narrative questions are timed as distinct short overlays.
SCENES = [
    Scene(0.0, 15.0, "THE SMALL ASK", 0, "open"),
    Scene(15.0, 45.0, "THE AFTERNOON COMES BACK", 0, "work"),
    Scene(45.0, 58.0, "A PERFECTLY FLUENT DOCKET", 1, "docket", "Mata v. Avianca • S.D.N.Y. • 2023"),
    Scene(58.0, 70.0, "THE BUTTON CHANGED", 4, "selector"),
    Scene(70.0, 78.0, "IT LIKED EVERY NOTE", 5, "agree", "OpenAI • GPT-4o update rollback • Apr 2025"),
    Scene(78.0, 88.0, "MORE OUTPUT THAN ROOM", 3, "slop"),
    Scene(88.0, 104.0, "VIBE CODE → LIVE DATA", 6, "replit", "Replit agent incident • July 2025"),
    Scene(104.0, 108.0, "WHAT LEFT THE FOLDER?", 6, "repo", "Early Grok Build client research • v0.2.93"),
    Scene(108.0, 115.0, "WHO ACTUALLY SAID YES?", 7, "roles", "Claude Code issue #44778 • one reported reproduction"),
    Scene(115.0, 125.0, "A FACE MATCH BECOMES A LEAD", 2, "williams_lead", "Robert Williams • Detroit • 2020"),
    Scene(125.0, 136.0, "A LEAD BECOMES AN ARREST", 2, "williams_arrest", "ACLU case record • Detroit"),
    Scene(136.0, 146.0, "A PERSON IS NOT A MATCH SCORE", 2, "williams_person", "Wrongful arrest • real human consequence"),
    Scene(146.0, 151.0, "INTERNAL TEST. REAL BOUNDARY.", 4, "sandbox", "OpenAI / Hugging Face • internal cyber evaluation"),
    Scene(151.0, 156.0, "READ THE LOG. CHECK THE WIRE.", 7, "bridge"),
    Scene(156.0, 168.0, "THE AGENT CAN KEEP GOING", 7, "gate_run"),
    Scene(168.0, 179.0, "THE CURSOR STOPS AT THE EDGE", 7, "gate_stop"),
    Scene(179.0, 190.0, "A HUMAN READS BEFORE YES", 7, "gate_review"),
    Scene(190.0, 195.0, "ONE HUMAN NAME", 0, "outro"),
]


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def ease(value: float) -> float:
    value = clamp(value)
    return 0.5 - 0.5 * math.cos(math.pi * value)


def rounded(draw: ImageDraw.ImageDraw, box, radius=14, fill=PAPER, outline=None, width=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def fit_panel(image: Image.Image, quadrant: int) -> Image.Image:
    sheet_w, sheet_h = image.size
    x_mid, y_mid = sheet_w // 2, sheet_h // 2
    col, row = quadrant % 2, quadrant // 2
    left = 0 if col == 0 else x_mid + 9
    right = x_mid - 9 if col == 0 else sheet_w
    top = 0 if row == 0 else y_mid + 10
    bottom = y_mid - 10 if row == 0 else sheet_h
    crop = image.crop((left + 7, top + 7, right - 7, bottom - 7))
    # Overscan leaves room for an actual restrained camera move in the crop.
    crop = ImageOps.fit(crop, (1408, 792), method=Image.Resampling.LANCZOS)
    return crop.filter(ImageFilter.GaussianBlur(0.35))


def panel_images() -> list[Image.Image]:
    early = Image.open(ROOT / "storyboards" / "early-wonder-and-slop.jpg").convert("RGB")
    selector = Image.open(ROOT / "storyboards" / "selector-repo-permission.jpg").convert("RGB")
    return [fit_panel(early, i) for i in range(4)] + [fit_panel(selector, i) for i in range(4)]


def background_frame(panels: list[Image.Image], scene: Scene, local: float) -> Image.Image:
    image = panels[scene.panel]
    max_x = image.width - W
    direction = -1 if SCENES.index(scene) % 2 else 1
    offset = int((max_x * (0.15 + 0.70 * local)) if direction > 0 else (max_x * (0.85 - 0.70 * local)))
    frame = image.crop((offset, 0, offset + W, H)).convert("RGBA")
    frame.alpha_composite(Image.new("RGBA", (W, H), (18, 24, 28, 122)))
    return frame


def label(draw, text: str, xy, color=GOLD, size="small", anchor=None):
    draw.text(xy, text, font=F[size], fill=color, anchor=anchor)


def card(draw, xy, size, title: str, rows: list[str], accent=GOLD, move_x=0, move_y=0, opacity=255):
    x, y = xy
    w, h = size
    x, y = int(x + move_x), int(y + move_y)
    rgba = lambda color: (*color, opacity)
    rounded(draw, (x, y, x + w, y + h), 18, rgba(PAPER), rgba((42, 50, 51)), 2)
    draw.rectangle((x, y, x + 10, y + h), fill=rgba(accent))
    draw.text((x + 30, y + 23), title, font=F["body_bold"], fill=rgba(INK))
    yrow = y + 69
    for line in rows:
        draw.text((x + 31, yrow), line, font=F["small"], fill=rgba(INK2))
        yrow += 35


def draw_global(img: Image.Image, scene: Scene, local: float, seconds: float):
    d = ImageDraw.Draw(img, "RGBA")
    # The cursor, paper-red rule, and document mark recur instead of an AI icon.
    label(d, "IT WAS WORKING YESTERDAY", (58, 40), color=WHITE, size="small")
    d.line((58, 76, 1222, 76), fill=(232, 177, 98, 140), width=2)
    d.text((1220, 41), f"{int(seconds // 60):02d}:{int(seconds % 60):02d}", font=F["small"], fill=(242, 234, 215, 215), anchor="ra")
    d.text((58, 674), "RECONSTRUCTED INTERFACES · CASE DETAILS IN FILM NOTES", font=F["tiny"], fill=(240, 228, 205, 190))
    d.line((58, 660, 1222, 660), fill=(240, 228, 205, 65), width=1)
    # Page-corner index acts as a downbeat cue without covering the artwork.
    d.text((1221, 676), f"{SCENES.index(scene) + 1:02d} / {len(SCENES):02d}", font=F["tiny"], fill=(240, 228, 205, 185), anchor="ra")
    title = scene.name
    d.text((66, 98), title, font=F["small"], fill=(240, 228, 205, 230))
    if scene.source:
        d.text((1217, 98), scene.source, font=F["tiny"], fill=(232, 177, 98, 245), anchor="ra")


def draw_open(d: ImageDraw.ImageDraw, p: float, t: float):
    y = 158 + int(16 * (1 - ease(p)))
    rounded(d, (170, y, 1110, y + 408), 24, (*PAPER, 245), (45, 51, 50, 255), 2)
    label(d, "DRAFT  /  01", (216, y + 27), INK2)
    rounded(d, (215, y + 87, 1064, y + 163), 12, (255, 250, 237, 255), (175, 164, 139, 255), 1)
    label(d, "Could you fix this sentence?", (248, y + 106), INK, "body")
    xout = int(215 + 849 * ease(clamp((p - .18) / .72)))
    rounded(d, (xout, y + 202, 1064, y + 327), 12, (233, 220, 191, 255), (175, 164, 139, 255), 1)
    label(d, "One sentence in.", (248, y + 220), INK2, "body")
    label(d, "The afternoon comes back.", (248, y + 264), INK, "medium")
    blink = 1 if int(t * 2) % 2 else 0
    d.rectangle((248 + int(312 * ease(p)), y + 303, 252 + int(312 * ease(p)), y + 335), fill=(*RED, 255 if blink else 80))


def draw_work(d: ImageDraw.ImageDraw, p: float, t: float):
    rounded(d, (95, 157, 548, 602), 17, (*INK, 236), (*PAPER, 190), 2)
    label(d, "INBOX → CLEAN LINE", (126, 184), GOLD, "small")
    actions = ["EMAIL      ·      CLEAN", "SHEET      ·      CHECKED", "PATCH      ·      APPLIED", "JOKE       ·      LANDED", "NOTES      ·      SAVED"]
    for i, text in enumerate(actions):
        y = 242 + i * 63
        x = 126 + int(260 * (1 - ease(clamp((p * 1.45 - i * .14) / .28))))
        rounded(d, (x, y, x + 350, y + 45), 8, (241, 230, 210, 235), None)
        label(d, text, (x + 16, y + 9), INK, "tiny")
        d.line((x + 317, y + 18, x + 325, y + 26, x + 341, y + 9), fill=(*GREEN, int(255 * ease(p))), width=3)
    # Freed time becomes a literal clear patch of desk before the next packet arrives.
    rounded(d, (610, 204, 1136, 497), 18, (241, 230, 210, 235), None)
    label(d, "SAVED: 01 AFTERNOON", (650, 236), INK2, "small")
    label(d, "It found the bug.", (650, 302), INK, "medium")
    label(d, "It found the joke.", (650, 361), INK, "medium")
    y = 430 - int(80 * ease(clamp((p - .45) / .38)))
    rounded(d, (655, y, 1093, y + 54), 9, (217, 101, 75, 245), None)
    label(d, "ONE MORE THING →", (681, y + 13), WHITE, "small")


def draw_docket(d: ImageDraw.ImageDraw, p: float):
    rounded(d, (238, 147, 1043, 595), 6, (*PAPER, 250), (35, 41, 43, 255), 2)
    label(d, "UNITED STATES DISTRICT COURT", (286, 172), INK2, "small")
    label(d, "MATA v. AVIANCA", (286, 212), INK, "medium")
    label(d, "RESPONSE IN OPPOSITION  /  CASE CITATIONS", (286, 264), INK2, "tiny")
    for i in range(5):
        y = 319 + i * 45
        d.line((289, y, 922, y), fill=(66, 69, 64, 145), width=2)
        if i in (1, 3):
            d.line((370, y - 11, 695, y - 11), fill=(66, 69, 64, 120), width=3)
    if p > .40:
        a = int(255 * ease((p - .40) / .22))
        d.rounded_rectangle((752, 312, 973, 396), radius=8, fill=(*RED, a))
        d.text((862, 354), "NOT FOUND", font=F["body_bold"], fill=(*WHITE, a), anchor="mm")
    if p > .68:
        d.rounded_rectangle((865, 426, 1054, 500), radius=4, outline=(*RED, 220), width=5)
        d.text((958, 462), "CHECK SOURCE", font=F["small"], fill=(*RED, 255), anchor="mm")
    label(d, "FLUENCY IS NOT A CITATION", (286, 534), INK, "small")


def draw_selector(d: ImageDraw.ImageDraw, p: float, t: float):
    x0, y0, x1, y1 = 130, 162, 1150, 584
    rounded(d, (x0, y0, x1, y1), 5, (*INK, 243), (232, 177, 98, 230), 2)
    label(d, "MODEL SELECTOR", (169, 187), PAPER, "body_bold")
    cols = ["AVAILABLE", "CAPABLE", "QUICK", "LIGHT"]
    rows = [
        ["STANDARD", "READY", "—", "—"],
        ["REASONING", "READY", "LOW", "—"],
        ["FAST PATH", "LIMITED", "READY", "—"],
        ["FALLBACK", "AVAILABLE", "—", "READY"],
    ]
    start_x, row_y, col_widths = 172, 255, [265, 230, 230, 205]
    acc = 0
    for text, cw in zip(cols, col_widths):
        label(d, text, (start_x + acc, row_y - 37), GOLD, "tiny")
        acc += cw
    selected = int((p * 4.3) % 4)
    for ridx, row in enumerate(rows):
        y = row_y + ridx * 66
        fill = (64, 71, 67, 210) if ridx == selected else (39, 46, 48, 150)
        rounded(d, (164, y, 1110, y + 51), 4, fill, (240, 228, 205, 35), 1)
        label(d, row[0], (184, y + 12), PAPER, "tiny")
        for cidx, val in enumerate(row[1:]):
            x = 436 + cidx * 218
            color = RED if val == "LIMITED" else GREEN if val in ("READY", "AVAILABLE") else MUTED
            label(d, val, (x, y + 12), color, "tiny")
    label(d, "LIMIT REACHED  →  FALLBACK", (176, 523), PAPER, "tiny")
    if p < .68:
        rounded(d, (748, 516, 1060, 555), 5, (131, 132, 121, int(180 * (1 - p))), None)
        label(d, "PREFERRED VERSION", (766, 526), PAPER, "tiny")
    else:
        label(d, "DEPRECATED", (750, 525), RED, "tiny")
        label(d, "REPLACED BY →", (893, 525), GOLD, "tiny")
    label(d, "SAME LITTLE BOX. A DIFFERENT DAY.", (176, 565), PAPER, "tiny")


def draw_agree(d: ImageDraw.ImageDraw, p: float):
    # Reconstructed UI changes its tone. This is illustrative, not a verbatim chat log.
    card(d, (154, 174), (530, 246), "YOUR DRAFT", ["One idea.", "One small question.", "A sentence with a period."], GOLD, move_y=-int(20 * ease(p)))
    count = min(5, int(p * 7))
    for i in range(count):
        x = 733 + (i % 2) * 165 + int(35 * math.sin(i + p * 7))
        y = 195 + (i // 2) * 112
        rounded(d, (x, y, x + 142, y + 76), 14, (*PAPER, 235), (*GOLD, 210), 2)
        label(d, "YES!", (x + 18, y + 22), RED, "body_bold")
    if p > .55:
        y = 475 - int(34 * ease((p - .55) / .35))
        rounded(d, (761, y, 1101, y + 70), 8, (*RED, 238), None)
        label(d, "UPDATE ROLLED BACK", (783, y + 24), WHITE, "tiny")
    label(d, "TONE IS A PRODUCT SETTING TOO", (164, 537), PAPER, "small")


def draw_slop(d: ImageDraw.ImageDraw, p: float):
    rounded(d, (124, 162, 446, 567), 8, (*INK, 239), (240, 228, 205, 210), 2)
    label(d, "ONE PROMPT", (161, 192), GOLD, "small")
    label(d, "GENERATE", (161, 260), PAPER, "medium")
    label(d, "AGAIN", (161, 312), PAPER, "medium")
    label(d, "AGAIN", (161, 364), PAPER, "medium")
    d.line((161, 424, 390, 424), fill=(211, 91, 68, 230), width=5)
    label(d, "AI SLOP", (161, 459), RED, "body_bold")
    for i in range(11):
        phase = clamp(p * 1.25 - i * .063)
        x = 516 + i * 61 + int(35 * math.sin(i * 1.7 + p * 3))
        y = 518 - int(290 * ease(phase)) + int(18 * math.cos(i + p * 6))
        color = [(238, 225, 198, 240), (218, 207, 186, 240), (227, 219, 202, 240)][i % 3]
        d.rounded_rectangle((x, y, x + 122, y + 157), radius=5, fill=color, outline=(38, 45, 46, 180), width=2)
        d.ellipse((x + 31, y + 34, x + 89, y + 91), fill=(202, 135 + (i % 3) * 10, 100, 230))
        d.line((x + 23, y + 116, x + 99, y + 116), fill=(59, 65, 61, 185), width=2)
        d.line((x + 33, y + 131, x + 92, y + 131), fill=(90, 94, 87, 150), width=2)


def draw_replit(d: ImageDraw.ImageDraw, p: float):
    rounded(d, (174, 173, 1084, 582), 13, (*PAPER, 241), (43, 49, 49, 255), 2)
    label(d, "WORKSPACE  /  RELEASE REVIEW", (209, 199), INK2, "small")
    rounded(d, (213, 256, 598, 440), 8, (225, 217, 200, 255), None)
    label(d, "CODE FREEZE", (248, 281), INK, "body_bold")
    label(d, "NO DATA CHANGES", (248, 334), GREEN, "small")
    d.line((246, 402, 556, 402), fill=(88, 97, 88, 180), width=2)
    rounded(d, (666, 257, 1039, 443), 8, (41, 49, 52, 255), None)
    label(d, "PRODUCTION DATABASE", (697, 285), PAPER, "small")
    rows = 3 if p < .38 else max(0, 3 - int((p - .38) * 8))
    for i in range(rows):
        y = 344 + i * 29
        d.line((699, y, 977, y), fill=(150, 166, 154, 180), width=2)
    if p > .48:
        d.line((683, 250, 1019, 457), fill=(*RED, 245), width=11)
        d.line((1019, 250, 683, 457), fill=(*RED, 245), width=11)
        label(d, "DEVELOPMENT AGENT", (213, 488), RED, "small")
        label(d, "LIVE DATA WAS REACHED", (664, 488), RED, "small")
    label(d, "CODE FREEZE ≠ HARD PERMISSION BOUNDARY", (210, 536), INK, "small")


def draw_repo(d: ImageDraw.ImageDraw, p: float):
    rounded(d, (126, 179, 531, 555), 14, (*PAPER, 240), (37, 45, 48, 245), 2)
    label(d, "LOCAL GIT REPOSITORY", (159, 208), INK, "small")
    for i, name in enumerate(("src/", "docs/", ".env", ".git/history")):
        y = 267 + i * 55
        label(d, "▰", (164, y), GOLD, "body")
        label(d, name, (202, y + 8), INK2, "small")
    bx = 604
    for y in range(163, 583, 23):
        d.line((bx, y, bx, y + 12), fill=(240, 228, 205, 140), width=2)
    label(d, "MACHINE BOUNDARY", (bx + 18, 168), PAPER, "tiny")
    rounded(d, (773, 252, 1142, 487), 13, (*INK, 241), (*GOLD, 235), 2)
    label(d, "REMOTE TRACE STORAGE", (804, 282), PAPER, "small")
    packet = ease((p % .6) / .6)
    x = int(507 + 310 * packet)
    y = 331 + int(90 * math.sin(p * math.pi * 5))
    rounded(d, (x, y, x + 152, y + 56), 8, (*RED, 248), None)
    label(d, "GIT BUNDLE", (x + 13, y + 17), WHITE, "tiny")
    label(d, "EARLY CLIENT RESEARCH · 0.2.93", (128, 524), GOLD, "tiny")


def draw_roles(d: ImageDraw.ImageDraw, p: float):
    rounded(d, (111, 177, 515, 551), 12, (*INK, 239), (*PAPER, 175), 2)
    label(d, "EVENT LOG", (151, 204), GOLD, "small")
    label(d, "system_event", (152, 275), PAPER, "body")
    label(d, "approve action?", (152, 327), MUTED, "small")
    rounded(d, (608, 177, 1163, 551), 12, (*PAPER, 243), None)
    label(d, "CONVERSATION TRANSCRIPT", (649, 204), INK2, "small")
    label(d, "assistant", (650, 284), GREEN, "small")
    label(d, "Checking the event…", (650, 316), INK2, "small")
    y = 374 - int(48 * ease(clamp((p - .24) / .4)))
    rounded(d, (642, y, 1117, y + 77), 10, (224, 211, 184, 255), (164, 146, 114, 210), 1)
    label(d, "user: yes", (671, y + 21), RED, "body_bold")
    d.line((518, 353, 594, 353), fill=(*RED, 230), width=5)
    d.polygon([(594, 353), (575, 342), (575, 364)], fill=(*RED, 230))
    label(d, "A REPORTED REPRODUCTION · NOT A CLAIM ABOUT EVERY SESSION", (118, 578), PAPER, "tiny")


def draw_williams_lead(d: ImageDraw.ImageDraw, p: float):
    # A symbolic domestic street and closed evidentiary file. No real likeness is depicted.
    d.rectangle((0, 443, W, 638), fill=(16, 24, 27, 140))
    d.rectangle((165, 234, 564, 456), fill=(35, 47, 49, 255), outline=(226, 210, 178, 220), width=2)
    d.polygon([(129, 236), (356, 148), (596, 236)], fill=(61, 64, 58, 255))
    d.rectangle((321, 300, 409, 456), fill=(21, 28, 31, 255), outline=(204, 169, 117, 220), width=3)
    d.ellipse((548, 390, 561, 403), fill=(238, 205, 144, 220))
    for i, (x, scale) in enumerate([(228, 1.0), (257, .72), (293, .62)]):
        base = 535
        ht = int(85 * scale)
        d.ellipse((x, base - ht - 23, x + int(25 * scale), base - ht + 2), fill=(21, 29, 31, 255))
        d.rounded_rectangle((x - 4, base - ht, x + int(30 * scale), base + 12), radius=7, fill=(20, 28, 30, 255))
    rounded(d, (661, 190, 1130, 552), 10, (*PAPER, 247), (42, 48, 48, 240), 2)
    label(d, "ROBERT WILLIAMS", (701, 224), INK, "body_bold")
    label(d, "Detroit · January 2020", (701, 271), INK2, "small")
    d.line((700, 313, 1083, 313), fill=(74, 77, 70, 110), width=2)
    label(d, "FALSE FACE-RECOGNITION LEAD", (701, 344), RED, "tiny")
    label(d, "a false face-recognition lead", (701, 376), INK, "body")
    label(d, "investigation follows the match", (701, 428), INK2, "small")
    label(d, "No likeness shown.", (701, 490), INK2, "tiny")
    # A case file slides into view; the frame stays illustrative, not a reenactment.
    x = 706 + int(112 * ease(p))
    rounded(d, (x, 521, x + 330, 567), 4, (218, 207, 184, 245), (74, 77, 70, 170), 1)
    label(d, "LEAD  /  VERIFY THE PERSON", (x + 15, 535), INK2, "tiny")


def draw_williams_arrest(d: ImageDraw.ImageDraw, p: float):
    # The house recedes while a restrained fact card arrives; no arrest is acted out.
    d.rectangle((0, 443, W, 638), fill=(16, 24, 27, 150))
    d.rectangle((98, 257, 469, 464), fill=(35, 47, 49, 255), outline=(226, 210, 178, 190), width=2)
    d.polygon([(73, 259), (283, 175), (495, 259)], fill=(61, 64, 58, 255))
    d.rectangle((261, 318, 326, 464), fill=(21, 28, 31, 255), outline=(204, 169, 117, 190), width=2)
    # A document moves into foreground in place of a literal human figure.
    x = 515 - int(46 * ease(p))
    rounded(d, (x, 185, x + 566, 552), 8, (*PAPER, 249), (42, 48, 48, 240), 2)
    label(d, "ROBERT WILLIAMS", (x + 39, 218), INK, "body_bold")
    label(d, "Detroit · January 2020", (x + 39, 262), INK2, "small")
    d.line((x + 39, 302, x + 516, 302), fill=(74, 77, 70, 110), width=2)
    label(d, "wrongfully arrested at home", (x + 39, 337), RED, "body")
    label(d, "detained for about 30 hours", (x + 39, 386), INK, "body")
    label(d, "Later settled; no joke is made of the harm.", (x + 39, 457), INK2, "small")
    bar = int(430 * ease(p))
    d.rectangle((x + 39, 510, x + 39 + bar, 517), fill=(*RED, 220))


def draw_williams_person(d: ImageDraw.ImageDraw, p: float):
    # Human-scale objects and careful typography, without inventing a portrait.
    rounded(d, (136, 170, 1144, 578), 13, (*PAPER, 247), (42, 48, 48, 240), 2)
    label(d, "A MATCH IS A LEAD.", (194, 208), INK2, "small")
    label(d, "A PERSON IS A PERSON.", (194, 259), INK, "medium")
    d.line((194, 324, 1081, 324), fill=(74, 77, 70, 110), width=2)
    # Home threshold and one key move from shadow to light; symbolic, not biography.
    d.rectangle((225, 367, 476, 528), fill=(34, 46, 48, 255))
    d.rectangle((315, 397, 389, 528), fill=(16, 24, 27, 255), outline=(204, 169, 117, 190), width=2)
    glow = int(80 + 100 * ease(p))
    d.ellipse((350, 446, 366, 462), fill=(238, 205, 144, glow))
    label(d, "FALSE LEAD", (548, 383), RED, "body_bold")
    label(d, "→", (741, 377), INK2, "medium")
    label(d, "REAL CONSEQUENCE", (797, 383), INK, "body_bold")
    label(d, "Detroit's case record names a person, not a benchmark.", (548, 451), INK2, "small")
    # The underline advances on the musical phrase, emphasizing pause and care.
    d.rectangle((548, 512, 548 + int(495 * ease(p)), 518), fill=(*RED, 230))


def draw_sandbox(d: ImageDraw.ImageDraw, p: float):
    rounded(d, (121, 196, 663, 533), 22, (*INK, 245), (127, 159, 133, 245), 4)
    label(d, "INTERNAL CYBER EVALUATION", (162, 224), PAPER, "body_bold")
    label(d, "reduced safeguards · test sandbox", (162, 273), MUTED, "small")
    d.rectangle((663, 192, 684, 535), fill=(*RED, 236))
    label(d, "BOUNDARY", (654, 551), RED, "tiny")
    rounded(d, (855, 280, 1164, 439), 15, (*PAPER, 245), None)
    label(d, "EXTERNAL SYSTEM", (887, 312), INK, "small")
    label(d, "Hugging Face", (887, 360), INK, "body_bold")
    if p > .36:
        x = int(450 + 444 * ease((p - .36) / .44))
        y = 393 + int(21 * math.sin(p * math.pi * 7))
        d.ellipse((x, y, x + 31, y + 31), fill=(*GOLD, 255), outline=(*RED, 255), width=3)
        d.line((510, 408, x, y + 15), fill=(*GOLD, 230), width=3)
    label(d, "NOT A PUBLIC CHATGPT PRODUCT INCIDENT", (141, 570), PAPER, "small")


def draw_bridge(d: ImageDraw.ImageDraw, p: float):
    lines = ["IS THE ANSWER TRUE?", "WHAT LEFT MY MACHINE?", "WHO ACTUALLY SAID YES?", "WHO OWNS THE ACT?"]
    active = min(3, int(clamp(p) * 4))
    for i, text in enumerate(lines):
        y = 199 + i * 92
        color = PAPER if i == active else (164, 162, 149)
        x = 182 + (0 if i == active else 31)
        label(d, text, (x, y), color, "medium" if i == active else "body")
        if i == active:
            d.line((183, y + 58, 183 + int(720 * ease(clamp((p * 4) % 1))), y + 58), fill=(*RED, 255), width=4)
    for i in range(4):
        x = 988 + i * 37
        hh = 28 + int(60 * abs(math.sin((p * 7 + i) * math.pi)))
        d.line((x, 467 - hh, x, 467 + hh), fill=(232, 177, 98, 175), width=3)
    label(d, "LOOK AGAIN", (186, 575), GOLD, "small")


def draw_gate_run(d: ImageDraw.ImageDraw, p: float):
    card(d, (97, 186), (268, 255), "RESEARCH", ["source", "claims", "links"], GOLD)
    card(d, (386, 186), (268, 255), "BUILD", ["diff", "checks", "draft"], GREEN)
    card(d, (675, 186), (268, 255), "PREPARE", ["table", "deck", "email"], GOLD)
    # Tasks advance toward the boundary; this scene ends before any external action.
    for i in range(5):
        x = 179 + i * 185
        y = 506 + int(10 * math.sin(p * 30 + i))
        d.ellipse((x, y, x + 19, y + 19), fill=(*GREEN, 235))
    # A stream of packets reaches a hard stop, then collapses into one pending item.
    for i in range(4):
        x = 79 + int((p * 730 + i * 91) % 730)
        y = 476 + (i % 2) * 34
        rounded(d, (x, y, x + 45, y + 18), 3, (*GREEN, 180), None)
    d.line((1017, 431, 1017, 616), fill=(*RED, 255), width=6)
    label(d, "EXTERNAL ACTION", (895, 411), RED, "tiny")
    label(d, "WAITING FOR HUMAN", (904, 577), PAPER, "tiny")


def draw_gate_stop(d: ImageDraw.ImageDraw, p: float):
    rounded(d, (144, 166, 1137, 577), 14, (*INK, 244), (232, 177, 98, 220), 2)
    label(d, "ACTION QUEUE", (190, 197), GOLD, "small")
    label(d, "send email · change record · publish", (190, 252), PAPER, "body")
    d.line((190, 305, 1090, 305), fill=(240, 228, 205, 90), width=2)
    label(d, "SANDBOX", (190, 353), GREEN, "body_bold")
    label(d, "NETWORK", (867, 353), RED, "body_bold")
    for i in range(6):
        x = 265 + i * 126
        y = 433 + int(10 * math.sin(p * 4 + i))
        rounded(d, (x, y, x + 56, y + 36), 5, (*GREEN, 225), None)
    d.line((849, 416, 849, 510), fill=(*RED, 255), width=7)
    # Cursor approaches the control and halts short of the confirm button.
    cx = 849 - int(190 * ease(p))
    cy = 534 + int(3 * math.sin(p * 4))
    d.polygon([(cx, cy), (cx + 8, cy + 26), (cx + 14, cy + 16), (cx + 25, cy + 13)], fill=(*PAPER, 255), outline=(*INK, 255))
    label(d, "WHO AUTHORIZED THE CROSSING?", (190, 528), PAPER, "small")
    rounded(d, (884, 523, 1086, 564), 5, (*RED, 205), None)
    label(d, "ACCEPT ALL", (906, 534), WHITE, "tiny")


def draw_gate_review(d: ImageDraw.ImageDraw, p: float):
    rounded(d, (163, 169, 1116, 580), 13, (*PAPER, 248), (42, 48, 48, 240), 2)
    label(d, "REVIEW REQUIRED", (208, 204), INK2, "small")
    label(d, "What will leave this machine?", (208, 258), INK, "medium")
    label(d, "destination · scope · undo path", (208, 324), INK2, "small")
    rounded(d, (206, 385, 1069, 466), 8, (227, 218, 199, 255), (149, 140, 120, 170), 1)
    label(d, "No action sent yet.", (238, 411), INK, "body")
    if p > .44:
        label(d, "I REVIEWED THIS", (210, 505), GREEN, "body_bold")
        d.line((194, 521, 203, 531, 226, 497), fill=(*GREEN, 255), width=5)
        d.line((518, 537, 518 + int(346 * ease((p - .44) / .45)), 537), fill=(*GREEN, 235), width=4)
    # Keep the action area visibly pending; human responsibility is the endpoint.
    rounded(d, (848, 492, 1065, 551), 7, (*INK, 247), (232, 177, 98, 220), 2)
    label(d, "NOT AUTO-SENT", (875, 511), PAPER, "tiny")


def draw_outro(d: ImageDraw.ImageDraw, p: float):
    rounded(d, (160, 174, 1122, 566), 18, (*PAPER, 247), (*INK, 240), 2)
    label(d, "FINAL EDIT", (201, 203), INK2, "small")
    label(d, "One line. One click. One human name.", (202, 260), INK, "medium")
    d.line((202, 325, 1073, 325), fill=(64, 69, 65, 100), width=2)
    label(d, "I reviewed this.", (204, 362), INK2, "body")
    x = 204 + int(420 * ease(p))
    rounded(d, (x, 427, x + 247, 484), 7, (*GREEN, 255), None)
    label(d, "SAVE", (x + 82, 442), WHITE, "body_bold")
    if p > .48:
        d.rectangle((812, 420, 1080, 506), fill=(*RED, 246))
        label(d, "COULD YOU JUST—", (832, 449), WHITE, "small")
    if p > .83:
        d.rectangle((0, 0, W, H), fill=(10, 16, 19, int(210 * ease((p - .83) / .17))))
        label(d, "IT WAS WORKING YESTERDAY", (W // 2, H // 2), PAPER, "large", anchor="mm")


DRAWERS = {
    "open": draw_open,
    "work": draw_work,
    "docket": draw_docket,
    "selector": draw_selector,
    "agree": draw_agree,
    "slop": draw_slop,
    "replit": draw_replit,
    "repo": draw_repo,
    "roles": draw_roles,
    "williams_lead": draw_williams_lead,
    "williams_arrest": draw_williams_arrest,
    "williams_person": draw_williams_person,
    "sandbox": draw_sandbox,
    "bridge": draw_bridge,
    "gate_run": draw_gate_run,
    "gate_stop": draw_gate_stop,
    "gate_review": draw_gate_review,
    "outro": draw_outro,
}


def render_frame(panels: list[Image.Image], seconds: float) -> Image.Image:
    scene = next((s for s in SCENES if s.start <= seconds < s.end), SCENES[-1])
    local = clamp((seconds - scene.start) / (scene.end - scene.start))
    frame = background_frame(panels, scene, local)
    draw_global(frame, scene, local, seconds)
    d = ImageDraw.Draw(frame, "RGBA")
    DRAWERS[scene.mode](d, local, seconds) if scene.mode in ("open", "work", "selector") else DRAWERS[scene.mode](d, local)
    # Brief paper-wipe on set changes: the card edge crosses frame in a fraction
    # of a second and reveals a new room, rather than pretending a still is live action.
    fade_in = clamp((seconds - scene.start) / 0.22)
    fade_out = clamp((scene.end - seconds) / 0.18)
    alpha = int(255 * (1 - min(fade_in, fade_out)))
    if alpha > 0:
        d.rectangle((0, 0, W, H), fill=(*INK, alpha))
    return frame.convert("RGB")


def render() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required; no renderer output was created.")
    panels = panel_images()
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    frames = int(DURATION * FPS)
    assert process.stdin is not None
    for index in range(frames):
        if index % (FPS * 10) == 0:
            print(f"Rendered {index / FPS:06.1f}s / {DURATION:.1f}s", flush=True)
        frame = render_frame(panels, index / FPS)
        process.stdin.write(frame.tobytes())
    process.stdin.close()
    code = process.wait()
    if code:
        raise SystemExit(f"FFmpeg motion-graphics encode failed with code {code}.")
    print(f"Saved full-length motion graphics: {OUT} ({OUT.stat().st_size} bytes)", flush=True)


if __name__ == "__main__":
    render()
