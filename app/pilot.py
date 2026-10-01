# -*- coding: utf-8 -*-
"""Разбор пилота: проходят ли ворота перехода (документ «Методология 2.0»).

Берёт папки сессий с одного или нескольких ноутбуков и считает то, что
нужно для решения о переходе всех менеджеров: хронометраж, надёжность
шкал по языкам, долю плоских профилей и флагов, трудность задач на
вращение, согласие опросника с карточками и долю годной ЭЭГ.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path

from app import content
from app.scoring.interests import TYPES
from app.storage import read_json

GATE_MEDIAN_MIN = 13.0
GATE_ALPHA = 0.7


def cronbach_alpha(matrix: list[list[float]]) -> float | None:
    """Строки — ученики, столбцы — пункты одной шкалы. Нужно ≥ 3 ученика и ≥ 2 пункта."""
    rows = [r for r in matrix if all(v is not None for v in r)]
    if len(rows) < 3 or len(rows[0]) < 2:
        return None
    k = len(rows[0])
    item_vars = [statistics.pvariance([r[j] for r in rows]) for j in range(k)]
    total_var = statistics.pvariance([sum(r) for r in rows])
    if total_var == 0:
        return None
    return round(k / (k - 1) * (1 - sum(item_vars) / total_var), 3)


def _sessions(roots: list[Path]) -> list[Path]:
    found = []
    for root in roots:
        for meta in Path(root).rglob("meta.json"):
            if (meta.parent / "events.json").exists():
                found.append(meta.parent)
    return found


def _module_minutes(events: list[dict]) -> dict[str, float]:
    started: dict[str, float] = {}
    out: dict[str, float] = {}
    for e in events:
        module = (e.get("payload") or {}).get("module")
        if e["kind"] == "module_start":
            started[module] = e["t_s"]
        elif e["kind"] == "module_end" and module in started:
            out[module] = (e["t_s"] - started[module]) / 60
    return out


def analyze(roots: list[Path]) -> dict:
    interest_items = content.load("interests")["items"]
    big5_items = content.load("bigfive")["items"] if content.available("bigfive") else []
    spatial_key = content.spatial_key()
    card_types = content.card_types()

    sessions = []
    for folder in _sessions(roots):
        meta = read_json(folder / "meta.json", {})
        events = read_json(folder / "events.json", [])
        result = read_json(folder / "result.json")
        sessions.append((folder, meta, events, result))

    finished = [s for s in sessions if s[1].get("status") == "finished"]
    durations = [(s[2][-1]["t_s"] - s[2][0]["t_s"]) / 60 for s in finished if s[2]]
    modules: dict[str, list[float]] = defaultdict(list)
    by_lang_interest: dict[str, dict[str, list[list[float]]]] = defaultdict(lambda: defaultdict(list))
    by_lang_big5: dict[str, dict[str, list[list[float]]]] = defaultdict(lambda: defaultdict(list))
    spatial_items: dict[str, list[int]] = defaultdict(list)
    levels, flags = defaultdict(int), defaultdict(int)
    agree = []
    eeg = {"sessions": 0, "reactive": 0, "cards_shown": 0}

    for folder, meta, events, result in finished:
        lang = (meta.get("student") or {}).get("lang", "ru")
        for module, minutes in _module_minutes(events).items():
            modules[module].append(minutes)
        answers = {e["payload"]["item"]: e["payload"]["value"] for e in events if e["kind"] == "interest_answer"}
        for t in TYPES:
            ids = [i["id"] for i in interest_items if i["type"] == t]
            by_lang_interest[lang][t].append([answers.get(i) for i in ids])
        b5 = {e["payload"]["item"]: e["payload"]["value"] for e in events if e["kind"] == "bigfive_answer"}
        for trait in ("E", "A", "C", "N", "I"):
            ids = [(i["id"], i["keyed"]) for i in big5_items if i["scale"] == trait]
            by_lang_big5[lang][trait].append([None if b5.get(i) is None else (b5[i] if k == "+" else 6 - b5[i]) for i, k in ids])
        for e in events:
            if e["kind"] == "spatial_answer":
                p = e["payload"]
                spatial_items[p["item"]].append(int(p.get("choice") == spatial_key.get(p["item"])))
        if result:
            levels[result["interests"]["level"]] += 1
            for f in result.get("flags", []):
                flags[f] += 1
            liked = defaultdict(list)
            for c in result.get("cards", []):
                if c.get("liked") is not None:
                    liked[c["type"]].append(1.0 if c["liked"] else 0.0)
            pairs = [(result["interests"]["scores"][t], statistics.mean(liked[t])) for t in TYPES if liked[t]]
            if len(pairs) >= 4 and len({p[1] for p in pairs}) > 1 and len({p[0] for p in pairs}) > 1:
                agree.append(statistics.correlation([p[0] for p in pairs], [p[1] for p in pairs]))
            mon = result.get("monitoring")
            if mon:
                eeg["sessions"] += 1
                eeg["reactive"] += int(bool((mon.get("background") or {}).get("reactive")))
                eeg["cards_shown"] += int(bool((mon.get("cards") or {}).get("shown")))

    alphas = {lang: {t: cronbach_alpha(rows) for t, rows in scales.items()} for lang, scales in by_lang_interest.items()}
    b5_alphas = {lang: {t: cronbach_alpha(rows) for t, rows in scales.items()} for lang, scales in by_lang_big5.items()}
    n = len(finished)
    median = statistics.median(durations) if durations else None
    all_alphas = [a for scales in alphas.values() for a in scales.values() if a is not None]
    return {
        "sessions": len(sessions), "finished": n,
        "statuses": dict(sorted({m.get("status"): sum(1 for s in sessions if s[1].get("status") == m.get("status"))
                                 for _, m, _, _ in sessions}.items(), key=lambda x: str(x[0]))),
        "median_minutes": None if median is None else round(median, 1),
        "module_minutes": {m: round(statistics.median(v), 1) for m, v in modules.items()},
        "interest_alpha": alphas, "bigfive_alpha": b5_alphas,
        "levels": dict(levels), "flags": dict(flags),
        "spatial_item_accuracy": {i: round(statistics.mean(v), 2) for i, v in sorted(spatial_items.items())},
        "questionnaire_cards_r": None if not agree else round(statistics.mean(agree), 2),
        "eeg": eeg,
        "gates": {
            "median_minutes_ok": median is not None and median <= GATE_MEDIAN_MIN,
            "alpha_ok": bool(all_alphas) and min(all_alphas) >= GATE_ALPHA,
            "lost_visits": sum(1 for s in sessions if s[1].get("status") in ("interrupted", "recording")),
        },
    }


def render_markdown(r: dict) -> str:
    def fmt(v):
        return "—" if v is None else str(v)
    lines = ["# Разбор пилота", "",
             f"Сессий: {r['sessions']}, завершено: {r['finished']}. Статусы: {r['statuses']}.",
             f"Медиана длительности: {fmt(r['median_minutes'])} мин (ворота: ≤ {GATE_MEDIAN_MIN}).", "",
             "## Ворота", "",
             f"- Хронометраж: {'да' if r['gates']['median_minutes_ok'] else 'нет'}",
             f"- Надёжность шкал интересов ≥ {GATE_ALPHA}: {'да' if r['gates']['alpha_ok'] else 'нет'}",
             f"- Оборванные сессии: {r['gates']['lost_visits']}", "",
             "## Модули, медиана минут", ""]
    lines += [f"- {m}: {v}" for m, v in r["module_minutes"].items()]
    lines += ["", "## Надёжность (альфа Кронбаха)", "", "| Язык | " + " | ".join(TYPES) + " |",
              "| --- |" + " --- |" * len(TYPES)]
    lines += [f"| {lang} | " + " | ".join(fmt(a.get(t)) for t in TYPES) + " |" for lang, a in r["interest_alpha"].items()]
    lines += ["", "Стиль работы (Mini-IPIP):", ""]
    lines += [f"- {lang}: " + ", ".join(f"{t} {fmt(v)}" for t, v in a.items()) for lang, a in r["bigfive_alpha"].items()]
    lines += ["", "## Профили и достоверность", "",
              f"- Выраженность: {r['levels']}", f"- Флаги: {r['flags'] or 'нет'}",
              f"- Согласие опросника и карточек (средняя r): {fmt(r['questionnaire_cards_r'])}", "",
              "## Задачи на вращение: доля верных", ""]
    lines += [f"- {i}: {v}" for i, v in r["spatial_item_accuracy"].items()]
    e = r["eeg"]
    lines += ["", "## ЭЭГ", "", f"- Сессий с ободком: {e['sessions']}, реакция альфы есть: {e['reactive']}, "
              f"внимание к карточкам показано: {e['cards_shown']}"]
    return "\n".join(lines) + "\n"
