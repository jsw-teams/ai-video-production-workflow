from __future__ import annotations

import json
import argparse
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
TIMELINE = ASSETS / "edit_timeline.json"
OUT_DIR = ASSETS / "rendered_scenes"


def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        raise SystemExit("FFmpeg is required; it was not found on PATH.")
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Render selected watercolor plates and Blender action clips into the illustrated edit timeline.")
    parser.add_argument("--only", nargs="+", type=int, help="Render only the listed zero-based timeline item indexes.")
    args = parser.parse_args()
    plan = json.loads(TIMELINE.read_text(encoding="utf-8"))
    fps = int(plan["fps"])
    width, height = int(plan["width"]), int(plan["height"])
    sequence = plan["sequence"]
    if sum(int(x["frames"]) for x in sequence) != int(plan["target_frames"]):
        raise SystemExit("Timeline frame total does not match target_frames.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    root_input = ffmpeg()

    selected = set(args.only) if args.only else set(range(len(sequence)))
    if any(index < 0 or index >= len(sequence) for index in selected):
        raise SystemExit("--only index is outside the timeline.")
    for index, shot in enumerate(sequence):
        if index not in selected:
            continue
        source = (ROOT / shot["source"]).resolve()
        target = OUT_DIR / f"{index:02d}_{shot['id']}.mp4"
        frames = int(shot["frames"])
        if not source.is_file():
            raise SystemExit(f"Missing scene source: {source}")
        command = [root_input, "-hide_banner", "-loglevel", "error", "-y"]
        if shot["kind"] == "image":
            command += ["-loop", "1", "-framerate", str(fps), "-i", str(source)]
            direction = shot.get("move", "right")
            x_expr = f"(iw-iw/zoom)*on/{frames}" if direction == "right" else f"(iw-iw/zoom)*(1-on/{frames})"
            graph = (
                "[0:v]split=2[bgsrc][fgsrc];"
                f"[bgsrc]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},boxblur=34:18,eq=brightness=-0.24:saturation=0.72[bg];"
                "[fgsrc]scale=2016:1296:force_original_aspect_ratio=increase,crop=2016:1296,"
                f"zoompan=z='1.015+0.025*on/{frames}':x='{x_expr}':"
                f"y='(ih-ih/zoom)*0.5':d=1:s=1680x1080:fps={fps},"
                "eq=saturation=1.02:contrast=1.015[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2:format=auto,"
                "drawbox=x=118:y=0:w=1684:h=1080:color=0xeadfc8@0.56:t=3,format=yuv420p[v]"
            )
            command += [
                "-filter_complex", graph, "-map", "[v]", "-frames:v", str(frames),
                "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart", str(target),
            ]
        elif shot["kind"] == "video":
            command += ["-i", str(source)]
            graph = f"[0:v]fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v]"
            command += [
                "-filter_complex", graph, "-map", "[v]", "-frames:v", str(frames),
                "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart", str(target),
            ]
        else:
            raise SystemExit(f"Unsupported source kind: {shot['kind']}")
        subprocess.run(command, cwd=ROOT, check=True)
        print(f"Rendered {target.name} ({frames / fps:.2f}s)", flush=True)

    print(f"Rendered {len(sequence)} selected picture segments ({plan['target_frames'] / fps:.3f}s total).")


if __name__ == "__main__":
    main()
