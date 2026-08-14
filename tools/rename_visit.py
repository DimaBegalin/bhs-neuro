# -*- coding: utf-8 -*-
"""Поправка анкеты уже прошедшего визита: локально и на сайте.

Боевой урок 13.08: анкета не доезжала до моста, и визиты легли в облако
как «без имени». Записи при этом полные, пропадать им незачем. Инструмент
вписывает имя в meta.json, пересобирает страницу отчёта с подписью
и выгружает карточку с отчётом в облако заново: облако на повторную
выгрузку отвечает адресным обновлением, дубля не будет.

Запуск из корня проекта:
  ./.venv/bin/python tools/rename_visit.py visit-172652 --name "Имя Фамилия" \
      --grade "9 класс" [--track kk] [--dry-run]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from report.build_html import build as build_report_page
from upload.cloud_push import push_visit

DATA = "data"
REPORTS = "web/reports"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    parser.add_argument("--name", default=None, help="имя и фамилия")
    parser.add_argument("--grade", default=None, help="класс, например «9 класс»")
    parser.add_argument("--track", default=None, choices=("ru", "kk"))
    parser.add_argument("--dry-run", action="store_true",
                        help="показать, что изменится, ничего не трогая")
    args = parser.parse_args()
    sid = args.session_id

    meta_path = os.path.join(DATA, f"{sid}.meta.json")
    profile_path = os.path.join(DATA, f"{sid}.profile.json")
    report_path = os.path.join(DATA, f"{sid}.report.json")
    for path in (meta_path, profile_path, report_path):
        if not os.path.exists(path):
            sys.exit(f"нет файла {path}: этот визит так не поправить. "
                     "Без профиля и отчёта выгружать в облако нечего.")

    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    before = dict(meta)
    if args.name is not None:
        meta["student_name"] = args.name.strip()[:80]
    if args.grade is not None:
        meta["grade"] = args.grade.strip()[:16]
    if args.track is not None:
        meta["track"] = args.track

    print(f"анкета {sid}:")
    for key in ("student_name", "grade", "track"):
        old, new = before.get(key) or "—", meta.get(key) or "—"
        mark = "->" if old != new else "  "
        print(f"  {key:14} {old!r:24} {mark} {new!r}")
    if args.dry_run:
        print("проверка без записи: ничего не изменено")
        return

    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)

    with open(profile_path, encoding="utf-8") as fh:
        profile = json.load(fh)
    with open(report_path, encoding="utf-8") as fh:
        report = json.load(fh)

    html_path = os.path.join(REPORTS, f"{sid}.html")
    caption = " · ".join(part for part in
                         (meta.get("student_name"), meta.get("grade"),
                          meta.get("started_at")) if part)
    build_report_page(report, html_path, caption or sid)
    print(f"отчёт пересобран: {html_path}")
    print("облако:", push_visit(meta, profile, report, html_path))


if __name__ == "__main__":
    main()
