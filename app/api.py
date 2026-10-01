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

from app import __version__, content
from app.battery.plan import plan_for
from app.session.result import build_result
from app.device.link import DeviceLink
from app.session.session import Session, SessionStore, Student

log = logging.getLogger(__name__)


class Api:
    def __init__(self, link: DeviceLink, store: SessionStore, manager: str = "",
                 dev_controls: dict | None = None, fast: bool = False) -> None:
        self._link = link
        self._store = store
        self._manager = manager
        self._session: Session | None = None
        self._lock = threading.Lock()
        # только для разработки: например, «закрыть глаза» у имитатора
        self._dev = dev_controls or {}
        self._fast = fast

    def app_info(self) -> dict:
        return {"version": __version__, "manager": self._manager,
                "dev": sorted(self._dev)}

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
            self._session = self._store.start(
                student, self._manager, self._link if with_headband else None,
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
        except Exception as error:  # итог пересчитывается из сырых файлов позже
            log.exception("расчёт итога %s", meta["id"])
            summary["result_error"] = str(error)
        return summary

    def session_abort(self, reason: str = "") -> dict:
        session = self._session
        if session is None or not session.active:
            return {"ok": True}
        session.abort(reason or "прервано менеджером")
        return {"ok": True}

    def sessions_list(self) -> list[dict]:
        return self._store.list()

    def dev(self, name: str, *args) -> dict:
        action = self._dev.get(name)
        if action is None:
            return {"error": f"нет действия {name}"}
        action(*args)
        return {"ok": True}
