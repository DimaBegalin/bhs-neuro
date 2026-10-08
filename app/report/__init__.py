"""Отчёты: саммари, PDF для родителя, PDF для профориентолога, HTML для облака,
дорожная карта BHS для 8–10 класса."""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path

from app.report.html import render_parent_html
from app.report.model import build_model
from app.report.pdf import render_manager, render_parent
from app.report.roadmap import ROADMAP_PDF, make_roadmap
from app.storage import atomic_write_bytes, atomic_write_json, read_json

PARENT_PDF = "отчёт-родителю.pdf"
MANAGER_PDF = "отчёт-профориентологу.pdf"
PARENT_HTML = "report.html"
COMMENT = "comment.json"
MAX_COMMENT = 3000
log = logging.getLogger(__name__)


def load_comment(folder: Path) -> dict | None:
    comment = read_json(Path(folder) / COMMENT)
    return comment if comment and comment.get("text") else None


def save_comment(folder: Path, text: str, author: str = "") -> dict | None:
    """Комментарий профориентолога. Пустой текст удаляет комментарий."""
    text = str(text or "").strip()[:MAX_COMMENT]
    path = Path(folder) / COMMENT
    if not text:
        if path.exists():
            path.unlink()
        return None
    comment = {"text": text, "author": str(author or "").strip()[:120],
               "updated_at": datetime.now().isoformat(timespec="seconds")}
    atomic_write_json(path, comment)
    return comment


def _roadmap(folder: Path, model: dict) -> None:
    try:  # печатает браузер: его сбой не должен ломать основные отчёты
        make_roadmap(folder, model)
    except Exception:
        log.exception("дорожная карта %s", folder.name)


def make_reports(folder: Path, result: dict | None = None, roadmap_wait: bool = False) -> dict:
    """Пишет в папку сессии PDF для родителя (с комментарием, если он есть),
    PDF для профориентолога и HTML для облака. Возвращает модель."""
    folder = Path(folder)
    meta = read_json(folder / "meta.json", {})
    result = result or read_json(folder / "result.json")
    model = build_model(result, meta)
    model["comment"] = load_comment(folder)
    render_parent(model, folder / PARENT_PDF)
    render_manager(model, folder / MANAGER_PDF)
    atomic_write_bytes(folder / PARENT_HTML, render_parent_html(model).encode("utf-8"))
    if roadmap_wait:
        _roadmap(folder, model)
    else:  # Chrome печатает секунды, а на первом запуске дольше: завершение теста его не ждёт
        threading.Thread(target=_roadmap, args=(folder, model), name="roadmap", daemon=True).start()
    return model
