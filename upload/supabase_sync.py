"""Отложенная выгрузка в Supabase. Интернет в школе может лечь, очередь ждёт.

Клиент передаётся снаружи, поэтому модуль тестируется без сети и без пакета
supabase. Боевой клиент создаётся в make_client по переменным окружения.
"""
import glob
import json
import os

DEFAULT_QUEUE = "data/queue"
STORAGE_BUCKET = "neuro-raw"


def make_client():
    """Боевой клиент. Ключи берутся из окружения, в коде их нет."""
    from supabase import create_client  # импорт ленивый: тестам он не нужен
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def queue_session(profile: dict, npz_path: str, events_path: str,
                  out_dir=DEFAULT_QUEUE) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(str(out_dir), f"{profile['session_id']}.job.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"profile": profile, "npz_path": npz_path,
                   "events_path": events_path}, fh, ensure_ascii=False, indent=2)
    return path


def _rows(profile: dict) -> dict:
    session_id = profile["session_id"]
    quality = profile.get("quality", {})
    rejected = quality.get("rejected_by_block", {}) or {}
    quality_score = 1.0 - (sum(rejected.values()) / len(rejected) if rejected else 0.0)

    blocks = []
    for domain, behavior in (profile.get("behavior") or {}).items():
        neuro = (profile.get("neuro") or {}).get(domain, {})
        blocks.append({"session_id": session_id, "domain": domain,
                       "accuracy": behavior["accuracy"],
                       "median_rt_ms": behavior["median_rt_ms"],
                       "rt_sd_ms": behavior["rt_sd_ms"],
                       "erd_alpha_high": neuro.get("erd_alpha_high"),
                       "erd_alpha_low": neuro.get("erd_alpha_low"),
                       "theta_rise": neuro.get("theta_rise"),
                       "engagement": neuro.get("engagement"),
                       "attention_slope": neuro.get("attention_slope"),
                       "epochs_total": neuro.get("epochs_total"),
                       "epochs_rejected": neuro.get("epochs_rejected")})

    return {
        "neuro_sessions": [{"id": session_id, "lang": profile.get("lang", "ru"),
                            "has_eeg": profile["has_eeg"],
                            "quality_score": round(quality_score, 3)}],
        "neuro_block_metrics": blocks,
        "neuro_profiles": [{"session_id": session_id, "iaf": profile.get("iaf"),
                            "iaf_prominence": profile.get("iaf_prominence"),
                            "bands": profile.get("bands"),
                            "domains": profile.get("domains"),
                            "quality": quality,
                            "method_version": profile["method_version"]}],
    }


def _upload_raw(client, session_id: str, npz_path: str, events_path: str) -> None:
    """Кладёт сырьё в Storage, чтобы базу можно было пересчитать заново."""
    storage = client.storage.from_(STORAGE_BUCKET)
    for path, suffix in ((npz_path, "npz"), (events_path, "events.json")):
        if not os.path.exists(path):
            continue
        with open(path, "rb") as fh:
            storage.upload(f"{session_id}.{suffix}", fh.read(), {"upsert": "true"})


def flush(client, queue_dir=DEFAULT_QUEUE) -> list[str]:
    """Отправляет все задания. Неудачные остаются в очереди до следующего вызова."""
    sent: list[str] = []
    for job_path in sorted(glob.glob(os.path.join(str(queue_dir), "*.job.json"))):
        with open(job_path, encoding="utf-8") as fh:
            job = json.load(fh)
        try:
            for table, rows in _rows(job["profile"]).items():
                if rows:
                    client.table(table).upsert(rows).execute()
            _upload_raw(client, job["profile"]["session_id"],
                        job["npz_path"], job["events_path"])
        except Exception:
            continue
        sent.append(job["profile"]["session_id"])
        os.remove(job_path)
    return sent
