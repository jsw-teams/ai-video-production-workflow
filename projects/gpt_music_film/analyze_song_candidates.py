"""Inspect the new ACE-Step song candidates with the installed local ASR environment.

This is a selection aid, not a lyric WER gate. It records duration, tempo, and a
small set of narrative-anchor transcript snippets, then leaves the final choice
to production judgment.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
ASSETS = PROJECT / "assets"
MANIFEST_PATH = ASSETS / "asset_manifest.json"
REPORT_PATH = PROJECT / "song_candidate_review.json"
DEFAULT_ASR_MODEL = Path(
    r"D:\AIProductionModels\huggingface-cache\hub\models--mobiuslabsgmbh--faster-whisper-large-v3-turbo"
)
ANCHORS = [
    "it was working yesterday",
    "what left my machine",
    "who actually said yes",
    "who said yes",
    "one human name",
    "Robert Williams",
    "Source? Citation?",
    "live database",
    "the docket had to set them straight",
]


def candidate_python_paths() -> list[Path]:
    paths: list[Path] = []
    configured = os.environ.get("AI_AUDIO_ANALYSIS_PYTHON")
    if configured:
        paths.append(Path(configured).expanduser())
    # This is the observed local ASR install. Check it before using it; never
    # assume the workstation or its D: drive exists on another machine.
    paths.append(Path(r"D:\AIVideoTools\ASR\Scripts\python.exe"))
    current = Path(sys.executable)
    paths.append(current)
    found_python = shutil.which("python")
    if found_python:
        paths.append(Path(found_python))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def ensure_audio_environment() -> None:
    required = "import numpy, librosa, faster_whisper"
    errors: list[str] = []
    for interpreter in candidate_python_paths():
        if not interpreter.is_file():
            errors.append(f"not found: {interpreter}")
            continue
        if Path(sys.executable).resolve() == interpreter.resolve():
            if all(importlib.util.find_spec(name) for name in ("numpy", "librosa", "faster_whisper")):
                return
            errors.append(f"missing one or more audio modules: {interpreter}")
            continue
        result = subprocess.run(
            [str(interpreter), "-c", required], capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            print(f"Using discovered audio-analysis environment: {interpreter}", flush=True)
            os.execv(str(interpreter), [str(interpreter), str(Path(__file__).resolve()), *sys.argv[1:]])
        errors.append(f"audio modules unavailable: {interpreter}")
    raise SystemExit(
        "Song analysis needs numpy, librosa, and faster-whisper. Checked the configured "
        "AI_AUDIO_ANALYSIS_PYTHON, the observed D:\\AIVideoTools\\ASR environment, and the "
        "active Python. Set AI_AUDIO_ANALYSIS_PYTHON to an existing Python executable that "
        "already has those packages. Details: " + "; ".join(errors)
    )


ensure_audio_environment()

import librosa  # noqa: E402
import numpy as np  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402


def model_path() -> Path:
    configured = os.environ.get("AI_AUDIO_ASR_MODEL")
    candidates = [Path(configured).expanduser()] if configured else []
    if DEFAULT_ASR_MODEL.is_dir():
        candidates.extend(sorted((DEFAULT_ASR_MODEL / "snapshots").glob("*"), reverse=True))
        candidates.append(DEFAULT_ASR_MODEL)
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "model.bin").is_file():
            return candidate
    raise SystemExit(
        "No cached faster-whisper model was found. Set AI_AUDIO_ASR_MODEL to an existing "
        "local CTranslate2 model directory; this script does not download models."
    )


def candidate_assets(manifest: dict) -> list[dict]:
    return [
        item
        for item in manifest.get("assets", [])
        if item.get("id", "").startswith("it_was_working_candidate_")
        and item.get("output_path")
    ]


def inspect_audio(path: Path, requested_bpm: float | None) -> dict:
    y, sr = librosa.load(str(path), sr=22050, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames", trim=False)
    measured = float(np.asarray(tempo).reshape(-1)[0])
    rms = librosa.feature.rms(y=y)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    frame_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr)
    centroid_times = librosa.frames_to_time(np.arange(len(centroid)), sr=sr)
    windows = {
        "verse1": (15.0, 45.0),
        "first_chorus": (58.0, 88.0),
        "agent_passage": (88.0, 115.0),
        "verification": (146.0, 156.0),
        "final_chorus": (156.0, 184.0),
        "outro": (184.0, min(195.0, len(y) / sr)),
    }
    section_profile: dict[str, dict] = {}
    for section, (start, end) in windows.items():
        mask = (frame_times >= start) & (frame_times < end)
        cmask = (centroid_times >= start) & (centroid_times < end)
        if mask.any() and cmask.any():
            mean_rms = float(rms[mask].mean())
            section_profile[section] = {
                "start_seconds": start,
                "end_seconds": end,
                "mean_rms_dbfs": round(float(20 * np.log10(max(1e-8, mean_rms))), 2),
                "mean_spectral_centroid_hz": round(float(centroid[cmask].mean()), 1),
            }
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    chroma_times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr)
    hook_vectors = []
    for start, end in ((55.0, 65.0), (184.0, min(191.0, len(y) / sr))):
        mask = (chroma_times >= start) & (chroma_times < end)
        hook_vectors.append(chroma[:, mask].mean(axis=1) if mask.any() else np.zeros(12))
    hook_harmony_similarity = float(np.corrcoef(hook_vectors[0], hook_vectors[1])[0, 1])
    verse_rms = section_profile.get("verse1", {}).get("mean_rms_dbfs")
    chorus_rms = section_profile.get("first_chorus", {}).get("mean_rms_dbfs")
    final_rms = section_profile.get("final_chorus", {}).get("mean_rms_dbfs")
    return {
        "duration_seconds": round(len(y) / sr, 3),
        "sample_rate_hz": sr,
        "requested_bpm": requested_bpm,
        "detected_bpm": round(measured, 2),
        "beat_count_detected": int(len(beat_frames)),
        "peak_linear": round(float(np.max(np.abs(y))), 5),
        "mean_rms_dbfs": round(float(20 * np.log10(max(1e-8, float(rms.mean())))), 2),
        "section_profile": section_profile,
        "chorus_lift_over_verse1_db": round(chorus_rms - verse_rms, 2) if chorus_rms is not None and verse_rms is not None else None,
        "final_chorus_lift_over_verse1_db": round(final_rms - verse_rms, 2) if final_rms is not None and verse_rms is not None else None,
        "first_chorus_to_closing_hook_chroma_similarity": round(hook_harmony_similarity, 4),
        "acoustic_metrics_note": "RMS, spectral centroid, and chroma are structural proxies; they do not measure subjective melody quality or replace a human listening pass.",
    }


def transcribe(path: Path, model: WhisperModel) -> dict:
    segments, info = model.transcribe(
        str(path), language="en", vad_filter=True, beam_size=3, word_timestamps=False
    )
    captured: list[dict] = []
    full_text: list[str] = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        full_text.append(text)
        captured.append({
            "start": round(float(segment.start), 2),
            "end": round(float(segment.end), 2),
            "text": text,
        })
    transcript = " ".join(full_text)
    lowered = " ".join(transcript.casefold().split())
    anchors = {
        phrase: phrase.casefold() in lowered
        for phrase in ANCHORS
    }
    return {
        "engine": "faster-whisper local large-v3-turbo, CPU int8",
        "language": info.language,
        "language_probability": round(float(info.language_probability), 4),
        "anchor_phrase_presence": anchors,
        "transcript_segments": captured,
        "transcript": transcript,
        "policy": "Diagnostic only; no full-song WER, no lyric correction loop, no candidate rejection threshold.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect only the new It Was Working Yesterday candidates.")
    parser.add_argument("--candidate", action="append", help="Candidate asset id; repeat to inspect more than one.")
    parser.add_argument("--no-asr", action="store_true", help="Skip local ASR and inspect basic audio properties only.")
    parser.add_argument("--select", help="Record the production-selected candidate id in the report.")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assets = candidate_assets(manifest)
    if args.candidate:
        requested = set(args.candidate)
        known = {asset["id"] for asset in assets}
        unknown = requested - known
        if unknown:
            raise SystemExit("Unknown candidate id(s): " + ", ".join(sorted(unknown)))
        assets = [asset for asset in assets if asset["id"] in requested]
    if not assets:
        raise SystemExit("No generated It Was Working Yesterday candidates are present in the manifest.")

    model = None if args.no_asr else WhisperModel(str(model_path()), device="cpu", compute_type="int8")
    report = {
        "status": "selection_diagnostic",
        "analysis_python": sys.executable,
        "asr_model": str(model_path()) if model else None,
        "selection_policy": "Song quality and hook first; ASR and tempo are supporting signals only.",
        "selected_song_id": args.select,
        "candidates": [],
    }
    for asset in assets:
        path = PROJECT / asset["output_path"]
        if not path.is_file():
            print(f"Skipping missing audio file: {path}", flush=True)
            continue
        metadata = asset.get("generated_metadata", {})
        requested_bpm = asset.get("tempo_bpm")
        result = {
            "id": asset["id"],
            "output_path": asset["output_path"],
            "duration_requested_seconds": asset.get("duration_seconds"),
            "generated_lyrics_sha256": metadata.get("lyrics_sha256"),
            "generated_key": (metadata.get("metas") or {}).get("keyscale"),
            "generated_bpm": (metadata.get("metas") or {}).get("bpm", requested_bpm),
            "audio": inspect_audio(path, float(requested_bpm) if requested_bpm else None),
        }
        if model:
            print(f"Checking narrative anchors in {asset['id']}…", flush=True)
            result["asr"] = transcribe(path, model)
        report["candidates"].append(result)
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            f"{asset['id']}: {result['audio']['duration_seconds']:.2f}s, "
            f"{result['audio']['detected_bpm']:.1f} BPM",
            flush=True,
        )
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Selection diagnostics: {REPORT_PATH}")


if __name__ == "__main__":
    main()
