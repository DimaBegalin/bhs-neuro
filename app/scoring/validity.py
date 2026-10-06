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
# карточки идут парами «что интереснее»: каждый тип встречается в 5 парах
CARDS_RARE = 0.2   # выбран не больше чем в 1 паре из 5
CARDS_OFTEN = 0.8  # выбран в 4 парах из 5 и больше


def longest_run(values: list[int]) -> int:
    best = run = 0
    previous = None
    for value in values:
        run = run + 1 if value == previous else 1
        previous = value
        best = max(best, run)
    return best


def card_shares(choices: list[dict]) -> dict[str, float | None]:
    """choices: [{"types": [тип, тип], "chosen_type"}] → тип → доля пар, где выбрали его."""
    shown = {t: 0 for t in TYPES}
    won = {t: 0 for t in TYPES}
    for choice in choices:
        for kind in choice["types"]:
            shown[kind] += 1
        won[choice["chosen_type"]] += 1
    return {t: round(won[t] / shown[t], 3) if shown[t] else None for t in TYPES}


def discrepancies(profile: InterestProfile, choices: list[dict]) -> list[dict]:
    """Тип в верхней двойке опросника, а в парах его почти не выбирали, или наоборот.

    У плоского профиля верх и низ выбраны из почти равных баллов, поэтому
    расхождений для него не бывает.
    """
    if profile.level == "flat":
        return []
    order = profile.top(6)
    high, low = set(order[:2]), set(order[-2:])
    found = []
    for kind, share in card_shares(choices).items():
        if share is None:
            continue
        if kind in high and share <= CARDS_RARE:
            found.append({"type": kind, "questionnaire": "high", "cards": "no"})
        elif kind in low and share >= CARDS_OFTEN:
            found.append({"type": kind, "questionnaire": "low", "cards": "yes"})
    return found


def validity_flags(answers: list[dict], profile: InterestProfile, choices: list[dict],
                   tasks: list[dict]) -> list[str]:
    """answers: [{"item", "value", "rt_ms"}] в порядке показа; tasks — итоги блоков заданий."""
    flags = []
    rts = sorted(a["rt_ms"] for a in answers if a.get("rt_ms") is not None)
    if rts and rts[len(rts) // 2] < TOO_FAST_MEDIAN_MS:
        flags.append("too_fast")
    if longest_run([a["value"] for a in answers]) >= STRAIGHT_RUN:
        flags.append("straightlining")
    if len(discrepancies(profile, choices)) >= INCONSISTENT_TYPES:
        flags.append("inconsistent")
    if any(block.get("median_rt_ms") is not None and block["median_rt_ms"] < GUESS_MEDIAN_MS
           and (block.get("share") or 0) <= (block.get("chance") or 0.125) + GUESS_MARGIN
           for block in tasks):
        flags.append("guessing")
    return flags
