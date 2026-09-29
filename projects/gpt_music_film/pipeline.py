from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
PROJECT = yaml.safe_load((ROOT / "project.yaml").read_text(encoding="utf-8"))
PROJECT_KIND = PROJECT["project"]
TARGET_SECONDS = float(PROJECT["target_duration_seconds"])
EXPECTED_STEMS = {
    "zhongqiu": ["dialogue.wav", "voiceover.wav", "sync_foley.wav", "ambience.wav", "event_sound.wav", "music.wav"],
    "gpt_music_film": ["lead_vocal.wav", "backing_vocals.wav", "sync_foley.wav", "ambience.wav", "event_sound.wav", "music.wav"],
}[PROJECT_KIND]
CAPTION_FILTER = {
    "zhongqiu": "subtitles=assets/captions.srt",
    "gpt_music_film": "ass=assets/lyrics.ass",
}[PROJECT_KIND]
OUTPUT = ROOT / "final.mp4"
MANIFEST = ASSETS / "edit_decision.json"
MIX = ASSETS / "mix.json"
POC_OUTPUT = ASSETS / "poc_clip.mp4"
POC_MANIFEST = ASSETS / "poc_edit_decision.json"
POC_MIX = ASSETS / "poc_mix.json"
CONTACT_SHEET = ROOT / "review.jpg"
FINAL_QA = ASSETS / "final_qa.json"


def fail(message: str) -> None:
    raise SystemExit(message)


def read_json(path: Path) -> dict:
    if not path.is_file():
        fail(f"Missing required production manifest: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        fail("ffmpeg is required for assembly.")
    return path


def ffprobe_bin() -> str:
    path = shutil.which("ffprobe")
    if not path:
        fail("ffprobe is required for technical QA.")
    return path


def poc_target_seconds() -> float:
    if "poc" in PROJECT:
        return float(PROJECT["poc"]["duration_seconds"])
    return float(PROJECT["motion"]["poc_duration_seconds"])


def validate_inputs(poc: bool = False) -> tuple[list[dict], list[dict], str | None, float]:
    edit = read_json(POC_MANIFEST if poc else MANIFEST)
    mix = read_json(POC_MIX if poc else MIX)
    segments = edit.get("segments", [])
    stems = mix.get("stems", [])
    if not segments:
        fail("The edit manifest must contain selected, ordered video segments.")
    if not stems:
        fail("The mix manifest must contain aligned audio stems and gain_db values.")

    shot_ids = {shot["id"] for shot in PROJECT.get("shots", [])}
    covered = set()
    for segment in segments:
        if not poc and segment.get("shot_id") not in shot_ids:
            fail(f"Unknown shot_id in edit decision: {segment.get('shot_id')}")
        if segment.get("shot_id"):
            covered.add(segment["shot_id"])
        media = (ASSETS / segment["clip"]).resolve()
        if not media.is_relative_to(ASSETS.resolve()) or not media.is_file():
            fail(f"Missing or out-of-project selected clip: {segment.get('clip')}")
        if float(segment.get("out", 0)) <= float(segment.get("in", 0)):
            fail(f"Invalid source in/out for segment {segment.get('shot_id')}.")

    if not poc:
        missing_shots = shot_ids - covered
        if missing_shots:
            fail("No selected video for planned shots: " + ", ".join(sorted(missing_shots)))

    names = [Path(stem["path"]).name for stem in stems]
    required_stems = mix.get("required_stems", EXPECTED_STEMS)
    missing_stems = set(required_stems) - set(names)
    if missing_stems:
        fail("Mix is missing required stems: " + ", ".join(sorted(missing_stems)))
    for stem in stems:
        media = (ASSETS / stem["path"]).resolve()
        if not media.is_relative_to(ASSETS.resolve()) or not media.is_file():
            fail(f"Missing or out-of-project audio stem: {stem.get('path')}")
        if "gain_db" not in stem:
            fail(f"Each mix stem needs an explicit gain_db: {stem.get('path')}")

    caption_filter = mix.get("caption_filter", CAPTION_FILTER)
    if caption_filter:
        caption_asset = (ROOT / caption_filter.split("=", 1)[1]).resolve()
        if not caption_asset.is_relative_to(ROOT.resolve()) or not caption_asset.is_file():
            fail(f"Missing or out-of-project post-reviewed caption/alignment file: {caption_asset}")
    elif not poc:
        fail("Full assembly requires a post-reviewed caption/alignment file.")

    target_seconds = float(mix.get("target_duration_seconds", poc_target_seconds() if poc else TARGET_SECONDS))
    timeline_seconds = sum(float(segment["out"]) - float(segment["in"]) for segment in segments)
    if abs(timeline_seconds - target_seconds) > 0.5:
        fail(f"Selected clips total {timeline_seconds:.3f}s; target is {target_seconds:.3f}s.")
    return segments, stems, caption_filter, target_seconds


def assemble(poc: bool = False) -> None:
    segments, stems, caption_filter, target_seconds = validate_inputs(poc)
    command = [ffmpeg_bin(), "-hide_banner", "-y"]
    for segment in segments:
        duration = float(segment["out"]) - float(segment["in"])
        command += ["-ss", str(float(segment["in"])), "-t", str(duration),
                    "-i", str((ASSETS / segment["clip"]).resolve())]
    for stem in stems:
        command += ["-i", str((ASSETS / stem["path"]).resolve())]

    filters = []
    video_labels = []
    for index in range(len(segments)):
        label = f"v{index}"
        video_labels.append(f"[{label}]")
        filters.append(
            f"[{index}:v:0]fps=24,scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,"
            f"setpts=PTS-STARTPTS[{label}]"
        )
    filters.append("".join(video_labels) + f"concat=n={len(segments)}:v=1:a=0[vbase]")
    if caption_filter:
        filters.append(f"[vbase]{caption_filter}[vout]")
    else:
        filters.append("[vbase]null[vout]")

    stem_labels = []
    offset = len(segments)
    for index, stem in enumerate(stems):
        label = f"a{index}"
        stem_labels.append(f"[{label}]")
        gain = float(stem["gain_db"])
        filters.append(
            f"[{offset + index}:a:0]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"volume={gain}dB[{label}]"
        )
    filters.append(
        "".join(stem_labels)
        + f"amix=inputs={len(stems)}:duration=longest:dropout_transition=0:normalize=0,"
        + "alimiter=limit=0.94,loudnorm=I=-16:LRA=10:TP=-1.5[aout]"
    )

    command += [
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "[aout]",
        "-t", str(target_seconds),
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k",
        "-ar", "48000", "-ac", "2", "-movflags", "+faststart",
        str(POC_OUTPUT if poc else OUTPUT),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    print(f"Assembled {(POC_OUTPUT if poc else OUTPUT).relative_to(ROOT)}.")
    technical_qa(poc)
    contact_sheet(poc)


def technical_qa(poc: bool = False) -> None:
    output = POC_OUTPUT if poc else OUTPUT
    target_seconds = poc_target_seconds() if poc else TARGET_SECONDS
    if poc and POC_MIX.is_file():
        target_seconds = float(read_json(POC_MIX).get("target_duration_seconds", target_seconds))
    if not output.is_file():
        fail(f"No output to inspect: {output}")
    command = [
        ffprobe_bin(), "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
        "-of", "json", str(output),
    ]
    result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    report = json.loads(result.stdout)
    print(json.dumps(report, indent=2))
    video = next((s for s in report.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in report.get("streams", []) if s.get("codec_type") == "audio"), None)
    duration = float(report.get("format", {}).get("duration", 0))
    if not video or not audio:
        fail("Technical QA failed: video or audio stream is missing.")
    if (video.get("width"), video.get("height"), video.get("r_frame_rate")) != (1920, 1080, "24/1"):
        fail("Technical QA failed: video specifications do not match the project.")
    if abs(duration - target_seconds) > 0.5:
        fail(f"Technical QA failed: duration {duration:.3f}s, expected {target_seconds:.3f}s.")
    decode = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(output), "-f", "null", "-"], cwd=ROOT, capture_output=True, text=True)
    if decode.returncode != 0:
        fail("Technical decode failed: " + (decode.stderr.strip() or "unknown FFmpeg error"))
    volume = subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-i", str(output), "-vn", "-af", "volumedetect", "-f", "null", "-"],
        cwd=ROOT, capture_output=True, text=True,
    )
    import re
    volume_text = volume.stderr + "\n" + volume.stdout
    mean = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", volume_text)
    peak = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", volume_text)
    qa = {
        "status": "technical_decode_pass",
        "output_path": str(output.relative_to(ROOT)),
        "ffprobe": report,
        "decode_stderr": decode.stderr.strip(),
        "audio_level": {
            "mean_volume_db": float(mean.group(1)) if mean else None,
            "max_volume_db": float(peak.group(1)) if peak else None,
            "ffmpeg_volumedetect_exit_code": volume.returncode,
        },
        "subjective_review": "Visual contact sheet and sample listening are separate review steps; assistant runtime had no audio-input support.",
    }
    FINAL_QA.write_text(json.dumps(qa, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(qa["audio_level"], indent=2))
    print(f"Full stream decode passed. QA report: {FINAL_QA.relative_to(ROOT)}")


def contact_sheet(poc: bool = False) -> None:
    output = POC_OUTPUT if poc else OUTPUT
    if not output.is_file():
        fail(f"No video for contact sheet: {output}")
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        fail("Pillow is required to build the editorial contact sheet.")
    probe = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    duration = float(probe.stdout.strip())
    columns, rows = 4, 4
    thumb_w, thumb_h, label_h = 320, 180, 24
    sheet = Image.new("RGB", (columns * thumb_w, rows * (thumb_h + label_h)), "#eee7d6")
    draw = ImageDraw.Draw(sheet)
    with tempfile.TemporaryDirectory(prefix="video-contact-") as temp_dir:
        for index in range(columns * rows):
            second = duration * (index + 0.5) / (columns * rows)
            frame = Path(temp_dir) / f"frame_{index:02d}.jpg"
            subprocess.run(
                [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{second:.3f}", "-i", str(output), "-frames:v", "1", "-vf", f"scale={thumb_w}:{thumb_h}:force_original_aspect_ratio=decrease,pad={thumb_w}:{thumb_h}:(ow-iw)/2:(oh-ih)/2", str(frame)],
                cwd=ROOT, check=True,
            )
            image = Image.open(frame).convert("RGB")
            x, y = (index % columns) * thumb_w, (index // columns) * (thumb_h + label_h)
            sheet.paste(image, (x, y))
            draw.text((x + 8, y + thumb_h + 4), f"{second:06.2f}s", fill="#211f1b")
    sheet.save(CONTACT_SHEET, quality=92)
    print(f"Contact sheet: {CONTACT_SHEET.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble selected generated footage, mix stems, add reviewed captions, and run technical QA.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--assemble", action="store_true")
    mode.add_argument("--poc-assemble", action="store_true")
    mode.add_argument("--qa", action="store_true")
    mode.add_argument("--poc-qa", action="store_true")
    mode.add_argument("--contact-sheet", choices=("final", "poc"))
    args = parser.parse_args()
    if args.assemble:
        assemble()
    elif args.poc_assemble:
        assemble(poc=True)
    elif args.contact_sheet:
        contact_sheet(poc=args.contact_sheet == "poc")
    elif args.poc_qa:
        technical_qa(poc=True)
    else:
        technical_qa()


if __name__ == "__main__":
    main()
