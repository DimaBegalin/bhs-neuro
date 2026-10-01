"""Отчёты: саммари, PDF для родителя, технический отчёт для менеджера."""
from __future__ import annotations

from pathlib import Path

from app.report.html import render_parent_html
from app.report.model import build_model
from app.report.pdf import render_manager, render_parent
from app.storage import atomic_write_bytes, read_json

PARENT_PDF = "отчёт-родителю.pdf"
MANAGER_PDF = "отчёт-менеджеру.pdf"
PARENT_HTML = "report.html"


def make_reports(folder: Path, result: dict | None = None) -> dict:
    """Пишет в папку сессии PDF для родителя, технический PDF и HTML. Возвращает модель."""
    folder = Path(folder)
    meta = read_json(folder / "meta.json", {})
    result = result or read_json(folder / "result.json")
    model = build_model(result, meta)
    render_parent(model, folder / PARENT_PDF)
    render_manager(model, folder / MANAGER_PDF)
    atomic_write_bytes(folder / PARENT_HTML, render_parent_html(model).encode("utf-8"))
    return model
