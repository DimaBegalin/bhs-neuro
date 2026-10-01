"""Стиль работы по Mini-IPIP (Donnellan et al., 2006): пять черт по 4 пункта.

Пункты IPIP — public domain (ipip.ori.org). В рекомендацию не входит:
личность говорит о том, «как» человеку комфортнее работать, а не «кем»
(документ «Методология 2.0»). Баллы 0–100 по шкале 1–5 с учётом обратных
пунктов, без норм.
"""
from __future__ import annotations

TRAITS = ("E", "A", "C", "N", "I")


def score_bigfive(items: list[dict], answers: dict[str, int]) -> dict:
    """items: [{"id","scale","keyed":"+|-"}], answers: id → 1..5."""
    sums = {t: 0 for t in TRAITS}
    counts = {t: 0 for t in TRAITS}
    for item in items:
        value = answers.get(item["id"])
        if value is None:
            continue
        value = int(value)
        if not 1 <= value <= 5:
            raise ValueError(f"ответ {value} на {item['id']} вне шкалы 1–5")
        sums[item["scale"]] += value if item["keyed"] == "+" else 6 - value
        counts[item["scale"]] += 1
    scores = {t: (round((sums[t] / counts[t] - 1) / 4 * 100, 1) if counts[t] else None)
              for t in TRAITS}
    # в отчёте нейротизм показывается как эмоциональная устойчивость
    stability = None if scores["N"] is None else round(100 - scores["N"], 1)
    return {"scores": scores, "stability": stability, "answered": counts}
