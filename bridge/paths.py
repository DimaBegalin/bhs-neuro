# -*- coding: utf-8 -*-
"""Пути программы в исходниках и в упакованном приложении.

PyInstaller распаковывает ``--onefile`` во временную папку. Хранить рядом с
``__file__`` записи детей, отчёты и вход менеджера в таком режиме нельзя:
папка исчезает после завершения процесса. Поэтому упакованная программа
пишет изменяемые данные в локальную папку пользователя, а ресурсы читает из
образа приложения.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "BHS Neuro"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))


def _user_root() -> Path:
    overridden = os.environ.get("BHS_HOME")
    if overridden:
        return Path(overridden).expanduser().resolve()
    if not FROZEN:
        return PROJECT_ROOT
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(base) / APP_NAME if base else Path.home() / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / "bhs-neuro"


APP_DIR = _user_root()
DATA_DIR = APP_DIR / "data"
REPORTS_DIR = (APP_DIR / "reports" if FROZEN
               else PROJECT_ROOT / "web" / "reports")
LOGS_DIR = APP_DIR / "logs"
OUTBOX_DIR = APP_DIR / "outbox"
SESSION_PATH = APP_DIR / ".manager_session.json"
ENV_PATH = APP_DIR / ".env"
EMBEDDED_ENV_PATH = BUNDLE_ROOT / "bhs-defaults.env"
PUBLIC_DIR = BUNDLE_ROOT / "public"


def ensure_runtime_dirs() -> None:
    for path in (APP_DIR, DATA_DIR, REPORTS_DIR, LOGS_DIR, OUTBOX_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def settings() -> dict[str, str]:
    """Настройки по слоям: встроенные, рядом с EXE, пользовательские, env."""
    values: dict[str, str] = {}
    candidates = [EMBEDDED_ENV_PATH]
    if FROZEN:
        candidates.append(Path(sys.executable).resolve().parent / ".env")
    else:
        candidates.append(PROJECT_ROOT / ".env")
    candidates.append(ENV_PATH)
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        values.update(_read_env(path))
    for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "TEST_URL",
                "OPERATOR", "OPERATOR_NAME", "HEADBAND_START_COMMAND"):
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def data_dir(requested: str | os.PathLike[str] | None = None) -> Path:
    """Каталог сессий.

    В готовом EXE путь со страницы намеренно игнорируется: удалённый сайт не
    должен выбирать произвольную папку на компьютере. В режиме разработки
    явный путь оставлен для тестов и инструментов.
    """
    if FROZEN or not requested or str(requested) == "data":
        return DATA_DIR
    return Path(requested)
