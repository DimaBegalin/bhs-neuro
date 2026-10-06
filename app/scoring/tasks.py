"""Блоки заданий (вращение, числа, слова): точность и уровень.

10–12 заданий дают грубую оценку, поэтому кластеры не переставляются:
уровень называет сильную сторону или зону развития (документ «Методология
2.0», расчёт, п. 5). Пороги и шанс угадать берутся из содержимого блока.
"""
from __future__ import annotations

BLOCKS = ("spatial", "numeric", "verbal")
STRONG_SHARE = 0.75
WEAK_SHARE = 0.375


def score_tasks(trials: list[dict], strong_share: float = STRONG_SHARE,
                weak_share: float = WEAK_SHARE, chance: float | None = None) -> dict:
    """trials: [{"item", "correct": bool | None (тайм-аут), "rt_ms"}].

    У двухвариантной задачи шанс 50%, у четырёхвариантной 25%, поэтому
    «зона развития» у них начинается с разной доли верных.
    """
    total = len(trials)
    if total == 0:
        return {"total": 0, "correct": 0, "share": None, "level": None, "timeouts": 0,
                "median_rt_ms": None, "chance": chance}
    correct = sum(1 for t in trials if t.get("correct") is True)
    timeouts = sum(1 for t in trials if t.get("correct") is None)
    share = correct / total
    rts = sorted(t["rt_ms"] for t in trials if t.get("rt_ms") is not None)
    level = "strong" if share >= strong_share else "zone" if share <= weak_share else "middle"
    return {"total": total, "correct": correct, "share": round(share, 3), "level": level,
            "timeouts": timeouts, "median_rt_ms": rts[len(rts) // 2] if rts else None,
            "chance": chance}
