"""Transcribe and compare local song candidates; retain real word timings."""

from __future__ import annotations

import json
import re
import argparse
from pathlib import Path

import librosa
import numpy as np


PROJECT = Path(__file__).resolve().parent
ASSETS = PROJECT / "assets"
MANIFEST = json.loads((ASSETS / "asset_manifest.json").read_text(encoding="utf-8"))
LYRICS_TEXT = (ASSETS / "song_lyrics.txt").read_text(encoding="utf-8")
REPORT_PATH = PROJECT / "song_candidate_review.json"
WHISPER_OUTPUT = Path(r"D:\AIVideoTools\ASR\input")
MODEL_ID = "OpenAI Whisper large / ggml-large.bin through official ggml-org whisper.cpp v1.8.7 CPU CLI"
MODEL_LICENSE = (
    "whisper.cpp code: MIT. Whisper model family: MIT per the OpenAI Whisper repository. "
    "The cached ggml-large.bin file's original download provenance is not verified; it is used only "
    "for internal analysis and is not included in deliverables."
)
EXPECTED_SECTIONS = [
    ("Cold Open", 0, 2),
    ("Verse 1", 2, 16),
    ("Pre-Chorus 1", 18, 8),
    ("Chorus 1", 26, 8),
    ("Verse 2", 34, 16),
    ("Pre-Chorus 2", 50, 4),
    ("Chorus 2", 54, 8),
    ("Agent Break", 62, 8),
    ("Verification Bridge", 70, 8),
    ("Final Chorus", 78, 12),
    ("Outro", 90, 4),
]


def tokens(text: str) -> list[str]:
    text = text.replace("’", "'").replace("‘", "'")
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.lower())


def reference_lyrics() -> list[str]:
    result: list[str] = []
    for raw_line in LYRICS_TEXT.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("TITLE:", "FORM:", "VOCAL:")):
            continue
        if line.startswith("["):
            continue
        line = re.sub(r"\[[^\]]*\]", " ", line)
        result.extend(tokens(line))
    return result


def align_words(reference: list[str], observed: list[dict]) -> tuple[dict, list[dict]]:
    hyp = [item["token"] for item in observed]
    n, m = len(reference), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    back: list[list[str]] = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0], back[i][0] = i, "delete"
    for j in range(1, m + 1):
        dp[0][j], back[0][j] = j, "insert"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            same = reference[i - 1] == hyp[j - 1]
            candidates = [
                (dp[i - 1][j - 1] + (0 if same else 1), "match" if same else "substitute"),
                (dp[i - 1][j] + 1, "delete"),
                (dp[i][j - 1] + 1, "insert"),
            ]
            dp[i][j], back[i][j] = min(candidates, key=lambda item: item[0])
    operations: list[dict] = []
    i, j = n, m
    while i or j:
        op = back[i][j]
        if op in ("match", "substitute"):
            operations.append({
                "operation": op,
                "reference_index": i - 1,
                "recognized_index": j - 1,
                "reference": reference[i - 1],
                "recognized": observed[j - 1]["token"],
                "start": observed[j - 1]["start"],
                "end": observed[j - 1]["end"],
                "probability": observed[j - 1]["probability"],
            })
            i -= 1
            j -= 1
        elif op == "delete":
            operations.append({
                "operation": op,
                "reference_index": i - 1,
                "recognized_index": None,
                "reference": reference[i - 1],
                "recognized": None,
            })
            i -= 1
        else:
            operations.append({
                "operation": op,
                "reference_index": None,
                "recognized_index": j - 1,
                "reference": None,
                "recognized": observed[j - 1]["token"],
                "start": observed[j - 1]["start"],
                "end": observed[j - 1]["end"],
                "probability": observed[j - 1]["probability"],
            })
            j -= 1
    operations.reverse()
    substitutions = sum(op["operation"] == "substitute" for op in operations)
    deletions = sum(op["operation"] == "delete" for op in operations)
    insertions = sum(op["operation"] == "insert" for op in operations)
    errors = substitutions + deletions + insertions
    return {
        "reference_word_count": n,
        "recognized_word_count": m,
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "word_error_rate": errors / max(1, n),
        "exact_match_rate": sum(op["operation"] == "match" for op in operations) / max(1, n),
    }, operations


def whisper_cpp_path(path: Path) -> Path:
    bpm = re.search(r"_(126|128|132)\.wav$", path.name)
    if not bpm:
        raise ValueError(f"No candidate BPM in audio filename: {path.name}")
    return WHISPER_OUTPUT / f"candidate-{bpm.group(1)}.wav.json"


def words_from_whisper_cpp(path: Path) -> tuple[str, list[dict], dict]:
    result_path = whisper_cpp_path(path)
    if not result_path.is_file():
        raise FileNotFoundError(f"Missing local Whisper JSON: {result_path}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    text_parts: list[str] = []
    words: list[dict] = []
    segment_info: list[dict] = []
    for segment in result.get("transcription", []):
        segment_text = segment.get("text", "").strip()
        if segment_text:
            text_parts.append(segment_text)
        offsets = segment.get("offsets", {})
        segment_info.append({
            "start": round(float(offsets.get("from", 0)) / 1000, 3),
            "end": round(float(offsets.get("to", 0)) / 1000, 3),
            "text": segment_text,
        })

        current_text = ""
        current_start: float | None = None
        current_end = 0.0
        current_probabilities: list[float] = []

        def flush_word() -> None:
            nonlocal current_text, current_start, current_end, current_probabilities
            if not current_text.strip() or current_start is None:
                current_text = ""
                current_start = None
                current_end = 0.0
                current_probabilities = []
                return
            word_tokens = tokens(current_text)
            span = max(0.0, current_end - current_start)
            for index, word_token in enumerate(word_tokens):
                words.append({
                    "token": word_token,
                    "start": round(current_start + span * index / max(1, len(word_tokens)), 3),
                    "end": round(current_start + span * (index + 1) / max(1, len(word_tokens)), 3),
                    "probability": round(float(np.mean(current_probabilities)), 4) if current_probabilities else None,
                })
            current_text = ""
            current_start = None
            current_end = 0.0
            current_probabilities = []

        for piece in segment.get("tokens", []):
            value = str(piece.get("text", ""))
            if value.startswith("[_") or not value.strip():
                continue
            start = float(piece.get("offsets", {}).get("from", offsets.get("from", 0))) / 1000
            end = float(piece.get("offsets", {}).get("to", offsets.get("to", 0))) / 1000
            has_word_char = bool(re.search(r"[A-Za-z0-9]", value))
            begins_word = value[:1].isspace() and has_word_char
            if begins_word:
                flush_word()
            if not current_text and not has_word_char:
                continue
            if current_start is None:
                current_start = start
            current_text += value
            current_end = max(current_end, end)
            if piece.get("p") is not None:
                current_probabilities.append(float(piece["p"]))
        flush_word()

    return " ".join(text_parts), words, {
        "language": result.get("result", {}).get("language", "unknown"),
        "language_probability": None,
        "engine": "whisper.cpp 1.8.7 official Windows CPU release",
        "source_json": str(result_path),
        "segments": segment_info,
    }


def key_estimate(chroma: np.ndarray) -> dict:
    major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    mean_chroma = chroma.mean(axis=1)
    candidates = []
    for index, name in enumerate(names):
        for mode, template in (("major", major), ("minor", minor)):
            rotated = np.roll(template, index)
            score = float(np.corrcoef(mean_chroma, rotated)[0, 1])
            candidates.append((score, f"{name} {mode}"))
    score, key = max(candidates)
    return {"key": key, "template_correlation": round(score, 4)}


def acoustic_analysis(path: Path, requested_bpm: int) -> dict:
    y, sr = librosa.load(str(path), sr=22050, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames", trim=False)
    detected_bpm = float(np.asarray(tempo).reshape(-1)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    rms = librosa.feature.rms(y=y)[0]
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    frame_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr)
    bar_seconds = 240.0 / (detected_bpm if detected_bpm > 0 else requested_bpm)
    section_metrics: dict[str, dict] = {}
    for name, start_bar, bars in EXPECTED_SECTIONS:
        start_seconds = start_bar * bar_seconds
        end_seconds = min(len(y) / sr, (start_bar + bars) * bar_seconds)
        mask = (frame_times >= start_seconds) & (frame_times < end_seconds)
        if not np.any(mask):
            continue
        section_metrics[name] = {
            "planned_start_bar": start_bar,
            "planned_bars": bars,
            "estimated_start_seconds": round(start_seconds, 3),
            "estimated_end_seconds": round(end_seconds, 3),
            "mean_rms": round(float(rms[mask].mean()), 5),
            "rms_dbfs": round(float(20 * np.log10(max(1e-8, rms[mask].mean()))), 2),
            "spectral_centroid_hz": round(float(centroid[mask].mean()), 1),
        }
    chroma_frames = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr)
    chorus_ranges = []
    for start_bar in (26, 54):
        start = start_bar * bar_seconds
        end = (start_bar + 4) * bar_seconds
        mask = (chroma_frames >= start) & (chroma_frames < end)
        chorus_ranges.append(chroma[:, mask].mean(axis=1) if np.any(mask) else np.zeros(12))
    hook_harmony_similarity = float(np.corrcoef(chorus_ranges[0], chorus_ranges[1])[0, 1])
    peak = float(np.max(np.abs(y)))
    return {
        "duration_seconds": round(len(y) / sr, 3),
        "sample_rate_hz": sr,
        "requested_bpm": requested_bpm,
        "detected_bpm": round(detected_bpm, 2),
        "beat_count_detected": int(len(beat_frames)),
        "beat_times_seconds": [round(float(value), 4) for value in beat_times],
        "seconds_per_bar_from_detected_tempo": round(bar_seconds, 4),
        "peak_linear": round(peak, 5),
        "key_estimate": key_estimate(chroma),
        "first_half_chorus_chroma_similarity": round(hook_harmony_similarity, 4),
        "sections": section_metrics,
        "energy_contrasts_db": {
            "chorus1_minus_verse1": round(section_metrics["Chorus 1"]["rms_dbfs"] - section_metrics["Verse 1"]["rms_dbfs"], 2),
            "chorus2_minus_verse2": round(section_metrics["Chorus 2"]["rms_dbfs"] - section_metrics["Verse 2"]["rms_dbfs"], 2),
            "final_chorus_minus_bridge": round(section_metrics["Final Chorus"]["rms_dbfs"] - section_metrics["Verification Bridge"]["rms_dbfs"], 2),
            "outro_minus_final_chorus": round(section_metrics["Outro"]["rms_dbfs"] - section_metrics["Final Chorus"]["rms_dbfs"], 2),
        },
        "mean_onset_strength": round(float(np.mean(onset)), 5),
    }


def manifest_candidates() -> list[dict]:
    return [
        item for item in MANIFEST["assets"]
        if item["id"].startswith("could_you_just_song_")
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze one or all locally generated full-song candidates.")
    parser.add_argument(
        "--candidate",
        action="append",
        help="Candidate asset id; repeat to select several. Omit to analyze every song candidate in the manifest.",
    )
    args = parser.parse_args()
    print(f"Using completed local CPU ASR results from {MODEL_ID}", flush=True)
    reference = reference_lyrics()
    results = []
    required = manifest_candidates()
    if args.candidate:
        wanted = set(args.candidate)
        unknown = wanted - {asset["id"] for asset in required}
        if unknown:
            raise ValueError("Unknown song candidate id(s): " + ", ".join(sorted(unknown)))
        required = [asset for asset in required if asset["id"] in wanted]
    for asset in required:
        audio_path = PROJECT / asset["output_path"]
        print(f"Analyzing {asset['id']}: {audio_path}", flush=True)
        transcript, words, asr = words_from_whisper_cpp(audio_path)
        lyric_metrics, word_alignment = align_words(reference, words)
        scene = asset["scene"]
        bpm_match = re.search(r"/\s*(\d+)\s+BPM", scene)
        requested_bpm = int(bpm_match.group(1)) if bpm_match else 0
        acoustic = acoustic_analysis(audio_path, requested_bpm)
        results.append({
            "asset_id": asset["id"],
            "provider_used": asset.get("provider_used"),
            "output_path": asset["output_path"],
            "generation_metadata": asset.get("generated_metadata"),
            "asr_model": MODEL_ID,
            "asr": asr,
            "transcript": transcript,
            "lyric_fit": lyric_metrics,
            "word_alignment": word_alignment,
            "acoustic_analysis": acoustic,
        })
        REPORT_PATH.write_text(json.dumps({
            "status": "technical_analysis_in_progress",
            "analysis_model": MODEL_ID,
            "analysis_model_license": MODEL_LICENSE,
            "asr_package": "Official ggml-org whisper.cpp 1.8.7 Windows CLI, MIT",
            "analysis_method": "Local whisper.cpp full-song English recognition; subword token timestamps grouped into word timings; Levenshtein alignment to the exact lyric sheet; tempo, chroma/key and section RMS from librosa features.",
            "subjective_audio_listening": "BLOCKED: this assistant runtime omitted an attached audition sample because audio input is unavailable; no subjective melody-memory, comic-performance or standalone-song pass is claimed.",
            "candidates": results,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            f"{asset['id']}: WER={lyric_metrics['word_error_rate']:.3f}; "
            f"tempo={acoustic['detected_bpm']:.2f}; key={acoustic['key_estimate']['key']}; "
            f"duration={acoustic['duration_seconds']:.2f}s",
            flush=True,
        )
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    required_ids = [asset["id"] for asset in manifest_candidates()]
    report["required_candidate_ids"] = required_ids
    report["analyzed_candidate_ids"] = [result["asset_id"] for result in report.get("candidates", [])]
    missing = set(required_ids) - set(report["analyzed_candidate_ids"])
    report["missing_candidate_ids"] = sorted(missing)
    report["status"] = (
        "partial_technical_analysis_pending_remaining_candidates"
        if missing else "technical_analysis_complete_pending_song_choice"
    )
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
