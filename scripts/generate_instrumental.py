"""Generate one manifest-defined instrumental cue through the installed local ACE-Step API."""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8001/"
PROVIDER = "ACE-Step 1.5 local REST API / acestep-v15-turbo"


def request_json(path: str, payload: dict) -> dict:
    req = Request(urljoin(BASE, path), data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


def data_of(response: dict):
    if response.get("error"):
        raise RuntimeError(response["error"])
    return response["data"]


def download_audio(result: dict, output: Path) -> None:
    url = result.get("url")
    if not url:
        file_value = result.get("file", "")
        if file_value.startswith(("http://", "https://", "/")):
            url = file_value
        else:
            url = "v1/audio?" + urlencode({"path": file_value})
    with urlopen(Request(urljoin(BASE, url)), timeout=180) as response, output.open("wb") as stream:
        while chunk := response.read(1024 * 1024):
            stream.write(chunk)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", choices=("guoqing", "zhongqiu"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "projects" / args.project
    manifest_path = root / "asset_manifest.json"
    if not manifest_path.exists():
        manifest_path = root / "assets" / "asset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    asset_id = f"{args.project}_score"
    asset = next(a for a in manifest["assets"] if a["id"] in {asset_id, "score"})
    asset_id = asset["id"]
    out = root / asset["output_path"]
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_type": "text2music", "model": "acestep-v15-turbo",
        "prompt": asset["prompt"], "lyrics": "", "vocal_language": "en",
        "audio_format": "wav", "audio_duration": float(asset["duration_seconds"]),
        "bpm": int(asset["tempo_bpm"]), "key_scale": asset["key"], "time_signature": "4",
        "thinking": False, "use_format": False, "use_cot_caption": False,
        "use_cot_language": False, "batch_size": 1, "inference_steps": 8,
        "use_random_seed": False, "seed": int(asset["seed"]),
    }
    queued = data_of(request_json("release_task", payload))
    task_id = queued.get("task_id")
    if not task_id:
        raise RuntimeError(f"Local ACE-Step returned no task id: {queued}")
    asset["provider_used"] = PROVIDER
    asset["status"] = "generation_queued"
    asset["generation_task_id"] = task_id
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Queued {asset_id}: {task_id}", flush=True)
    while True:
        time.sleep(4)
        tasks = data_of(request_json("query_result", {"task_id_list": [task_id]}))
        if not tasks:
            continue
        task = tasks[0]
        status = int(task.get("status", 0))
        print(f"{asset_id}: status={status}", flush=True)
        if status == 1:
            import json as json_module
            result = task.get("result", "[]")
            files = json_module.loads(result) if isinstance(result, str) else result
            if not files:
                raise RuntimeError("ACE-Step returned an empty audio list")
            download_audio(files[0], out)
            asset["status"] = "generated_pending_review"
            asset["generation_metadata"] = {"task_id": task_id, "seed": asset["seed"], "bpm": asset["tempo_bpm"], "duration_seconds": asset["duration_seconds"]}
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"Saved {out} ({out.stat().st_size} bytes)")
            break
        if status == 2:
            asset["status"] = "generation_failed_after_local_call"
            asset["generation_error"] = str(task.get("result"))
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            raise RuntimeError(f"Local generation failed: {task.get('result')}")


if __name__ == "__main__":
    main()
