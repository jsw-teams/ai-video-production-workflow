"""Prepare the measured song excerpt and recorded office-audio stems for the GPT POC."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf


PROJECT = Path(__file__).resolve().parent
ASSETS = PROJECT / "assets"
TIMELINE_PATH = ASSETS / "poc_timeline.json"
FOLEY_MANIFEST_PATH = ASSETS / "foley_sources.json"
REVIEW_PATH = ASSETS / "poc_audio_inputs_review.json"
SAMPLE_RATE = 48_000


def run_ffmpeg(command: list[str]) -> None:
    subprocess.run(command, cwd=PROJECT, check=True)


def decode_stereo(path: Path) -> np.ndarray:
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-vn", "-f", "f32le", "-acodec", "pcm_f32le", "-ar", str(SAMPLE_RATE),
        "-ac", "2", "pipe:1",
    ]
    result = subprocess.run(command, cwd=PROJECT, check=True, capture_output=True)
    values = np.frombuffer(result.stdout, dtype="<f4")
    if values.size < 2 or values.size % 2:
        raise ValueError(f"FFmpeg returned an invalid stereo buffer for {path}.")
    return values.reshape(-1, 2).copy()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_token(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum() or character == "'")


def find_word(timeline: dict, value: str) -> dict:
    wanted = normalize_token(value)
    for line in timeline.get("lines", []):
        for word in line.get("words", []):
            if normalize_token(str(word.get("text", ""))) == wanted and float(word.get("start_seconds", -1)) >= 0:
                return word
    raise ValueError(f"Measured POC timeline does not contain the lyric word '{value}'.")


def select_source_offsets(audio: np.ndarray, duration_seconds: float, count: int) -> list[dict]:
    window = max(1, int(duration_seconds * SAMPLE_RATE))
    if len(audio) < window:
        raise ValueError("Recorded Foley source is shorter than the requested event window.")
    stride = max(1, SAMPLE_RATE // 10)
    candidates: list[tuple[float, int, float, float]] = []
    for start in range(0, len(audio) - window + 1, stride):
        segment = audio[start:start + window]
        rms = float(np.sqrt(np.mean(np.square(segment), dtype=np.float64)))
        attack = float(np.mean(np.abs(np.diff(segment, axis=0)), dtype=np.float64))
        candidates.append((0.55 * rms + 0.45 * attack, start, rms, attack))
    candidates.sort(reverse=True)
    chosen: list[tuple[float, int, float, float]] = []
    separation = window + int(0.06 * SAMPLE_RATE)
    for candidate in candidates:
        if all(abs(candidate[1] - old[1]) >= separation for old in chosen):
            chosen.append(candidate)
        if len(chosen) >= count:
            break
    if len(chosen) < count:
        for candidate in candidates:
            if candidate not in chosen:
                chosen.append(candidate)
            if len(chosen) >= count:
                break
    if len(chosen) < count:
        chosen = [candidates[0]] * count
    return [
        {
            "source_start_seconds": round(start / SAMPLE_RATE, 4),
            "window_seconds": round(window / SAMPLE_RATE, 4),
            "activity_score": round(score, 7),
            "rms": round(rms, 7),
            "mean_absolute_sample_difference": round(attack, 7),
        }
        for score, start, rms, attack in chosen[:count]
    ]


def event_time(timeline: dict, specification: dict) -> float:
    if "word" in specification:
        return float(find_word(timeline, specification["word"])["start_seconds"]) + float(specification.get("offset_seconds", 0.0))
    return float(specification["time_seconds"])


def pan_stereo(audio: np.ndarray, pan: float) -> np.ndarray:
    pan = max(-1.0, min(1.0, pan))
    mono = audio.mean(axis=1)
    angle = (pan + 1.0) * math.pi / 4.0
    return np.column_stack((mono * math.cos(angle), mono * math.sin(angle))).astype(np.float32)


def fade_audio(audio: np.ndarray, fade_in_seconds: float = 0.025, fade_out_seconds: float = 0.10) -> np.ndarray:
    result = audio.astype(np.float32, copy=True)
    fade_in = min(len(result), int(fade_in_seconds * SAMPLE_RATE))
    fade_out = min(len(result), int(fade_out_seconds * SAMPLE_RATE))
    if fade_in:
        result[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)[:, None]
    if fade_out:
        result[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, dtype=np.float32)[:, None]
    return result


def write_pcm24(path: Path, audio: np.ndarray) -> None:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0.98:
        audio = audio * (0.98 / peak)
    sf.write(path, audio.astype(np.float32), SAMPLE_RATE, subtype="PCM_24")


def rms_dbfs(audio: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))
    return round(20.0 * math.log10(max(1e-8, rms)), 2)


def prepare(timeline: dict) -> dict:
    duration = float(timeline["duration_seconds"])
    song_path = (PROJECT / timeline["song_path"]).resolve()
    if not song_path.is_file():
        raise FileNotFoundError(f"Selected song source is missing: {song_path}")

    song_output = ASSETS / "poc_song_excerpt.wav"
    run_ffmpeg([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{float(timeline['clip_start_audio_seconds']):.6f}", "-i", str(song_path),
        "-t", f"{duration:.6f}", "-vn", "-ar", str(SAMPLE_RATE), "-ac", "2",
        "-c:a", "pcm_s24le", str(song_output),
    ])
    song_excerpt_audio = decode_stereo(song_output)

    foley_manifest = json.loads(FOLEY_MANIFEST_PATH.read_text(encoding="utf-8"))
    source_assets = {item["id"]: item for item in foley_manifest["assets"]}
    source_paths = {
        "keyboard": ASSETS / "office_keyboard.mp3",
        "paper": ASSETS / "paper_shuffle.mp3",
        "pen": ASSETS / "pen_writing.mp3",
        "ambience": ASSETS / "busy_office.mp3",
    }
    source_ids = {
        "keyboard": "office_keyboard_cc0",
        "paper": "paper_shuffling_cc0",
        "pen": "pen_writing_cc0",
        "ambience": "busy_office_ambience_cc0",
    }
    for key, path in source_paths.items():
        if not path.is_file() or source_ids[key] not in source_assets:
            raise FileNotFoundError(f"Missing local CC0 source or source record for {key}: {path}")

    events = [
        {"name": "turn source page", "word": "ships", "source": "paper", "offset_seconds": -0.06, "duration_seconds": 0.62, "gain_db": -10.0, "pan": -0.48},
        {"name": "mark checked date", "word": "date", "source": "pen", "duration_seconds": 0.44, "gain_db": -10.0, "pan": -0.35},
        {"name": "circle verified figure", "word": "math", "source": "pen", "duration_seconds": 0.46, "gain_db": -10.0, "pan": -0.20},
        {"name": "initial source check", "word": "initial", "source": "pen", "duration_seconds": 0.62, "gain_db": -9.0, "pan": -0.30},
        {"name": "manager packet reaches worker", "time_seconds": float(timeline["chorus2_start_seconds"]), "source": "paper", "duration_seconds": 0.82, "gain_db": -9.0, "pan": 0.48},
        {"name": "open request folder", "word": "open", "source": "paper", "duration_seconds": 0.52, "gain_db": -11.0, "pan": 0.36},
        {"name": "build deck keystrokes", "word": "build", "source": "keyboard", "duration_seconds": 0.27, "gain_db": -9.0, "pan": 0.30},
        {"name": "read source tabs", "word": "read", "source": "paper", "duration_seconds": 0.52, "gain_db": -11.0, "pan": 0.30},
        {"name": "mark workflow status", "word": "mark", "source": "keyboard", "duration_seconds": 0.27, "gain_db": -11.0, "pan": -0.08},
        {"name": "draft final message", "word": "draft", "source": "keyboard", "duration_seconds": 0.27, "gain_db": -11.0, "pan": 0.12},
    ]
    for event in events:
        event["timeline_seconds"] = round(max(0.0, event_time(timeline, event)), 4)

    decoded = {key: decode_stereo(path) for key, path in source_paths.items()}
    offsets_by_source: dict[str, list[dict]] = {}
    for key in ("keyboard", "paper", "pen"):
        matching_events = [event for event in events if event["source"] == key]
        longest = max(float(event["duration_seconds"]) for event in matching_events)
        offsets = select_source_offsets(decoded[key], longest, len(matching_events))
        offsets_by_source[key] = offsets
        for event, selected in zip(matching_events, offsets):
            event.update(selected)

    output_samples = int(round(duration * SAMPLE_RATE))
    foley_mix = np.zeros((output_samples, 2), dtype=np.float32)
    used_by_source = {"keyboard": 0, "paper": 0, "pen": 0}
    for event in events:
        source_key = event["source"]
        source_offset = int(float(event["source_start_seconds"]) * SAMPLE_RATE)
        length = max(1, int(float(event["duration_seconds"]) * SAMPLE_RATE))
        sample = decoded[source_key][source_offset:source_offset + length]
        if not len(sample):
            raise ValueError(f"Selected source segment for '{event['name']}' is empty.")
        sample = pan_stereo(fade_audio(sample), float(event["pan"]))
        sample *= 10.0 ** (float(event["gain_db"]) / 20.0)
        event_start = int(round(float(event["timeline_seconds"]) * SAMPLE_RATE))
        event_end = min(output_samples, event_start + len(sample))
        if event_start < output_samples and event_end > event_start:
            foley_mix[event_start:event_end] += sample[:event_end - event_start]
        used_by_source[source_key] += 1

    ambience = decoded["ambience"]
    repeats = int(math.ceil(output_samples / len(ambience)))
    ambience_bed = np.tile(ambience, (repeats, 1))[:output_samples].astype(np.float32)
    ambience_bed *= 10.0 ** (-30.0 / 20.0)
    ambience_bed = fade_audio(ambience_bed, fade_in_seconds=0.08, fade_out_seconds=0.45)

    foley_output = ASSETS / "poc_sync_foley.wav"
    ambience_output = ASSETS / "poc_ambience.wav"
    write_pcm24(foley_output, foley_mix)
    write_pcm24(ambience_output, ambience_bed)

    edit_manifest = {
        "version": 1,
        "status": "single_selected_picture_source_pending_subjective_review",
        "segments": [
            {
                "clip": "poc_picture.mp4",
                "in": 0.0,
                "out": round(duration, 6),
                "purpose": "Full measured Pre-Chorus 2 to Chorus 2 POC from the current song timeline.",
            }
        ],
    }
    mix_manifest = {
        "version": 1,
        "status": "actual_song_plus_recorded_cc0_foley_pending_audio_review",
        "target_duration_seconds": round(duration, 6),
        "caption_filter": None,
        "required_stems": ["poc_song_excerpt.wav", "poc_sync_foley.wav", "poc_ambience.wav"],
        "stems": [
            {"path": "poc_song_excerpt.wav", "gain_db": -1.0, "role": "selected full song excerpt; lead and accompaniment remain as generated"},
            {"path": "poc_sync_foley.wav", "gain_db": 0.0, "role": "recorded event foley, timed from measured lyric-word onsets"},
            {"path": "poc_ambience.wav", "gain_db": 0.0, "role": "recorded CC0 stereo office ambience, already attenuated by 30 dB"},
        ],
        "technical_mix_target": {"integrated_loudness_lufs": -16, "true_peak_dbtp_max": -1.5},
        "subjective_mix_review": "BLOCKED until an actual full passage audio audition is available; no balance or intelligibility pass claimed.",
    }
    (ASSETS / "poc_edit_decision.json").write_text(json.dumps(edit_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ASSETS / "poc_mix.json").write_text(json.dumps(mix_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "status": "audio_inputs_prepared_pending_subjective_review",
        "candidate_id": timeline["candidate_id"],
        "song_path": timeline["song_path"],
        "clip_start_audio_seconds": timeline["clip_start_audio_seconds"],
        "clip_end_audio_seconds": timeline["clip_end_audio_seconds"],
        "duration_seconds": round(duration, 6),
        "sample_rate_hz": SAMPLE_RATE,
        "source_assets": {
            key: {
                "path": path.relative_to(PROJECT).as_posix(),
                "sha256": sha256_file(path),
                "source_id": source_ids[key],
                "source_url": source_assets[source_ids[key]]["reference_inputs"][0],
                "license_note": source_assets[source_ids[key]]["license_note"],
            }
            for key, path in source_paths.items()
        },
        "events": events,
        "event_count_by_source": used_by_source,
        "output_metrics": {
            "song_excerpt": {
                "path": song_output.relative_to(PROJECT).as_posix(),
                "sha256": sha256_file(song_output),
                "rms_dbfs": rms_dbfs(song_excerpt_audio),
                "peak": round(float(np.max(np.abs(song_excerpt_audio))), 7),
            },
            "sync_foley": {
                "path": foley_output.relative_to(PROJECT).as_posix(),
                "sha256": sha256_file(foley_output),
                "rms_dbfs": rms_dbfs(foley_mix),
                "peak": round(float(np.max(np.abs(foley_mix))), 7),
            },
            "ambience": {
                "path": ambience_output.relative_to(PROJECT).as_posix(),
                "sha256": sha256_file(ambience_output),
                "rms_dbfs": rms_dbfs(ambience_bed),
                "peak": round(float(np.max(np.abs(ambience_bed))), 7),
            },
        },
        "pipeline_input_manifests": ["assets/poc_edit_decision.json", "assets/poc_mix.json"],
        "subjective_audio_review": "BLOCKED until an actual full passage audition is available; technical audio preparation is not an audition.",
    }


def main() -> None:
    if not TIMELINE_PATH.is_file():
        raise FileNotFoundError(f"Build the selected-song measured timeline first: {TIMELINE_PATH}")
    timeline = json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))
    if timeline.get("selected_song_status") != "provisional_for_poc_only":
        raise ValueError("Audio POC inputs may only use a provisionally selected song after the 3-candidate comparison.")
    report = prepare(timeline)
    REVIEW_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Prepared actual song excerpt and {sum(report['event_count_by_source'].values())} timed Foley events "
        f"for {report['duration_seconds']:.3f}s; subjective audio review remains BLOCKED.",
        flush=True,
    )


if __name__ == "__main__":
    main()
