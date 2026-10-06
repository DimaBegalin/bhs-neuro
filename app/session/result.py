"""Итог сессии: всё, из чего строятся саммари и отчёты (этап 3).

Читает файлы сессии, считает рекомендацию по ответам и задачам, отдельно
нейромониторинг, и пишет result.json. Пересчитывается в любой момент из
сырых файлов: это нужно, когда меняются пороги после пилота.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from app import content
from app.eeg.monitoring import monitoring
from app.scoring.bigfive import score_bigfive
from app.scoring.interests import TYPES, score_interests
from app.scoring.match import rank
from app.scoring.tasks import BLOCKS, score_tasks
from app.scoring.validity import card_shares, discrepancies, validity_flags
from app.storage import atomic_write_json, read_json

RESULT_VERSION = 2  # 2: карточки парами, блоки заданий на числа и слова


def _payloads(events: list[dict], kind: str) -> list[dict]:
    return [e["payload"] for e in events if e["kind"] == kind]


def collect(events: list[dict]) -> dict:
    """Ответы из журнала. Повторный ответ на тот же пункт заменяет прежний."""
    interest: dict[str, dict] = {}
    for p in _payloads(events, "interest_answer"):
        interest[p["item"]] = {"item": p["item"], "value": int(p["value"]), "rt_ms": p.get("rt_ms")}
    types = content.card_types()
    cards: dict[tuple, dict] = {}
    for p in _payloads(events, "card_choice"):
        pair = list(p["pair"])
        cards[tuple(sorted(pair))] = {"pair": pair, "types": [types.get(c) for c in pair],
                                      "chosen": p["chosen"], "chosen_type": types.get(p["chosen"]),
                                      "rt_ms": p.get("rt_ms")}
    tasks: dict[str, list[dict]] = {}
    for block in BLOCKS:
        key = content.task_key(block)
        answered: dict[str, dict] = {}
        for p in _payloads(events, f"{block}_answer"):
            choice = p.get("choice")
            answered[p["item"]] = {"item": p["item"], "choice": choice, "rt_ms": p.get("rt_ms"),
                                   "correct": None if choice is None else choice == key.get(p["item"])}
        tasks[block] = list(answered.values())
    bigfive: dict[str, int] = {}
    for p in _payloads(events, "bigfive_answer"):
        bigfive[p["item"]] = int(p["value"])
    subjects = _payloads(events, "context_subjects")
    return {"interest": list(interest.values()), "cards": list(cards.values()), "bigfive": bigfive,
            "tasks": tasks, "subjects": subjects[-1].get("subjects", []) if subjects else []}


def build_result(folder: Path) -> dict:
    folder = Path(folder)
    meta = read_json(folder / "meta.json", {})
    events = read_json(folder / "events.json", [])
    answers = collect(events)
    items = content.load("interests")["items"]
    profile = score_interests(items, {a["item"]: a["value"] for a in answers["interest"]})
    tasks = {block: score_tasks(answers["tasks"][block], **content.task_rules(block)) for block in BLOCKS}
    clusters = content.clusters()
    ranking = rank(profile.vector(), content.occupations(), [c["id"] for c in clusters])
    titles = {c["id"]: c["title"] for c in clusters}
    for cluster in ranking["clusters"]:
        cluster["title"] = titles[cluster["cluster"]]
    eeg = None
    npz = folder / "signal.npz"
    if meta.get("with_headband") and npz.exists():
        data = np.load(npz)
        eeg = monitoring(np.asarray(data["signal"], dtype=float), int(data["fs"]), events)
    result = {
        "version": RESULT_VERSION,
        "session": meta.get("id"),
        "lang": (meta.get("student") or {}).get("lang", "ru"),
        "interests": {"scores": profile.scores, "level": profile.level, "spread": profile.spread,
                      "top": profile.top(3), "answered": profile.answered, "expected": profile.expected},
        "recommendation": ranking,
        **tasks,  # spatial, numeric, verbal
        "subjects": answers["subjects"],
        "work_style": (score_bigfive(content.load("bigfive")["items"], answers["bigfive"])
                       if content.available("bigfive") and answers["bigfive"] else None),
        "cards": answers["cards"],
        "card_shares": card_shares(answers["cards"]),
        "flags": validity_flags(answers["interest"], profile, answers["cards"], list(tasks.values())),
        "discrepancies": discrepancies(profile, answers["cards"]),
        "monitoring": eeg,
    }
    atomic_write_json(folder / "result.json", result)
    return result
