"""Вход менеджера через Supabase Auth с работой без сети до 30 дней.

Первый вход требует интернет. Дальше приложение работает офлайн, пока с
последнего успешного обращения к облаку прошло меньше OFFLINE_DAYS:
так потерянный ноутбук сам теряет доступ. Токены лежат в папке данных
пользователя, как и в версии 1.
"""
from __future__ import annotations

import threading
import time

from app.cloud.http import HttpError, Offline, request
from app.settings import cloud_configured, settings
from app.storage import atomic_write_json, data_root, read_json

OFFLINE_DAYS = 30
REFRESH_MARGIN_S = 60


class AuthError(RuntimeError):
    pass


class ManagerAuth:
    def __init__(self, clock=time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._path = data_root() / "manager.json"

    def _load(self) -> dict | None:
        return read_json(self._path)

    def _save(self, data: dict) -> None:
        atomic_write_json(self._path, data)

    def _remember(self, payload: dict, email: str) -> dict:
        user = payload.get("user") or {}
        meta = user.get("user_metadata") or {}
        data = {
            "email": user.get("email") or email,
            "user_id": user.get("id"),
            "name": meta.get("full_name") or meta.get("name") or (user.get("email") or email).split("@")[0],
            "access_token": payload["access_token"],
            "refresh_token": payload["refresh_token"],
            "expires_at": self._clock() + float(payload.get("expires_in", 3600)),
            "last_online_at": self._clock(),
        }
        self._save(data)
        return data

    def login(self, email: str, password: str) -> dict:
        if not cloud_configured():
            raise AuthError("облако не настроено в этой сборке")
        s = settings()
        try:
            payload = request(f"{s['SUPABASE_URL']}/auth/v1/token?grant_type=password", "POST",
                              {"email": email.strip(), "password": password},
                              {"apikey": s["SUPABASE_ANON_KEY"]})
        except HttpError as error:
            if error.status in (400, 401):
                raise AuthError("неверная почта или пароль") from error
            raise AuthError(f"облако ответило ошибкой {error.status}") from error
        except Offline as error:
            raise AuthError("нет интернета: первый вход требует сеть") from error
        with self._lock:
            return self._remember(payload, email)

    def logout(self) -> None:
        with self._lock:
            if self._path.exists():
                self._path.unlink()

    def state(self) -> dict:
        data = self._load()
        if not data:
            return {"logged_in": False}
        age_days = (self._clock() - data.get("last_online_at", 0)) / 86400
        left = OFFLINE_DAYS - age_days
        return {"logged_in": left > 0, "email": data.get("email"), "name": data.get("name"),
                "user_id": data.get("user_id"), "offline_days_left": max(0, int(left)),
                "expired": left <= 0}

    def token(self) -> tuple[str, str]:
        """Действующий токен и id менеджера; при необходимости обновляет токен.

        Offline — сети нет, визиты подождут. AuthError — нужно войти заново.
        """
        with self._lock:
            data = self._load()
            if not data:
                raise AuthError("менеджер не вошёл")
            if data["expires_at"] - REFRESH_MARGIN_S > self._clock():
                return data["access_token"], data["user_id"]
            s = settings()
            try:
                payload = request(f"{s['SUPABASE_URL']}/auth/v1/token?grant_type=refresh_token", "POST",
                                  {"refresh_token": data["refresh_token"]}, {"apikey": s["SUPABASE_ANON_KEY"]})
            except HttpError as error:
                if error.status in (400, 401):
                    raise AuthError("сессия входа истекла, войдите заново") from error
                raise
            data = self._remember(payload, data["email"])
            return data["access_token"], data["user_id"]

    def touch_online(self) -> None:
        """Отметить успешное обращение к облаку (продлевает офлайн-срок)."""
        with self._lock:
            data = self._load()
            if data:
                data["last_online_at"] = self._clock()
                self._save(data)
