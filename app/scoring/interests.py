"""Профиль интересов RIASEC и его выраженность.

Каждое утверждение относится к одному типу и оценивается по шкале 1–5.
Балл типа — среднее по его утверждениям, переведённое в 0–100. Пропуски
допустимы: балл считается по отвеченным, а полнота сохраняется отдельно.
Нормы не используются (ADR 0004): профиль читается относительно самого ученика.
"""
from __future__ import annotations

from dataclasses import dataclass

TYPES = ("R", "I", "A", "S", "E", "C")
SCALE_MIN, SCALE_MAX = 1, 5

# Пороги выраженности: разница верхнего и нижнего типа в пунктах 0–100.
# Стартовые значения, калибруются на пилоте (документ «Методология 2.0»).
BRIGHT_SPREAD = 40.0
MODERATE_SPREAD = 20.0
ALL_LOW = 30.0


@dataclass(frozen=True)
class InterestProfile:
    scores: dict[str, float]
    answered: dict[str, int]
    expected: dict[str, int]
    spread: float
    level: str  # bright | moderate | flat

    def top(self, k: int = 3) -> list[str]:
        return sorted(TYPES, key=lambda t: (-self.scores[t], TYPES.index(t)))[:k]

    def vector(self) -> list[float]:
        return [self.scores[t] for t in TYPES]


def profile_level(scores: dict[str, float]) -> tuple[float, str]:
    values = list(scores.values())
    spread = max(values) - min(values)
    if max(values) < ALL_LOW or spread < MODERATE_SPREAD:
        return spread, "flat"
    return spread, "bright" if spread >= BRIGHT_SPREAD else "moderate"


def score_interests(items: list[dict], answers: dict[str, int]) -> InterestProfile:
    """items: [{"id", "type"}], answers: id → 1..5."""
    sums = {t: 0.0 for t in TYPES}
    answered = {t: 0 for t in TYPES}
    expected = {t: 0 for t in TYPES}
    for item in items:
        kind = item["type"]
        expected[kind] += 1
        value = answers.get(item["id"])
        if value is None:
            continue
        if not SCALE_MIN <= int(value) <= SCALE_MAX:
            raise ValueError(f"ответ {value} на {item['id']} вне шкалы 1–5")
        sums[kind] += int(value)
        answered[kind] += 1
    scores = {}
    for t in TYPES:
        if answered[t]:
            mean = sums[t] / answered[t]
            scores[t] = round((mean - SCALE_MIN) / (SCALE_MAX - SCALE_MIN) * 100, 1)
        else:
            scores[t] = 0.0
    spread, level = profile_level(scores)
    return InterestProfile(scores, answered, expected, round(spread, 1), level)
