# -*- coding: utf-8 -*-
"""Пуш визита в облако: карточка и готовый отчёт.

Ключи лежат в app/.env рядом с мостом и в репозиторий не попадают.
Анонимный ключ умеет только писать в эти две таблицы, читать снаружи
нельзя: чтение идёт через облачную функцию с кодом школы.
"""
import json
import os

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        ".env")
# Менеджер визита. Пока колонок operator и operator_name в облаке нет,
# слать их нельзя: неизвестная колонка роняет выгрузку целиком, и визит
# не доедет вовсе. Порядок включения: docs/ОБЛАКО_ДОРАБОТКА.md
PUSH_OPERATOR = False


def _env() -> dict:
    values = {}
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def push_visit(meta: dict, profile: dict, report: dict,
               report_html_path: str) -> str:
    env = _env()
    url, key = env.get("SUPABASE_URL"), env.get("SUPABASE_ANON_KEY")
    if not url or not key:
        return "облако не настроено: нет app/.env"
    from supabase import create_client
    client = create_client(url, key)

    pulse = (report.get("pulse") or {})
    card = {
        "session_id": meta["session_id"],
        "student_name": meta.get("student_name") or "без имени",
        "grade": meta.get("grade") or "",
        "track": meta.get("track") or "ru",
        "started_at": meta.get("started_at") or "",
        "has_eeg": bool(profile.get("has_eeg")),
        "iaf": profile.get("iaf"),
        "pulse_bpm": pulse.get("bpm_median"),
    }
    if PUSH_OPERATOR:
        card["operator"] = meta.get("operator") or ""
        card["operator_name"] = meta.get("operator_name") or ""
    def insert_or_update(table, row):
        """Вставка, при повторе адресное обновление: у anon нет права на upsert."""
        try:
            client.table(table).insert(row, returning="minimal").execute()
        except Exception as error:
            if "23505" not in str(error) and "duplicate" not in str(error).lower():
                raise
            payload = {k: v for k, v in row.items() if k != "session_id"}
            client.table(table).update(payload, returning="minimal") \
                .eq("session_id", row["session_id"]).execute()

    insert_or_update("neuro_cards", card)
    with open(report_html_path, encoding="utf-8") as fh:
        insert_or_update("neuro_reports",
                         {"session_id": meta["session_id"], "html": fh.read()})
    return "визит в облаке"
