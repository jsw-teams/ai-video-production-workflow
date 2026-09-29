"""Crop each generated 2x2 storyboard sheet into independent production frames."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
MANIFEST = PROJECT / "asset_manifest.json"
OUT = PROJECT / "assets" / "generated"


def run(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    for sheet in manifest["storyboards"]:
        source = PROJECT / sheet["path"]
        probe = json.loads(run("ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(source)))
        width = int(probe["streams"][0]["width"])
        height = int(probe["streams"][0]["height"])
        half_w, half_h = width // 2, height // 2
        gutter = max(6, round(min(width, height) * 0.006))
        rects = [
            (0, 0, half_w - gutter, half_h - gutter),
            (half_w + gutter, 0, half_w - gutter, half_h - gutter),
            (0, half_h + gutter, half_w - gutter, half_h - gutter),
            (half_w + gutter, half_h + gutter, half_w - gutter, half_h - gutter),
        ]
        for index, (x, y, crop_w, crop_h) in enumerate(rects, 1):
            output = OUT / f"{sheet['id']}_{index:02d}.jpg"
            vf = f"crop={crop_w}:{crop_h}:{x}:{y},scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
            run("ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-vf", vf, "-frames:v", "1", "-q:v", "2", str(output))
            print(f"{output.relative_to(PROJECT)} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Storyboard crop failed: {exc}", file=sys.stderr)
        raise SystemExit(1)