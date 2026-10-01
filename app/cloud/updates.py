"""Есть ли новая версия: файл profor-version.json на сайте (ADR 0005).

Установка ручная: приложение только показывает плашку со ссылкой.
"""
from __future__ import annotations

import re

from app import __version__
from app.cloud.http import HttpError, Offline, request
from app.settings import settings


def parse(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version.split("-")[0]))


def check(current: str = __version__) -> dict | None:
    try:
        manifest = request(f"{settings()['SITE_URL']}/profor-version.json", timeout=4.0)
    except (Offline, HttpError, ValueError):
        return None
    if not isinstance(manifest, dict) or "version" not in manifest:
        return None
    if parse(manifest["version"]) > parse(current):
        return {"version": manifest["version"], "url": manifest.get("url", ""),
                "notes": manifest.get("notes", "")}
    return None
