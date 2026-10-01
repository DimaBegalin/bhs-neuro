# -*- coding: utf-8 -*-
"""Модель отчёта: из итога сессии (result.json) в готовые тексты.

Одна модель питает экран итога, PDF для родителя, технический отчёт и
HTML, который уходит в облако. Тексты — app/report/texts.py.
"""
from __future__ import annotations

from datetime import datetime

from app.report.texts import (LEVEL, NEXT_STEPS, SPATIAL, STYLE, STYLE_STRENGTH, T, TYPES, tr)

STYLE_STRONG = 60.0
MAX_DISCREPANCIES = 2


def _type_name(kind: str, lang: str) -> str:
    return TYPES[kind].get(lang, TYPES[kind]["ru"])[0]


def _style_scores(work_style: dict | None) -> dict[str, float] | None:
    if not work_style:
        return None
    scores = {k: work_style["scores"].get(k) for k in ("E", "A", "C", "I")}
    scores["S"] = work_style.get("stability")
    return {k: v for k, v in scores.items() if v is not None}


def build_summary(result: dict, lang: str) -> list[dict]:
    """Пять пунктов «на что обратить внимание» (CONTEXT.md, Саммари)."""
    interests = result["interests"]
    rec = result["recommendation"]
    clusters = {c["cluster"]: c for c in rec["clusters"]}
    flat = interests["level"] == "flat" or not rec["top"]

    # 1. Куда смотреть
    if flat:
        where = tr(T, "interests_flat", lang)
    else:
        types = ", ".join(_type_name(k, lang).lower() for k in interests["top"][:2])
        where = tr(T, "interests_lead", lang).format(level=LEVEL[interests["level"]][lang], types=types)
        where += " " + tr(T, "clusters_lead", lang).format(
            clusters=", ".join(clusters[c]["title"][lang] for c in rec["top"]))

    # 2. Сильная сторона сейчас
    strengths = []
    spatial = result.get("spatial") or {}
    if spatial.get("level"):
        strengths.append(SPATIAL[spatial["level"]][lang])
    style = _style_scores(result.get("work_style"))
    if style:
        best = max(style, key=style.get)
        if style[best] >= STYLE_STRONG:
            strengths.append(tr(T, "style_strength", lang).format(
                name=STYLE[best][lang].lower(), text=STYLE_STRENGTH[best][lang]))
    strong = " ".join(strengths)

    # 3. Расхождение
    gaps = []
    for d in result.get("discrepancies", [])[:MAX_DISCREPANCIES]:
        key = "disc_high_no" if d["questionnaire"] == "high" else "disc_low_yes"
        gaps.append(tr(T, key, lang).format(type=_type_name(d["type"], lang)))
    for d in result.get("attention_discrepancies", [])[:1]:
        how = tr(T, "attention_higher" if d["attention"] == "high" else "attention_lower", lang)
        gaps.append(tr(T, "disc_attention", lang).format(type=_type_name(d["type"], lang), how=how))
    gap = " ".join(gaps) or tr(T, "no_discrepancy", lang)

    # 4. Состояние на тесте
    flags = result.get("flags", [])
    state = (tr(T, "state_flags", lang).format(flags=", ".join(tr(T, f"flag_{f}", lang) for f in flags))
             if flags else tr(T, "state_ok", lang))
    monitoring = result.get("monitoring") or {}
    extra = monitoring.get("state") or {}
    if extra.get("fatigue_signs"):
        state += " " + tr(T, "state_fatigue", lang)
    if extra.get("movement"):
        state += " " + tr(T, "state_movement", lang)

    # 5. Что сделать в ближайший месяц
    if flat:
        steps = list(tr(T, "flat_steps", lang))
    else:
        first, *rest = rec["top"]
        steps = NEXT_STEPS[first][lang][:2] + [NEXT_STEPS[c][lang][0] for c in rest[:1]]
    steps.append(tr(T, "retest", lang))

    return [
        {"key": "where", "title": tr(T, "s1", lang), "text": where},
        {"key": "strength", "title": tr(T, "s2", lang), "text": strong or "—"},
        {"key": "gap", "title": tr(T, "s3", lang), "text": gap},
        {"key": "state", "title": tr(T, "s4", lang), "text": state},
        {"key": "steps", "title": tr(T, "s5", lang), "steps": steps},
    ]


def build_model(result: dict, meta: dict) -> dict:
    lang = result.get("lang") or "ru"
    student = meta.get("student") or {}
    rec = result["recommendation"]
    by_id = {c["cluster"]: c for c in rec["clusters"]}
    monitoring = result.get("monitoring")
    neuro = None
    if meta.get("with_headband"):
        cards = (monitoring or {}).get("cards") or {}
        if cards.get("shown"):
            top = ", ".join(_type_name(t, lang).lower() for t in cards["type_order"][:2])
            attention = tr(T, "neuro_attention", lang).format(types=top)
        else:
            attention = tr(T, "neuro_hidden", lang).format(
                reason=cards.get("reason") or "нет данных")
        neuro = {"badge": tr(T, "neuro_badge", lang), "attention": attention}
    started = meta.get("started_at") or ""
    try:
        date = datetime.fromisoformat(started).strftime("%d.%m.%Y")
    except ValueError:
        date = started[:10]
    style = _style_scores(result.get("work_style"))
    return {
        "lang": lang,
        "session": meta.get("id"),
        "student": {"name": student.get("name", ""), "grade": student.get("grade", "")},
        "date": date,
        "with_headband": bool(meta.get("with_headband")),
        "t": {k: tr(T, k, lang) for k in T},
        "summary": build_summary(result, lang),
        "interests": {
            "level": LEVEL[result["interests"]["level"]][lang],
            "types": [{"type": k, "name": TYPES[k][lang][0], "desc": TYPES[k][lang][1],
                       "score": result["interests"]["scores"][k]} for k in TYPES],
        },
        "clusters": [{"title": by_id[c]["title"][lang], "score": by_id[c]["score"],
                      "professions": [p["title"].get(lang) or p["title"]["ru"] for p in by_id[c]["professions"]]}
                     for c in rec["top"]],
        "spatial": result.get("spatial"),
        "style": ([{"name": STYLE[k][lang], "score": v} for k, v in style.items()] if style else None),
        "neuro": neuro,
        "result": result,  # для технического отчёта
    }
