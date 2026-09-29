"""Generate the new full-song candidates through the already-installed local ACE-Step service."""

from __future__ import annotations

import json
import argparse
import hashlib
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


PROJECT = Path(__file__).resolve().parent
MANIFEST_PATH = PROJECT / "assets" / "asset_manifest.json"
LYRICS_PATH = PROJECT / "assets" / "song_lyrics.txt"
BASE_URL = "http://127.0.0.1:8001/"
PROVIDER = "ACE-Step 1.5 local API / acestep-v15-turbo"


def request_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        urljoin(BASE_URL, path),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def save_manifest(manifest: dict) -> None:
    temporary = MANIFEST_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(MANIFEST_PATH)


def api_data(response: dict):
    if response.get("error"):
        raise RuntimeError(str(response["error"]))
    if "data" not in response:
        raise RuntimeError(f"Unexpected API response: {response}")
    return response["data"]


def response_is_running_past_api_timeout(task: dict) -> bool:
    """ACE-Step's legacy cache reports status 2 after one hour while work can continue."""
    if int(task.get("status", 0)) != 2:
        return False
    raw_result = task.get("result", "[]")
    try:
        result = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
    except json.JSONDecodeError:
        return False
    return bool(
        isinstance(result, list)
        and result
        and isinstance(result[0], dict)
        and int(result[0].get("status", -1)) == 0
        and result[0].get("stage")
    )


def download_audio(audio_path: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(urljoin(BASE_URL, audio_path), method="GET")
    with urlopen(request, timeout=180) as response, output_path.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def generation_lyrics(source: str) -> str:
    """Send only singable lines and generic section tags, never writer metadata."""
    result: list[str] = []
    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("TITLE:", "FORM:", "VOCAL:")):
            continue
        if line.startswith("["):
            lower = line.lower()
            if "cold open" in lower:
                result.append("[Intro]")
            elif "verse" in lower:
                result.append("[Verse]")
            elif "pre-chorus" in lower:
                result.append("[Pre-Chorus]")
            elif "chorus" in lower:
                result.append("[Chorus]")
            elif "agent break" in lower or "verification bridge" in lower:
                result.append("[Bridge]")
            elif "outro" in lower:
                result.append("[Outro]")
            continue
        result.append(line)
    return "\n".join(result)


def audio_download_url(audio_result: dict) -> str:
    """Use the API URL when supplied, or encode a server-local Windows path."""
    api_url = audio_result.get("url")
    if api_url:
        return urljoin(BASE_URL, api_url)
    file_value = audio_result.get("file", "")
    if file_value.startswith(("http://", "https://")):
        return file_value
    if file_value.startswith("/"):
        return urljoin(BASE_URL, file_value)
    return urljoin(BASE_URL, "v1/audio?" + urlencode({"path": file_value}))


def generate_one(asset: dict, lyrics: str, manifest: dict) -> None:
    output_path = PROJECT / asset["output_path"]
    bpm = int(asset["tempo_bpm"])
    key_scale = str(asset["key"])
    payload = {
        "task_type": "text2music",
        "model": "acestep-v15-turbo",
        "prompt": asset["prompt"],
        "lyrics": lyrics,
        "vocal_language": "en",
        "audio_format": "wav",
        "audio_duration": float(asset["duration_seconds"]),
        "bpm": bpm,
        "key_scale": key_scale,
        "time_signature": "4",
        "thinking": bool(asset.get("thinking", False)),
        "use_format": False,
        "use_cot_caption": False,
        "use_cot_language": False,
        "batch_size": 1,
        "inference_steps": 8,
        "use_random_seed": False,
        "seed": 610000 + bpm,
    }
    if asset.get("lm_model_path"):
        payload["lm_model_path"] = asset["lm_model_path"]
    if asset.get("lm_backend"):
        payload["lm_backend"] = asset["lm_backend"]
    task_id = asset.get("generation_task_id") if asset.get("status") == "generation_queued" else None
    if task_id:
        print(f"Resuming {asset['id']} task {task_id}", flush=True)
    else:
        print(f"Submitting {asset['id']} ({bpm} BPM, {key_scale})", flush=True)
        queued_response = request_json("release_task", payload)
        queued = api_data(queued_response)
        task_id = queued.get("task_id")
        if not task_id:
            raise RuntimeError(f"No task ID in queue response: {queued_response}")

        asset["provider_used"] = PROVIDER
        asset["status"] = "generation_queued"
        asset["generation_task_id"] = task_id
        for stale_field in ("generated_metadata", "generation_error", "last_query_status"):
            asset.pop(stale_field, None)
        save_manifest(manifest)

    poll_interval = 10
    while True:
        time.sleep(poll_interval)
        response = request_json("query_result", {"task_id_list": [task_id]})
        results = api_data(response)
        if not results:
            continue
        task = results[0]
        status = int(task.get("status", 0))
        print(f"{asset['id']}: status={status}", flush=True)
        if status == 2 and response_is_running_past_api_timeout(task):
            poll_interval = 60
            raw_result = task.get("result", "[]")
            decoded_result = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
            stage = decoded_result[0].get("stage", "unknown stage")
            timeout_note = f"ACE-Step API one-hour query timeout; backend still reports active stage: {stage}"
            if asset.get("last_query_status") != timeout_note:
                asset["status"] = "generation_queued"
                asset["last_query_status"] = timeout_note
                save_manifest(manifest)
            print(timeout_note + "; continuing to poll the same local task.", flush=True)
            continue
        if status == 2:
            asset["status"] = "generation_failed_after_local_provider_call"
            asset["generation_error"] = task.get("result", "ACE-Step generation failed")
            save_manifest(manifest)
            raise RuntimeError(f"Generation failed for {asset['id']}: {task.get('result')}")
        if status != 1:
            continue

        raw_result = task.get("result", "[]")
        files = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
        if not files:
            raise RuntimeError(f"Successful task had no audio result: {task}")
        audio_url = audio_download_url(files[0])
        if not files[0].get("file") and not files[0].get("url"):
            raise RuntimeError(f"Successful task had no audio URL: {files[0]}")
        download_audio(audio_url, output_path)
        asset["status"] = "generated_pending_audition"
        asset["generated_metadata"] = {
            "task_id": task_id,
            "seed_value": files[0].get("seed_value"),
            "metas": files[0].get("metas"),
            "vocal_language": files[0].get("vocal_language"),
            "generation_info": files[0].get("generation_info"),
            "lyrics_sha256": hashlib.sha256(lyrics.encode("utf-8")).hexdigest(),
            "lyrics_filter": "Removed TITLE/FORM/VOCAL metadata; normalized section headers to generic non-sung tags.",
        }
        save_manifest(manifest)
        print(f"Saved {asset['output_path']} ({output_path.stat().st_size} bytes)", flush=True)
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or resume full-song candidates through local ACE-Step.")
    parser.add_argument(
        "--candidate",
        action="append",
        help="Candidate asset id to generate/resume; repeat to select several. Omit to process all eligible song candidates.",
    )
    args = parser.parse_args()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    source_lyrics = LYRICS_PATH.read_text(encoding="utf-8")
    lyrics = generation_lyrics(source_lyrics)
    candidates = [asset for asset in manifest["assets"] if asset["id"].startswith("it_was_working_candidate_")]
    if args.candidate:
        requested = set(args.candidate)
        known = {asset["id"] for asset in candidates}
        unknown = requested - known
        if unknown:
            raise ValueError("Unknown song candidate id(s): " + ", ".join(sorted(unknown)))
        candidates = [asset for asset in candidates if asset["id"] in requested]
    for asset in candidates:
        if asset["status"] == "generated_pending_audition" or asset["status"].startswith("rejected_"):
            continue
        try:
            generate_one(asset, lyrics, manifest)
        except Exception as exc:
            asset["status"] = (
                "generation_failed_after_local_provider_call"
                if asset.get("provider_used")
                else "generation_failed_before_provider_call"
            )
            asset["generation_error"] = f"{type(exc).__name__}: {exc}"
            save_manifest(manifest)
            print(f"{asset['id']} failed; continuing to the next candidate: {exc}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (HTTPError, URLError, TimeoutError, ConnectionError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"Candidate generation stopped: {exc}") from exc
