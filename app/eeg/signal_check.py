"""Проверка, что ободок отдаёт настоящую ЭЭГ в правильных единицах.

Запись из двух отрезков: глаза закрыты, затем открыты. Настоящая ЭЭГ
показывает реакцию Бергера: затылочная альфа при закрытых глазах заметно
сильнее, чем при открытых. Амплитуда после фильтра 1–40 Гц сверяется с
эталоном из записей на Mac: так ловится ошибка множителя единиц (В→мкВ),
которая сдвигает амплитуду на порядки.
"""
from __future__ import annotations

import numpy as np

from analyzer.iaf import compute_iaf
from analyzer.preprocess import bandpass, epoch, notch, reject_epochs
from analyzer.spectra import band_power, psd_of_epochs

CHANNELS = ("T3", "T4", "O1", "O2")
OCCIPITAL = (2, 3)
ALPHA = (8.0, 12.0)


def _clean(sig: np.ndarray, fs: int) -> np.ndarray:
    return bandpass(notch(sig, fs), fs, 1.0, 40.0)


def segment_metrics(sig: np.ndarray, fs: int) -> dict:
    """Амплитуда, доля пригодных эпох и сетевая наводка одного отрезка.

    Амплитуда считается по пригодным эпохам, а если пригодных нет, по всему
    отрезку: иначе ошибка единиц спряталась бы за браком всех эпох.
    """
    clean = _clean(sig, fs)
    epochs = epoch(clean, fs)
    keep = reject_epochs(epochs, fs)
    used = epochs[keep] if keep.any() else epochs
    rms = np.sqrt((used ** 2).mean(axis=(0, 2)))
    freqs, psd = psd_of_epochs(epoch(sig - sig.mean(axis=-1, keepdims=True), fs), fs)
    line = band_power(freqs, psd, 49.0, 51.0)
    body = band_power(freqs, psd, 1.0, 40.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        line_ratio = np.where(body > 0, line / body, np.inf)
    return {
        "rms_uv": {name: float(rms[i]) for i, name in enumerate(CHANNELS)},
        "accepted_share": float(keep.mean()) if keep.size else 0.0,
        "line_ratio": {name: float(line_ratio[i]) for i, name in enumerate(CHANNELS)},
        "_epochs": epochs,
        "_keep": keep,
    }


def check_recording(closed: np.ndarray, opened: np.ndarray, fs: int) -> dict:
    """Показатели записи «глаза закрыты / открыты».

    alpha_reactivity — отношение затылочной альфы закрытые/открытые.
    У живой ЭЭГ оно обычно больше 1,3; около 1 — шум или срыв контакта.
    """
    c = segment_metrics(closed, fs)
    o = segment_metrics(opened, fs)

    def alpha(seg: dict) -> float:
        keep = seg["_keep"] if seg["_keep"].any() else None
        freqs, psd = psd_of_epochs(seg["_epochs"], fs, keep)
        return float(band_power(freqs, psd, *ALPHA)[list(OCCIPITAL)].mean())

    a_closed, a_open = alpha(c), alpha(o)
    keep = c["_keep"] if c["_keep"].any() else None
    freqs, psd = psd_of_epochs(c["_epochs"], fs, keep)
    iaf, prominence = compute_iaf(freqs, psd, OCCIPITAL)
    for seg in (c, o):
        seg.pop("_epochs")
        seg.pop("_keep")
    return {
        "closed": c,
        "open": o,
        "alpha_reactivity": a_closed / a_open if a_open > 0 else float("inf"),
        "iaf_hz": iaf,
        "iaf_prominence": prominence,
    }


# Эталон по 42 записям калибровки на Mac (август–сентябрь 2026): амплитуда
# после фильтра 1–40 Гц у 5–95% записей 17–38 мкВ, медиана 28. Границы
# взяты с запасом: их задача поймать ошибку единиц (множитель 1e6 даёт
# порядки), а не отличить хороший контакт от среднего.
RMS_RANGE_UV = (2.0, 500.0)
MIN_REACTIVITY = 1.2
MIN_ACCEPTED_SHARE = 0.45
MIN_RATE_SHARE = 0.95
MAX_GAP_S = 0.5


def judge(result: dict, expected_fs: int, effective_fs: float, max_gap_s: float) -> list[dict]:
    """Вердикты по пунктам проверки: ok, текст и что делать, если не ok."""
    rms = result["closed"]["rms_uv"]
    low, high = RMS_RANGE_UV
    units_ok = all(low <= value <= high for value in rms.values())
    rate_ok = effective_fs >= expected_fs * MIN_RATE_SHARE
    gaps_ok = max_gap_s <= MAX_GAP_S
    quality_ok = result["closed"]["accepted_share"] >= MIN_ACCEPTED_SHARE
    reactivity = result["alpha_reactivity"]
    iaf = result["iaf_hz"]
    return [
        {"name": "Единицы сигнала", "ok": units_ok,
         "text": "амплитуда по каналам " + ", ".join(f"{k} {v:.3g} мкВ" for k, v in rms.items()),
         "fix": f"ожидалось {low:g}–{high:g} мкВ, как в записях на Mac: проверить множитель В→мкВ"},
        {"name": "Частота и полнота потока", "ok": rate_ok,
         "text": f"фактически {effective_fs:.1f} отсчётов/с при заявленных {expected_fs}",
         "fix": "часть пакетов теряется: проверить Bluetooth-адаптер и расстояние до ободка"},
        {"name": "Разрывы потока", "ok": gaps_ok,
         "text": f"самая длинная пауза между пакетами {max_gap_s:.2f} с",
         "fix": f"паузы длиннее {MAX_GAP_S} с: поток подвисает, проверить адаптер"},
        {"name": "Пригодность записи", "ok": quality_ok,
         "text": f"пригодных эпох при закрытых глазах {result['closed']['accepted_share']:.0%}",
         "fix": "много брака: поправить ободок, смочить электроды, не двигаться"},
        {"name": "Реакция альфы на закрытые глаза", "ok": reactivity >= MIN_REACTIVITY,
         "text": f"альфа закрыто/открыто = {reactivity:.2f}"
                 + (f", пик {iaf:.1f} Гц" if iaf else ", пик не найден"),
         "fix": "повторить проверку, держа глаза закрытыми весь отрезок; "
                "у части людей реакция слабая и на исправном приборе"},
    ]
