"""Настройки облака: адрес Supabase, публичный ключ, сайт с версией.

Порядок: переменные окружения, затем файл, вшитый в сборку
(bhs-defaults.env, пишет tools/build_windows.py из секретов CI), затем
.env в репозитории для разработки. Публичный (anon) ключ не секрет:
доступ к данным держат правила базы (upload/schema.sql).
"""
from __future__ import annotations

import os
from functools import lru_cache

from app.storage import BUNDLE_ROOT, PROJECT_ROOT

KEYS = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SITE_URL")
DEFAULT_SITE = "https://bhs-neuro.vercel.app"


def _read(path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    except OSError:
        pass
    return values


@lru_cache(maxsize=1)
def settings() -> dict[str, str]:
    files = [_read(BUNDLE_ROOT / "bhs-defaults.env"), _read(PROJECT_ROOT / ".env")]
    result = {}
    for key in KEYS:
        value = os.environ.get(key, "")
        for source in files:
            value = value or source.get(key, "")
        result[key] = value.rstrip("/")
    result["SITE_URL"] = result["SITE_URL"] or DEFAULT_SITE
    return result


def cloud_configured() -> bool:
    s = settings()
    return bool(s["SUPABASE_URL"] and s["SUPABASE_ANON_KEY"])
