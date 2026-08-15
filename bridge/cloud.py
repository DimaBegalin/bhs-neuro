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

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(APP_DIR, ".env")
SESSION_PATH = os.path.join(APP_DIR, ".manager_session.json")
TABLE = "neuro_visits"
TIMEOUT_S = 20
# токен живёт час, обновляем заранее: визит не должен упереться в протухший
REFRESH_MARGIN_S = 300


def _env() -> dict:
    values = {}
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def settings() -> tuple[str, str]:
    env = _env()
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
        if not os.path.exists(SESSION_PATH):
            return
        try:
            with open(SESSION_PATH, encoding="utf-8") as fh:
                self.data = json.load(fh)
        except Exception:
            self.data = {}

    def _save(self) -> None:
        with open(SESSION_PATH, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False)
        # в файле лежит доступ к записям менеджера, читать его посторонним незачем
        os.chmod(SESSION_PATH, 0o600)

    def clear(self) -> None:
        self.data = {}
        if os.path.exists(SESSION_PATH):
            os.remove(SESSION_PATH)

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


def push_visit(session: ManagerSession, meta: dict, profile: dict,
               report: dict, report_html_path: str) -> str:
    """Кладёт визит в облако под учётной записью менеджера."""
    url, key = settings()
    if not url or not key:
        return "облако не настроено"
    if not session.snapshot()["signed_in"]:
        return "менеджер не вошёл, визит остался на ноутбуке"

    token = session.token()
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
    headers = {"apikey": key, "Authorization": "Bearer " + token,
               "Content-Type": "application/json",
               # повторная выгрузка того же визита обновляет запись,
               # а не спотыкается о занятый ключ
               "Prefer": "resolution=merge-duplicates,return=minimal"}
    _request(f"{url}/rest/v1/{TABLE}?on_conflict=session_id", "POST", [row], headers)
    return "визит в облаке"
