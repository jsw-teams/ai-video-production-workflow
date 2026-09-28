"""Derive the 12-bar POC boundary and sung-word events from measured audio."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
ASSETS = PROJECT / "assets"
LYRICS = ASSETS / "song_lyrics.txt"
REVIEW = PROJECT / "song_candidate_review.json"
OUTPUT = ASSETS / "poc_timeline.json"


def normalize_words(text: str) -> list[str]:
    text = text.replace("’", "'").replace("‘", "'")
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.lower())


def sections() -> tuple[list[dict], list[str]]:
    all_lines: list[dict] = []
    all_words: list[str] = []
    current_section = ""
    for raw in LYRICS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("TITLE:", "FORM:", "VOCAL:")):
            continue
        if line.startswith("[") and line.endswith("]"):
            header = line[1:-1].lower()
            if "pre-chorus 2" in header:
                current_section = "Pre-Chorus 2"
            elif "chorus 2" in header:
                current_section = "Chorus 2"
            elif "verification bridge" in header:
                current_section = "Verification Bridge"
            elif "chorus" in header:
                current_section = "Chorus 1" if not current_section else "Other"
            elif "verse" in header:
                current_section = "Other"
            elif "agent break" in header:
                current_section = "Other"
            elif "bridge" in header:
                current_section = "Other"
            else:
                current_section = "Other"
            continue
        words = normalize_words(line)
        if not words:
            continue
        start = len(all_words)
        all_words.extend(words)
        all_lines.append({
            "section": current_section,
            "text": line,
            "tokens": words,
            "reference_indices": list(range(start, len(all_words))),
        })
    return all_lines, all_words


def surface_words(line: str) -> list[str]:
    """Keep punctuation attached to visible lyric words while matching normalized tokens."""
    result: list[str] = []
    for part in line.split():
        if normalize_words(part):
            result.append(part)
    return result


def build(candidate_id: str) -> dict:
    report = json.loads(REVIEW.read_text(encoding="utf-8"))
    candidate = next((x for x in report["candidates"] if x["asset_id"] == candidate_id), None)
    if candidate is None:
        raise KeyError(f"Candidate is missing from {REVIEW.name}: {candidate_id}")
    if candidate["lyric_fit"]["word_error_rate"] > 0.30:
        raise ValueError("Candidate lyric fit exceeds the 0.30 POC limit; do not force a misleading lyric animation.")

    lyric_lines, reference = sections()
    timing_by_reference: dict[int, dict] = {}
    for operation in candidate["word_alignment"]:
        index = operation.get("reference_index")
        if index is None or operation["operation"] not in ("match", "substitute"):
            continue
        if operation.get("start") is None or operation.get("end") is None:
            continue
        timing_by_reference[int(index)] = {
            "start": float(operation["start"]),
            "end": float(operation["end"]),
            "operation": operation["operation"],
            "recognized": operation.get("recognized"),
            "probability": operation.get("probability"),
        }

    focus_lines: list[dict] = []
    for line in lyric_lines:
        if line["section"] not in ("Pre-Chorus 2", "Chorus 2"):
            continue
        words = []
        matched_count = 0
        for word_index, ref_index in enumerate(line["reference_indices"]):
            timing = timing_by_reference.get(ref_index)
            if timing:
                matched_count += timing["operation"] == "match"
                words.append({
                    "text": surface_words(line["text"])[word_index],
                    "start_seconds": timing["start"],
                    "end_seconds": timing["end"],
                    "alignment": timing["operation"],
                    "recognized": timing["recognized"],
                    "asr_probability": timing["probability"],
                })
            else:
                words.append({
                    "text": surface_words(line["text"])[word_index],
                    "start_seconds": None,
                    "end_seconds": None,
                    "alignment": "missing",
                    "recognized": None,
                    "asr_probability": None,
                })
        valid_times = [word for word in words if word["start_seconds"] is not None]
        if valid_times:
            focus_lines.append({
                "section": line["section"],
                "text": line["text"],
                "words": words,
                "start_absolute_seconds": min(word["start_seconds"] for word in valid_times),
                "end_absolute_seconds": max(word["end_seconds"] for word in valid_times),
                "matched_word_count": int(matched_count),
                "reference_word_count": len(words),
                "match_coverage": round(matched_count / max(1, len(words)), 4),
            })

    chorus_lines = [line for line in focus_lines if line["section"] == "Chorus 2"]
    if not chorus_lines or not chorus_lines[0]["words"]:
        raise ValueError("No aligned Chorus 2 hook found in the chosen candidate.")
    chorus_hook = chorus_lines[0]["words"]
    hook_words = [word for word in chorus_hook if word["start_seconds"] is not None]
    if not hook_words or hook_words[0]["text"].strip('“”\"').lower() != "could":
        raise ValueError("The first Chorus 2 hook is not aligned to 'Could you just'; revise the lyric/music before POC.")

    critical_phrases = {
        "Could you just": ["could", "you", "just"],
        "Since you're saving time": ["since", "you're", "saving", "time"],
    }
    for phrase, tokens in critical_phrases.items():
        matching_lines = [
            lyric_line for lyric_line in lyric_lines
            if lyric_line["section"] == "Chorus 2"
            and any(
                lyric_line["tokens"][offset:offset + len(tokens)] == tokens
                for offset in range(len(lyric_line["tokens"]) - len(tokens) + 1)
            )
        ]
        if not matching_lines:
            raise ValueError(f"Critical role-reversal phrase is missing from the source lyric: {phrase}")
        matching_indices = []
        for lyric_line in matching_lines:
            for offset in range(len(lyric_line["tokens"]) - len(tokens) + 1):
                if lyric_line["tokens"][offset:offset + len(tokens)] == tokens:
                    matching_indices.extend(lyric_line["reference_indices"][offset:offset + len(tokens)])
        if any(timing_by_reference.get(index, {}).get("operation") != "match" for index in matching_indices):
            raise ValueError(f"The generated song does not clearly sing the full POC hook phrase: {phrase}")

    for lyric_line in lyric_lines:
        if lyric_line["section"] not in ("Pre-Chorus 2", "Chorus 2"):
            continue
        missing = [
            lyric_line["tokens"][offset]
            for offset, index in enumerate(lyric_line["reference_indices"])
            if timing_by_reference.get(index, {}).get("operation") != "match"
        ]
        if missing:
            raise ValueError(
                "The 20–25 second passage has words without a clean exact Whisper alignment; "
                "do not render invented karaoke timing. Unmatched: " + ", ".join(missing)
            )

    acoustic = candidate["acoustic_analysis"]
    beat_times = [float(x) for x in acoustic["beat_times_seconds"]]
    hook_time = float(hook_words[0]["start_seconds"])
    chorus_beat_index = min(range(len(beat_times)), key=lambda idx: abs(beat_times[idx] - hook_time))
    clip_start_index = chorus_beat_index - 16
    clip_end_index = chorus_beat_index + 32
    if clip_start_index < 0 or clip_end_index >= len(beat_times):
        raise ValueError("Measured beat grid does not cover the full 4+8 bar POC passage.")
    clip_start = beat_times[clip_start_index]
    clip_end = beat_times[clip_end_index]
    duration = clip_end - clip_start
    if not 20.0 <= duration <= 25.0:
        raise ValueError(f"Measured 12-bar passage is outside the 20–25 second target: {duration:.3f}s")

    bars = [
        round(beat_times[clip_start_index + beats] - clip_start, 4)
        for beats in range(0, 49, 4)
    ]
    lines: list[dict] = []
    for line in focus_lines:
        words = []
        for word in line["words"]:
            if word["start_seconds"] is None:
                words.append({
                    "text": word["text"],
                    "start_seconds": -1.0,
                    "end_seconds": -1.0,
                    "alignment": "missing",
                })
                continue
            if clip_start <= word["start_seconds"] <= clip_end:
                words.append({
                    "text": word["text"],
                    "start_seconds": round(word["start_seconds"] - clip_start, 4),
                    "end_seconds": round(min(word["end_seconds"], clip_end) - clip_start, 4),
                    "alignment": word["alignment"],
                    "recognized": word["recognized"],
                    "asr_probability": word["asr_probability"],
                })
        timed = [word for word in words if word["start_seconds"] >= 0]
        if timed:
            lines.append({
                "section": line["section"],
                "text": line["text"],
                "words": words,
                "start_seconds": min(word["start_seconds"] for word in timed),
                "end_seconds": max(word["end_seconds"] for word in timed),
                "match_coverage": line["match_coverage"],
            })

    return {
        "status": "technical_timeline_pending_subjective_song_review",
        "selected_song_status": "provisional_for_poc_only",
        "subjective_audio_listening": report.get("subjective_audio_listening"),
        "candidate_id": candidate_id,
        "song_path": candidate["output_path"],
        "asr_model": candidate["asr_model"],
        "lyric_wer": candidate["lyric_fit"]["word_error_rate"],
        "detected_bpm": acoustic["detected_bpm"],
        "estimated_key": acoustic["key_estimate"]["key"],
        "sample_rate_hz": acoustic["sample_rate_hz"],
        "clip_start_audio_seconds": round(clip_start, 4),
        "clip_end_audio_seconds": round(clip_end, 4),
        "duration_seconds": round(duration, 4),
        "chorus2_start_seconds": round(beat_times[chorus_beat_index] - clip_start, 4),
        "chorus2_middle_seconds": round(beat_times[chorus_beat_index + 16] - clip_start, 4),
        "bar_starts_seconds": bars,
        "beat_times_seconds": [round(value - clip_start, 4) for value in beat_times if clip_start <= value < clip_end],
        "lines": lines,
        "selection_evidence": {
            "full_song_wer": candidate["lyric_fit"]["word_error_rate"],
            "chorus1_chorus2_chroma_similarity": acoustic["first_half_chorus_chroma_similarity"],
            "section_energy_contrasts_db": acoustic["energy_contrasts_db"],
            "melody_memorability": "BLOCKED: the assistant runtime cannot receive audio input; a timed audio audition is still required.",
            "dry_humour_delivery": "BLOCKED: the assistant runtime cannot receive audio input; no delivery pass is claimed.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build actual beat and lyric timing for the 12-bar POC.")
    parser.add_argument("--candidate", required=True, help="A candidate asset id present in song_candidate_review.json")
    args = parser.parse_args()
    timeline = build(args.candidate)
    OUTPUT.write_text(json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {OUTPUT.relative_to(PROJECT)}: {timeline['clip_start_audio_seconds']:.3f}–"
        f"{timeline['clip_end_audio_seconds']:.3f}s ({timeline['duration_seconds']:.3f}s; "
        f"{timeline['detected_bpm']:.2f} BPM; WER {timeline['lyric_wer']:.3f}).",
        flush=True,
    )


if __name__ == "__main__":
    main()
