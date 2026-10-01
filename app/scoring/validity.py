"""Флаги достоверности и расхождения (CONTEXT.md).

Флаг не отменяет результат: он смягчает формулировки саммари и виден
менеджеру в техническом отчёте. Пороги стартовые, калибруются на пилоте.
"""
from __future__ import annotations

from app.scoring.interests import TYPES, InterestProfile

TOO_FAST_MEDIAN_MS = 1000
STRAIGHT_RUN = 10
INCONSISTENT_TYPES = 3
GUESS_MEDIAN_MS = 3000
GUESS_MARGIN = 0.1  # «наугад»: точность не выше шанса + 10 пунктов


def longest_run(values: list[int]) -> int:
    best = run = 0
    previous = None
    for value in values:
        run = run + 1 if value == previous else 1
        previous = value
        best = max(best, run)
    return best


def card_votes(cards: list[dict]) -> dict[str, list[bool]]:
    """cards: [{"card", "type", "liked": bool | None}] → тип → оценки."""
    votes: dict[str, list[bool]] = {t: [] for t in TYPES}
    for card in cards:
        if card.get("liked") is not None:
            votes[card["type"]].append(bool(card["liked"]))
    return votes


def discrepancies(profile: InterestProfile, cards: list[dict]) -> list[dict]:
    """Тип в верхней двойке опросника, а все его карточки «нет», или наоборот.

    У плоского профиля верх и низ выбраны из почти равных баллов, поэтому
    расхождений для него не бывает.
    """
    if profile.level == "flat":
        return []
    order = profile.top(6)
    high, low = set(order[:2]), set(order[-2:])
    found = []
    for kind, votes in card_votes(cards).items():
        if not votes:
            continue
        if kind in high and not any(votes):
            found.append({"type": kind, "questionnaire": "high", "cards": "no"})
        elif kind in low and all(votes):
            found.append({"type": kind, "questionnaire": "low", "cards": "yes"})
    return found


def validity_flags(answers: list[dict], profile: InterestProfile, cards: list[dict],
                   spatial: dict) -> list[str]:
    """answers: [{"item", "value", "rt_ms"}] в порядке показа."""
    flags = []
    rts = sorted(a["rt_ms"] for a in answers if a.get("rt_ms") is not None)
    if rts and rts[len(rts) // 2] < TOO_FAST_MEDIAN_MS:
        flags.append("too_fast")
    if longest_run([a["value"] for a in answers]) >= STRAIGHT_RUN:
        flags.append("straightlining")
    if len(discrepancies(profile, cards)) >= INCONSISTENT_TYPES:
        flags.append("inconsistent")
    chance = spatial.get("chance") or 0.125
    if (spatial.get("median_rt_ms") is not None and spatial["median_rt_ms"] < GUESS_MEDIAN_MS
            and (spatial.get("share") or 0) <= chance + GUESS_MARGIN):
        flags.append("guessing")
    return flags
