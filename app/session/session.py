"""Сессия ученика и папка с её файлами.

Папка сессии: meta.json (кто, когда, статус), signal.npz и events.json после
завершения, а во время записи — signal.part и events.jsonl. Статус
recording у сессии, которую никто не завершил, значит, что программа упала:
при следующем запуске такая сессия собирается и помечается interrupted.
"""
from __future__ import annotations

import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from app.device.link import DeviceLink
from app.session.recorder import SessionRecorder, recover
from app.storage import atomic_write_json, read_json

LANGS = ("ru", "kk")
GRADES = (8, 9, 10, 11)


@dataclass(frozen=True)
class Student:
    name: str
    grade: int
    lang: str

    @staticmethod
    def parse(raw: dict) -> "Student":
        name = " ".join(str(raw.get("name", "")).split())
        if not name or len(name) > 80:
            raise ValueError("имя ученика: от 1 до 80 символов")
        try:
            grade = int(raw.get("grade"))
        except (TypeError, ValueError):
            raise ValueError("класс: 8, 9, 10 или 11") from None
        if grade not in GRADES:
            raise ValueError("класс: 8, 9, 10 или 11")
        lang = str(raw.get("lang", ""))
        if lang not in LANGS:
            raise ValueError("язык: ru или kk")
        return Student(name=name, grade=grade, lang=lang)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "local"


class Session:
    def __init__(self, folder: Path, meta: dict, recorder: SessionRecorder,
                 link: DeviceLink | None) -> None:
        self.folder = folder
        self.meta = meta
        self.recorder = recorder
        self._link = link
        self._lock = threading.Lock()
        if link is not None:
            link.add_listener(recorder.on_chunk)

    @property
    def id(self) -> str:
        return self.meta["id"]

    @property
    def active(self) -> bool:
        return self.meta["status"] == "recording"

    def mark(self, kind: str, payload: dict | None = None) -> dict:
        if not self.active:
            raise RuntimeError("сессия уже закрыта")
        return self.recorder.mark(kind, payload)

    def _close(self, status: str, extra: dict) -> dict:
        with self._lock:
            if not self.active:
                return self.meta
            if self._link is not None:
                self._link.remove_listener(self.recorder.on_chunk)
            self.recorder.mark("session_end", {"status": status})
            self.recorder.finish()
            self.meta.update(status=status, finished_at=datetime.now().isoformat(timespec="seconds"),
                             samples=self.recorder.samples, **extra)
            atomic_write_json(self.folder / "meta.json", self.meta)
            return self.meta

    def finish(self) -> dict:
        return self._close("finished", {})

    def abort(self, reason: str) -> dict:
        return self._close("aborted", {"abort_reason": reason[:200]})


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def start(self, student: Student, manager: str, link: DeviceLink | None,
              plan: list[str], app_version: str, now: datetime | None = None) -> Session:
        now = now or datetime.now()
        base = f"{_slug(manager)}-{now:%y%m%d-%H%M%S}"
        session_id, n = base, 1
        while (self.root / session_id).exists():
            n += 1
            session_id = f"{base}-{n}"
        folder = self.root / session_id
        fs = link.fs if link is not None and link.streaming else None
        recorder = SessionRecorder(folder, fs)
        snapshot = link.snapshot() if link is not None else {}
        meta = {
            "id": session_id,
            "student": asdict(student),
            "manager": manager,
            "with_headband": fs is not None,
            "device": snapshot.get("name") or None,
            "battery": snapshot.get("battery"),
            "fs": fs,
            "plan": plan,
            "app_version": app_version,
            "started_at": now.isoformat(timespec="seconds"),
            "status": "recording",
        }
        atomic_write_json(folder / "meta.json", meta)
        session = Session(folder, meta, recorder, link if fs is not None else None)
        session.mark("session_start", {"lang": student.lang, "with_headband": fs is not None})
        return session

    def list(self) -> list[dict]:
        metas = [read_json(p / "meta.json") for p in self.root.iterdir() if p.is_dir()]
        return sorted((m for m in metas if m), key=lambda m: m.get("started_at", ""), reverse=True)

    def recover_interrupted(self) -> list[str]:
        """Собирает сессии, оборванные сбоем программы."""
        recovered = []
        for meta in self.list():
            if meta.get("status") != "recording":
                continue
            folder = self.root / meta["id"]
            recover(folder, meta.get("fs"))
            meta["status"] = "interrupted"
            atomic_write_json(folder / "meta.json", meta)
            recovered.append(meta["id"])
        return recovered
