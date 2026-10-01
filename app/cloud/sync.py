"""Отправка визитов в облако фоновой очередью (ADR 0003).

Завершённая сессия кладёт метку в outbox/. Фоновый поток раз в
FLUSH_EVERY_S пробует отправить всё, что ждёт, если менеджер вошёл и есть
сеть. Визит отправляется в таблицу версии 1 neuro_visits: веб-панель
руководителя показывает его без доработок, а отчёт открывает из
report_html. Сырая ЭЭГ в облако не уходит: только агрегаты.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from app.cloud.auth import AuthError, ManagerAuth
from app.cloud.http import HttpError, Offline, request
from app.report import PARENT_HTML
from app.settings import cloud_configured, settings
from app.storage import atomic_write_json, data_root, read_json

log = logging.getLogger(__name__)
TABLE = "neuro_visits"
FLUSH_EVERY_S = 30.0
METHODOLOGY = "2.0"


def outbox_dir() -> Path:
    path = data_root() / "outbox"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_row(folder: Path, manager_id: str) -> dict:
    meta = read_json(folder / "meta.json", {})
    result = read_json(folder / "result.json", {}) or {}
    student = meta.get("student") or {}
    monitoring = result.get("monitoring") or {}
    background = monitoring.get("background") or {}
    rec = result.get("recommendation") or {}
    html_path = folder / PARENT_HTML
    return {
        "session_id": meta["id"],
        "manager_id": manager_id,
        "student_name": student.get("name", ""),
        "grade": str(student.get("grade", "")),
        "track": student.get("lang", "ru"),
        "started_at": meta.get("started_at", ""),
        "has_eeg": bool(meta.get("with_headband")),
        "iaf": background.get("iaf_hz"),
        "pulse_bpm": None,
        "quality": {"modules": monitoring.get("modules"), "state": monitoring.get("state"),
                    "background": background, "status": meta.get("status")} if monitoring else
                   {"status": meta.get("status")},
        "domains": {
            "methodology": METHODOLOGY,
            "app_version": meta.get("app_version"),
            "interests": result.get("interests"),
            "top_clusters": rec.get("top"),
            "clusters": [{"cluster": c["cluster"], "title": c.get("title"), "score": c["score"],
                          "professions": [p["title"].get("ru") for p in c["professions"]]}
                         for c in rec.get("clusters", [])],
            "spatial": result.get("spatial"),
            "work_style": result.get("work_style"),
            "subjects": result.get("subjects"),
            "flags": result.get("flags"),
            "discrepancies": result.get("discrepancies"),
            "card_attention": (monitoring.get("cards") or {}).get("type_attention"),
        },
        "report_html": html_path.read_text(encoding="utf-8") if html_path.exists() else None,
    }


class Syncer:
    def __init__(self, auth: ManagerAuth, sessions_root: Path) -> None:
        self._auth = auth
        self._root = Path(sessions_root)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.last_error = ""
        self.last_ok_at: float | None = None
        self._thread: threading.Thread | None = None

    def enqueue(self, folder: Path) -> None:
        atomic_write_json(outbox_dir() / f"{Path(folder).name}.json", {"queued_at": time.time()})

    def pending(self) -> list[str]:
        return sorted(p.stem for p in outbox_dir().glob("*.json"))

    def flush(self) -> dict:
        """Одна попытка отправить всё из очереди. Ошибки не бросает."""
        with self._lock:
            pending = self.pending()
            if not pending:
                return {"sent": 0, "pending": 0}
            if not cloud_configured():
                self.last_error = "облако не настроено в этой сборке"
                return {"sent": 0, "pending": len(pending)}
            try:
                token, manager_id = self._auth.token()
            except AuthError as error:
                self.last_error = str(error)
                return {"sent": 0, "pending": len(pending)}
            except Offline:
                self.last_error = "нет сети"
                return {"sent": 0, "pending": len(pending)}
            s = settings()
            headers = {"apikey": s["SUPABASE_ANON_KEY"], "Authorization": f"Bearer {token}",
                       "Prefer": "resolution=merge-duplicates,return=minimal"}
            sent = 0
            for session_id in pending:
                folder = self._root / session_id
                if not (folder / "meta.json").exists():
                    (outbox_dir() / f"{session_id}.json").unlink(missing_ok=True)
                    continue
                try:
                    row = build_row(folder, manager_id)
                    request(f"{s['SUPABASE_URL']}/rest/v1/{TABLE}?on_conflict=session_id", "POST",
                            [row], headers, timeout=30.0)
                except Offline:
                    self.last_error = "нет сети"
                    break
                except HttpError as error:
                    self.last_error = f"облако не приняло визит {session_id}: {error}"[:300]
                    log.warning(self.last_error)
                    continue
                (outbox_dir() / f"{session_id}.json").unlink(missing_ok=True)
                meta = read_json(folder / "meta.json", {})
                meta["synced_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                atomic_write_json(folder / "meta.json", meta)
                sent += 1
            if sent:
                self._auth.touch_online()
                self.last_ok_at = time.time()
                if sent == len(pending):
                    self.last_error = ""
            return {"sent": sent, "pending": len(self.pending())}

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="cloud-sync", daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(FLUSH_EVERY_S if self.pending() else 5.0):
            try:
                self.flush()
            except Exception:
                log.exception("синхронизация")

    def status(self) -> dict:
        return {"pending": len(self.pending()), "last_error": self.last_error,
                "last_ok_at": self.last_ok_at, "configured": cloud_configured()}
