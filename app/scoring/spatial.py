"""Пространственные задачи: точность и уровень.

8 задач дают грубую оценку, поэтому кластеры не переставляются: уровень
только подкрепляет инженерные, IT- и естественнонаучные кластеры или
называет зону развития (документ «Методология 2.0», расчёт, п. 5).
"""
from __future__ import annotations

STRONG_SHARE = 0.75  # 6 из 8
WEAK_SHARE = 0.375   # 3 из 8 и меньше


def score_spatial(trials: list[dict], strong_share: float = STRONG_SHARE,
                  weak_share: float = WEAK_SHARE, chance: float | None = None) -> dict:
    """trials: [{"item", "correct": bool | None (тайм-аут), "rt_ms"}].

    Пороги берутся из содержимого задачи: у двухвариантной задачи шанс 50%,
    и «зона развития» начинается выше, чем у задачи с восемью вариантами.
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
