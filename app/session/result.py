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
from app.scoring.spatial import score_spatial
from app.scoring.validity import discrepancies, validity_flags
from app.storage import atomic_write_json, read_json

RESULT_VERSION = 1


def _payloads(events: list[dict], kind: str) -> list[dict]:
    return [e["payload"] for e in events if e["kind"] == kind]


def collect(events: list[dict]) -> dict:
    """Ответы из журнала. Повторный ответ на тот же пункт заменяет прежний."""
    interest: dict[str, dict] = {}
    for p in _payloads(events, "interest_answer"):
        interest[p["item"]] = {"item": p["item"], "value": int(p["value"]), "rt_ms": p.get("rt_ms")}
    types = content.card_types()
    cards: dict[str, dict] = {}
    for p in _payloads(events, "card_rating"):
        cards[p["card"]] = {"card": p["card"], "type": types.get(p["card"]),
                            "liked": p.get("liked"), "rt_ms": p.get("rt_ms")}
    key = content.spatial_key()
    spatial: dict[str, dict] = {}
    for p in _payloads(events, "spatial_answer"):
        choice = p.get("choice")
        spatial[p["item"]] = {"item": p["item"], "choice": choice, "rt_ms": p.get("rt_ms"),
                              "correct": None if choice is None else choice == key.get(p["item"])}
    bigfive: dict[str, int] = {}
    for p in _payloads(events, "bigfive_answer"):
        bigfive[p["item"]] = int(p["value"])
    subjects = _payloads(events, "context_subjects")
    return {"interest": list(interest.values()), "cards": list(cards.values()), "bigfive": bigfive,
            "spatial": list(spatial.values()),
            "subjects": subjects[-1].get("subjects", []) if subjects else []}


def attention_discrepancies(profile, eeg_cards: dict | None) -> list[dict]:
    """Тип в верхней двойке опросника, а внимание к его карточкам в нижней двойке, и наоборот."""
    if not eeg_cards or not eeg_cards.get("shown"):
        return []
    order = eeg_cards["type_order"]
    if len(order) < 4:
        return []
    top_q, low_q = set(profile.top(6)[:2]), set(profile.top(6)[-2:])
    top_a, low_a = set(order[:2]), set(order[-2:])
    found = [{"type": t, "questionnaire": "high", "attention": "low"} for t in TYPES if t in top_q and t in low_a]
    found += [{"type": t, "questionnaire": "low", "attention": "high"} for t in TYPES if t in low_q and t in top_a]
    return found


def build_result(folder: Path) -> dict:
    folder = Path(folder)
    meta = read_json(folder / "meta.json", {})
    events = read_json(folder / "events.json", [])
    answers = collect(events)
    items = content.load("interests")["items"]
    profile = score_interests(items, {a["item"]: a["value"] for a in answers["interest"]})
    spatial = score_spatial(answers["spatial"], **content.spatial_rules())
    ranking = rank(profile.vector(), content.occupations(), [c["id"] for c in content.clusters()])
    eeg = None
    npz = folder / "signal.npz"
    if meta.get("with_headband") and npz.exists():
        data = np.load(npz)
        eeg = monitoring(np.asarray(data["signal"], dtype=float), int(data["fs"]), events,
                         content.card_types())
    result = {
        "version": RESULT_VERSION,
        "session": meta.get("id"),
        "lang": (meta.get("student") or {}).get("lang", "ru"),
        "interests": {"scores": profile.scores, "level": profile.level, "spread": profile.spread,
                      "top": profile.top(3), "answered": profile.answered, "expected": profile.expected},
        "recommendation": ranking,
        "spatial": spatial,
        "subjects": answers["subjects"],
        "work_style": (score_bigfive(content.load("bigfive")["items"], answers["bigfive"])
                       if content.available("bigfive") and answers["bigfive"] else None),
        "cards": answers["cards"],
        "flags": validity_flags(answers["interest"], profile, answers["cards"], spatial),
        "discrepancies": discrepancies(profile, answers["cards"]),
        "attention_discrepancies": attention_discrepancies(profile, (eeg or {}).get("cards")),
        "monitoring": eeg,
    }
    atomic_write_json(folder / "result.json", result)
    return result
