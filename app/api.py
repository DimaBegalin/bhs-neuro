"""Методы, которые окно вызывает через мост pywebview (window.pywebview.api).

pywebview зовёт каждый метод в своём потоке и передаёт в JS только то, что
сериализуется в JSON. Поэтому все методы возвращают словари, а ошибки
ввода — словарь {"error": текст}, а не исключение.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import asdict

import random
import sys

from app import __version__, content
from app.battery.plan import plan_for
from app.report import MANAGER_PDF, PARENT_PDF, load_comment, make_reports, save_comment
from app.report.model import build_model
from app.storage import read_json
from app.session.result import build_result
from app.device.link import DeviceLink
from app.session.session import Session, SessionStore, Student

log = logging.getLogger(__name__)


class Api:
    def __init__(self, link: DeviceLink, store: SessionStore, manager: str = "",
                 dev_controls: dict | None = None, fast: bool = False,
                 on_finished=None, auth=None, syncer=None) -> None:
        self._link = link
        self._store = store
        self._manager = manager
        self._session: Session | None = None
        self._lock = threading.Lock()
        # только для разработки: например, «закрыть глаза» у имитатора
        self._dev = dev_controls or {}
        self._fast = fast
        self._on_finished = on_finished  # например, поставить визит в очередь облака
        self._auth = auth
        self._syncer = syncer

    def app_info(self) -> dict:
        return {"version": __version__, "manager": self._manager,
                "dev": sorted(self._dev), "mac": sys.platform == "darwin"}

    # ободок -----------------------------------------------------------------

    def device_state(self) -> dict:
        return self._link.snapshot()

    def device_connect(self) -> dict:
        self._link.connect()
        return self._link.snapshot()

    def device_reconnect(self) -> dict:
        if self._session is not None and self._session.active:
            return {"error": "нельзя переподключать ободок во время сессии"}
        self._link.reconnect()
        return self._link.snapshot()

    # сессия -----------------------------------------------------------------

    def session_start(self, raw: dict) -> dict:
        try:
            student = Student.parse(raw or {})
        except ValueError as error:
            return {"error": str(error)}
        with_headband = bool(raw.get("with_headband"))
        with self._lock:
            if self._session is not None and self._session.active:
                return {"error": "предыдущая сессия ещё не закрыта"}
            if with_headband and not self._link.streaming:
                return {"error": "ободок не передаёт сигнал: подключите его или выберите «без ободка»"}
            modules = plan_for(with_headband, self._fast)
            manager = self._manager
            if self._auth is not None and self._auth.state().get("logged_in"):
                manager = self._auth.state().get("name") or manager
            self._session = self._store.start(
                student, manager, self._link if with_headband else None,
                [m.id for m in modules], __version__)
        return {"id": self._session.id,
                "with_headband": self._session.meta["with_headband"],
                "plan": [asdict(m) for m in modules]}

    def session_mark(self, kind: str, payload: dict | None = None) -> dict:
        session = self._session
        if session is None or not session.active:
            return {"error": "нет активной сессии"}
        if not isinstance(kind, str) or not kind or len(kind) > 64:
            return {"error": "неверный тип события"}
        event = session.mark(kind, payload if isinstance(payload, dict) else {})
        hook = self._dev.get(f"on:{kind}")
        if hook is not None:
            hook(payload or {})
        return {"ok": True, "sample": event["sample"]}

    def session_content(self) -> dict:
        """Содержимое батареи на языке ученика в порядке этой сессии.

        Порядок утверждений и карточек перемешивается по id сессии: у разных
        учеников он разный, у одной сессии — воспроизводимый.
        """
        session = self._session
        if session is None:
            return {"error": "нет активной сессии"}
        data = content.for_window(session.meta["student"]["lang"])
        rng = random.Random(session.id)
        rng.shuffle(data["interests"]["items"])
        rng.shuffle(data["cards"])
        session.mark("content_order", {
            "interests": [i["id"] for i in data["interests"]["items"]],
            "cards": [c["id"] for c in data["cards"]],
        })
        return data

    def session_finish(self) -> dict:
        session = self._session
        if session is None:
            return {"error": "нет активной сессии"}
        meta = session.finish()
        summary = {"id": meta["id"], "status": meta["status"], "samples": meta.get("samples"),
                   "fs": meta.get("fs"), "result": None}
        try:
            summary["result"] = build_result(session.folder)
            model = make_reports(session.folder, summary["result"])
            summary["report"] = {"summary": model["summary"], "clusters": model["clusters"]}
        except Exception as error:  # итог пересчитывается из сырых файлов позже
            log.exception("расчёт итога %s", meta["id"])
            summary["result_error"] = str(error)
        if self._on_finished is not None:
            self._on_finished(session.folder)
        return summary

    def _folder(self, session_id: str):
        folder = self._store.root / str(session_id)
        if not folder.is_dir() or folder.parent != self._store.root:
            return None
        return folder

    def open_report(self, session_id: str, kind: str = "parent") -> dict:
        """Открыть PDF системной программой. Нет отчёта — пересобрать из файлов сессии."""
        folder = self._folder(session_id)
        if folder is None:
            return {"error": "нет такой сессии"}
        path = folder / (PARENT_PDF if kind == "parent" else MANAGER_PDF)
        if not path.exists():
            try:
                build_result(folder)
                make_reports(folder)
            except Exception as error:
                return {"error": f"отчёт не собран: {error}"}
        _open_path(path)
        return {"ok": True}

    def session_view(self, session_id: str) -> dict:
        """Итог прошлой сессии для экрана: саммари, направления, комментарий."""
        folder = self._folder(session_id)
        if folder is None:
            return {"error": "нет такой сессии"}
        meta = read_json(folder / "meta.json", {})
        result = read_json(folder / "result.json")
        try:
            if result is None:
                result = build_result(folder)
                make_reports(folder, result)
            model = build_model(result, meta)
        except Exception as error:
            return {"id": session_id, "meta": meta, "result": None, "result_error": str(error)}
        return {"id": session_id, "meta": meta, "status": meta.get("status"), "result": result,
                "report": {"summary": model["summary"], "clusters": model["clusters"]},
                "comment": load_comment(folder)}

    def session_comment(self, session_id: str, text: str) -> dict:
        """Сохранить комментарий профориентолога и пересобрать PDF для родителя."""
        folder = self._folder(session_id)
        if folder is None:
            return {"error": "нет такой сессии"}
        author = self._manager
        if self._auth is not None and self._auth.state().get("logged_in"):
            author = self._auth.state().get("name") or author
        try:
            comment = save_comment(folder, text, author)
            make_reports(folder)
        except Exception as error:
            log.exception("комментарий %s", session_id)
            return {"error": f"PDF не собран: {error}"}
        if self._on_finished is not None:  # обновлённый отчёт уходит и в облако
            self._on_finished(folder)
        _open_path(folder / PARENT_PDF)
        return {"ok": True, "comment": comment}

    def show_folder(self, session_id: str) -> dict:
        folder = self._folder(session_id)
        if folder is None:
            return {"error": "нет такой сессии"}
        _open_path(folder)
        return {"ok": True}

    def session_abort(self, reason: str = "") -> dict:
        session = self._session
        if session is None or not session.active:
            return {"ok": True}
        session.abort(reason or "прервано менеджером")
        return {"ok": True}

    def sessions_list(self) -> list[dict]:
        return self._store.list()

    # менеджер и облако ------------------------------------------------------

    def manager_state(self) -> dict:
        if self._auth is None:
            return {"logged_in": False, "cloud": False}
        return {**self._auth.state(), "cloud": True}

    def manager_login(self, email: str, password: str) -> dict:
        if self._auth is None:
            return {"error": "облако выключено"}
        from app.cloud.auth import AuthError
        try:
            self._auth.login(str(email), str(password))
        except AuthError as error:
            return {"error": str(error)}
        if self._syncer is not None:
            threading.Thread(target=self._syncer.flush, daemon=True).start()
        return self.manager_state()

    def manager_logout(self) -> dict:
        if self._auth is not None:
            self._auth.logout()
        return self.manager_state()

    def sync_status(self) -> dict:
        return self._syncer.status() if self._syncer is not None else {"pending": 0, "configured": False}

    def sync_now(self) -> dict:
        if self._syncer is None:
            return {"error": "облако выключено"}
        return {**self._syncer.flush(), **self._syncer.status()}

    def update_check(self) -> dict | None:
        from app.cloud.updates import check
        return check()

    def open_url(self, url: str) -> dict:
        if not str(url).startswith("https://"):
            return {"error": "только https-ссылки"}
        import webbrowser
        webbrowser.open(url)
        return {"ok": True}

    def dev(self, name: str, *args) -> dict:
        action = self._dev.get(name)
        if action is None:
            return {"error": f"нет действия {name}"}
        action(*args)
        return {"ok": True}


def _open_path(path) -> None:
    import os
    import subprocess
    import sys
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606 — путь из папки сессии
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
