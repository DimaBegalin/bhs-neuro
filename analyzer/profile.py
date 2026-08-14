"""Карта когнитивной эффективности и сборка итогового профиля.

Все сравнения строятся внутри одного ребёнка между четырьмя доменами.
Межиндивидуальные сравнения запрещены, пока в базе меньше 100 сессий.
"""
import numpy as np

METHOD_VERSION = "1.0"
DOMAINS = ("numeric", "spatial", "verbal", "working_memory")
# пороги брака подобраны под сухие электроды прибора: на нём сорок процентов
# отбракованных эпох это рабочая норма, а не поломка. На пилоте перепроверить
MAX_REJECTED_CALIBRATION = 0.55
MAX_REJECTED_BLOCK = 0.60


def zscores(values) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    sd = arr.std(ddof=0)
    if sd <= 0:
        return np.zeros_like(arr)
    return (arr - arr.mean()) / sd


def build_domain_map(blocks: dict) -> list[dict]:
    """Четыре карточки: результат, цена усилия, эффективность.

    Цена усилия это среднее z-значений величины десинхронизации верхней альфы
    и подъёма теты. Чем больше ресурсов вложено, тем выше цена.
    Эффективность это z(точность) минус z(цена).
    """
    names = list(DOMAINS)
    acc = [blocks[d]["behavior"]["accuracy"] for d in names]
    erd_magnitude = [abs(blocks[d]["neuro"]["erd_alpha_high"]) for d in names]
    theta = [blocks[d]["neuro"]["theta_rise"] for d in names]

    z_acc = zscores(acc)
    z_cost = (zscores(erd_magnitude) + zscores(theta)) / 2.0
    efficiency = z_acc - z_cost

    cards = []
    for i, d in enumerate(names):
        cards.append({
            "domain": d,
            "accuracy": float(acc[i]),
            "median_rt_ms": float(blocks[d]["behavior"]["median_rt_ms"]),
            "cost": float(z_cost[i]),
            "efficiency": float(efficiency[i]),
            "attention_slope": float(blocks[d]["neuro"]["attention_slope"]),
        })
    return cards


def quality_verdict(calibration_rejected_share: float,
                    block_rejected_shares: dict,
                    iaf: float | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if iaf is None:
        reasons.append("альфа-пик не выделен, нейро-слой не считается")
    if calibration_rejected_share > MAX_REJECTED_CALIBRATION:
        reasons.append(
            f"в калибровке отбраковано {calibration_rejected_share:.0%} эпох, "
            f"порог {MAX_REJECTED_CALIBRATION:.0%}")
    for domain, share in block_rejected_shares.items():
        if share > MAX_REJECTED_BLOCK:
            reasons.append(
                f"в блоке {domain} отбраковано {share:.0%} эпох, "
                f"порог {MAX_REJECTED_BLOCK:.0%}")
    return (len(reasons) == 0), reasons


def build_profile(session_meta: dict, iaf: float | None, prominence: float,
                  bands: dict, blocks: dict) -> dict:
    rejected = {}
    for d in DOMAINS:
        total = max(1, blocks[d]["neuro"]["epochs_total"])
        rejected[d] = blocks[d]["neuro"]["epochs_rejected"] / total
    calibration_share = session_meta.get("calibration_rejected_share", 0.0)
    has_eeg, reasons = quality_verdict(calibration_share, rejected, iaf)

    if has_eeg:
        cards = build_domain_map(blocks)
    else:
        cards = [{
            "domain": d,
            "accuracy": float(blocks[d]["behavior"]["accuracy"]),
            "median_rt_ms": float(blocks[d]["behavior"]["median_rt_ms"]),
            "cost": None,
            "efficiency": None,
            "attention_slope": None,
        } for d in DOMAINS]

    return {
        "session_id": session_meta["session_id"],
        "lang": session_meta.get("lang", "ru"),
        "method_version": METHOD_VERSION,
        "iaf": float(iaf) if (iaf is not None and has_eeg) else None,
        "iaf_prominence": float(prominence),
        "bands": bands if has_eeg else None,
        "has_eeg": has_eeg,
        "quality": {"reasons": reasons, "rejected_by_block": rejected,
                    "calibration_rejected_share": calibration_share},
        "domains": cards,
        "behavior": {d: blocks[d]["behavior"] for d in DOMAINS},
        "neuro": {d: blocks[d]["neuro"] for d in DOMAINS} if has_eeg else None,
    }
