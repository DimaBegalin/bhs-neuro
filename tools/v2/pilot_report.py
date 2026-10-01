# -*- coding: utf-8 -*-
"""Разбор пилота. Запуск: python tools/v2/pilot_report.py ПАПКА [ПАПКА ...] > пилот.md

ПАПКА — папка sessions с ноутбука (%LOCALAPPDATA%\\BHS Profor\\sessions) или
её копия; можно указать несколько ноутбуков сразу.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.pilot import analyze, render_markdown  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    print(render_markdown(analyze([Path(p) for p in sys.argv[1:]])))
