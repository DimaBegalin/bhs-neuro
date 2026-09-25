# -*- coding: utf-8 -*-
"""Облако визитов: вход менеджера и выгрузка от его имени.

Работаем прямыми запросами, без клиентской библиотеки: нужно ровно три
обращения, а библиотека тянет за собой версии и своё представление о сессии,
которое пришлось бы обходить.

Ключевое: визит уходит в базу под учётной записью менеджера, поэтому его
принадлежность обеспечивают правила доступа самой базы. Подмена менеджера
со страницы невозможна, даже если её переписать.

Сессия менеджера живёт дольше рабочего дня, поэтому токен обновления
хранится на диске: иначе после перезагрузки ноутбука пришлось бы входить
заново, а визиты копились бы неотправленными.
"""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from bridge.paths import (ENV_PATH as APP_ENV_PATH, OUTBOX_DIR, SESSION_PATH,
                          ensure_runtime_dirs, settings as app_settings)
from bridge.storage import atomic_write_json

TABLE = "neuro_visits"
ENV_PATH = APP_ENV_PATH  # имя оставлено для инструментов и тестовых подмен
TIMEOUT_S = 20
# токен живёт час, обновляем заранее: визит не должен упереться в протухший
REFRESH_MARGIN_S = 300


def settings() -> tuple[str, str]:
    env = app_settings()
    # Явно прочитать переменную модуля: старые инструменты подменяют этот путь.
    try:
        for raw in Path(ENV_PATH).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    except OSError:
        pass
    return env.get("SUPABASE_URL", "").rstrip("/"), env.get("SUPABASE_ANON_KEY", "")


def configured() -> bool:
    url, key = settings()
    return bool(url and key)


def _request(url: str, method: str = "GET", body=None, headers=None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers=headers or {})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


class ManagerSession:
    """Учётная запись менеджера на этом рабочем месте."""

    def __init__(self) -> None:
        self.data: dict = {}
        self._load()

    # --- хранение ---

    def _load(self) -> None:
        path = Path(SESSION_PATH)
        if not path.exists():
            return
        try:
            with path.open(encoding="utf-8") as fh:
                self.data = json.load(fh)
        except Exception:
            self.data = {}

    def _save(self) -> None:
        ensure_runtime_dirs()
        path = Path(SESSION_PATH)
        atomic_write_json(path, self.data, indent=None)
        # в файле лежит доступ к записям менеджера, читать его посторонним незачем
        try:
            os.chmod(path, 0o600)
        except OSError:
            # ACL Windows управляется системой; chmod там может быть недоступен
            pass

    def clear(self) -> None:
        self.data = {}
        path = Path(SESSION_PATH)
        if path.exists():
            path.unlink()

    # --- вход ---

    def remember(self, payload: dict) -> dict:
        """Запоминает сессию, полученную страницей входа."""
        self.data = {
            "access_token": payload.get("access_token", ""),
            "refresh_token": payload.get("refresh_token", ""),
            "manager_id": payload.get("manager_id", ""),
            "email": payload.get("email", ""),
            "expires_at": float(payload.get("expires_at") or 0),
        }
        self._save()
        return self.snapshot()

    def snapshot(self) -> dict:
        return {"signed_in": bool(self.data.get("manager_id")),
                "email": self.data.get("email", ""),
                "manager_id": self.data.get("manager_id", "")}

    def token(self) -> str:
        """Живой токен доступа. Протухший обновляется молча."""
        if not self.data.get("access_token"):
            raise RuntimeError("менеджер не вошёл в систему")
        if time.time() < float(self.data.get("expires_at") or 0) - REFRESH_MARGIN_S:
            return self.data["access_token"]
        return self._refresh()

    def _refresh(self) -> str:
        url, key = settings()
        if not url or not key:
            raise RuntimeError("облако не настроено")
        try:
            body = _request(
                f"{url}/auth/v1/token?grant_type=refresh_token", "POST",
                {"refresh_token": self.data.get("refresh_token", "")},
                {"apikey": key, "Content-Type": "application/json"})
        except urllib.error.HTTPError as error:
            # обновиться не вышло: сессия мертва, менеджеру надо войти заново
            self.clear()
            raise RuntimeError(f"вход устарел, войдите заново ({error.code})")
        self.data["access_token"] = body.get("access_token", "")
        self.data["refresh_token"] = body.get("refresh_token",
                                              self.data.get("refresh_token", ""))
        self.data["expires_at"] = time.time() + float(body.get("expires_in") or 3600)
        self._save()
        return self.data["access_token"]


def _outbox_path(session_id: str) -> Path:
    safe = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")[:64]
    return OUTBOX_DIR / f"{safe or 'visit'}.json"


def pending_count() -> int:
    try:
        return sum(1 for _ in OUTBOX_DIR.glob("*.json"))
    except OSError:
        return 0


def _send_row(session: ManagerSession, row: dict) -> None:
    url, key = settings()
    if not url or not key:
        raise RuntimeError("облако не настроено")
    token = session.token()
    # Не отправляем визит другого менеджера токеном текущего пользователя.
    # RLS всё равно отклонит такую запись, но явная проверка даёт ясную причину.
    if row.get("manager_id") != session.data.get("manager_id"):
        raise RuntimeError("визит ожидает входа своего менеджера")
    headers = {"apikey": key, "Authorization": "Bearer " + token,
               "Content-Type": "application/json",
               "Prefer": "resolution=merge-duplicates,return=minimal"}
    _request(f"{url}/rest/v1/{TABLE}?on_conflict=session_id", "POST", [row], headers)


def flush_pending(session: ManagerSession) -> dict:
    """Повторяет отложенные выгрузки. Повреждённый файл не валит очередь."""
    if not configured() or not session.snapshot()["signed_in"]:
        return {"sent": 0, "pending": pending_count()}
    sent = 0
    for path in sorted(OUTBOX_DIR.glob("*.json")):
        try:
            with path.open(encoding="utf-8") as fh:
                row = json.load(fh)
            _send_row(session, row)
            path.unlink()
            sent += 1
        except ValueError:
            # Повреждённый файл сохраняем для разбора, но не крутим вечно.
            try:
                path.replace(path.with_suffix(".invalid"))
            except OSError:
                pass
            continue
        except RuntimeError as error:
            if "своего менеджера" in str(error):
                continue
            break
        except (OSError, urllib.error.URLError):
            # Если сеть лежит, следующие файлы упадут так же. Не заставляем
            # вход менеджера ждать timeout отдельно на каждом визите.
            break
        except Exception:
            continue
    return {"sent": sent, "pending": pending_count()}


def push_visit(session: ManagerSession, meta: dict, profile: dict,
               report: dict, report_html_path: str) -> str:
    """Надёжно ставит визит в очередь и пытается отправить сразу."""
    url, key = settings()
    if not url or not key:
        return "облако не настроено"
    if not session.snapshot()["signed_in"]:
        return "менеджер не вошёл, визит остался на ноутбуке"

    pulse = report.get("pulse") or {}
    html = ""
    if report_html_path and os.path.exists(report_html_path):
        with open(report_html_path, encoding="utf-8") as fh:
            html = fh.read()

    row = {
        "session_id": meta["session_id"],
        "manager_id": session.data["manager_id"],
        "student_name": meta.get("student_name") or "без имени",
        "grade": meta.get("grade") or "",
        "track": meta.get("track") or "ru",
        "started_at": meta.get("started_at") or "",
        "has_eeg": bool(profile.get("has_eeg")),
        "iaf": profile.get("iaf"),
        "pulse_bpm": pulse.get("bpm_median"),
        "quality": profile.get("quality"),
        "domains": profile.get("domains"),
        "report_html": html,
    }
    ensure_runtime_dirs()
    queued = _outbox_path(meta["session_id"])
    atomic_write_json(queued, row)
    _send_row(session, row)
    try:
        queued.unlink()
    except FileNotFoundError:
        pass
    return "визит в облаке"
