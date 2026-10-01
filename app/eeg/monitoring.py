"""Нейромониторинг сессии: качество, внимание к карточкам, состояние.

В рекомендацию не входит (ADR 0001). Всё сравнивается с фоном самого
ученика. Внимание к карточке — подавление затылочной альфы в окне показа
относительно фона с открытыми глазами: чем сильнее подавление, тем выше
внимание. Показатель показывается, только если у ученика на фоне альфа
заметно реагирует на закрытие глаз: иначе подавлять нечего и ранжирование
карточек было бы шумом (у четверти записей на Mac реакции почти нет).
"""
from __future__ import annotations

import numpy as np

from analyzer.preprocess import bandpass, epoch, notch, reject_epochs
from analyzer.spectra import band_power, psd_of_epochs
from app.eeg.signal_check import MIN_REACTIVITY, OCCIPITAL, check_recording

CARD_S = 10.0
MIN_CLEAN_EPOCHS = 4  # эпохи по 2 с с перекрытием 50%: 4 эпохи ≈ 5 с чистого сигнала
MIN_VALID_CARDS = 9
MIN_MODULE_QUALITY = 0.6
FATIGUE_RISE = 0.3


def _events_by_kind(events: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for event in events:
        grouped.setdefault(event["kind"], []).append(event)
    return grouped


def _segment(signal: np.ndarray, a: int | None, b: int | None) -> np.ndarray:
    if a is None or b is None or b <= a:
        return signal[:, 0:0]
    return signal[:, a:min(b, signal.shape[1])]


def _clean_epochs(segment: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray]:
    if segment.shape[1] < 2 * fs:
        return np.zeros((0, segment.shape[0], 2 * fs)), np.zeros(0, dtype=bool)
    filtered = bandpass(notch(segment, fs), fs, 1.0, 40.0)
    epochs = epoch(filtered, fs)
    return epochs, reject_epochs(epochs, fs)


def _alpha(epochs: np.ndarray, keep: np.ndarray, fs: int, band: tuple[float, float]) -> float | None:
    if keep.sum() == 0:
        return None
    freqs, psd = psd_of_epochs(epochs, fs, keep)
    return float(band_power(freqs, psd, *band)[list(OCCIPITAL)].mean())


def _ratio_theta_alpha(epochs, keep, fs, band) -> float | None:
    if keep.sum() == 0:
        return None
    freqs, psd = psd_of_epochs(epochs, fs, keep)
    theta = band_power(freqs, psd, 4.0, 7.0)[list(OCCIPITAL)].mean()
    alpha = band_power(freqs, psd, *band)[list(OCCIPITAL)].mean()
    return float(theta / alpha) if alpha > 0 else None


def monitoring(signal: np.ndarray, fs: int, events: list[dict], card_types: dict[str, str]) -> dict:
    """signal (4, n) мкВ; events из events.json; card_types: id карточки → тип RIASEC."""
    ev = _events_by_kind(events)

    def at(kind: str) -> int | None:
        found = ev.get(kind)
        return found[0]["sample"] if found else None

    closed = _segment(signal, at("background_closed_start"), at("background_closed_end"))
    opened = _segment(signal, at("background_open_start"), at("background_open_end"))
    result: dict = {"background": None, "modules": {}, "cards": None, "state": {}}
    if closed.shape[1] < 10 * fs or opened.shape[1] < 10 * fs:
        result["background"] = {"ok": False, "reason": "нет фона"}
        return result

    bg = check_recording(closed, opened, fs)
    iaf = bg["iaf_hz"]
    band = (iaf - 2.0, iaf + 2.0) if iaf else (8.0, 12.0)
    open_epochs, open_keep = _clean_epochs(opened, fs)
    baseline = _alpha(open_epochs, open_keep, fs, band)
    reactive = bool(iaf) and bg["alpha_reactivity"] >= MIN_REACTIVITY
    result["background"] = {"ok": baseline is not None, "iaf_hz": iaf,
                            "alpha_reactivity": round(bg["alpha_reactivity"], 3),
                            "reactive": reactive, "band_hz": [round(b, 2) for b in band]}

    # качество по модулям
    starts = [e for e in events if e["kind"] == "module_start" and e.get("sample") is not None]
    ends = {e["payload"].get("module"): e["sample"] for e in events
            if e["kind"] == "module_end" and e.get("sample") is not None}
    for start in starts:
        name = start["payload"].get("module")
        epochs, keep = _clean_epochs(_segment(signal, start["sample"], ends.get(name)), fs)
        share = float(keep.mean()) if keep.size else None
        result["modules"][name] = {"quality": None if share is None else round(share, 3)}

    # внимание к карточкам
    cards = []
    for show in ev.get("card_show", []):
        card_id = show["payload"].get("card")
        a = show.get("sample")
        epochs, keep = _clean_epochs(_segment(signal, a, None if a is None else a + int(CARD_S * fs)), fs)
        power = _alpha(epochs, keep, fs, band) if keep.sum() >= MIN_CLEAN_EPOCHS else None
        erd = None if power is None or not baseline else (power - baseline) / baseline * 100.0
        cards.append({"card": card_id, "type": card_types.get(card_id),
                      "clean_epochs": int(keep.sum()),
                      "alpha_change_pct": None if erd is None else round(erd, 1)})
    valid = [c for c in cards if c["alpha_change_pct"] is not None]
    show_cards = reactive and baseline is not None and len(valid) >= MIN_VALID_CARDS
    if cards:
        # внимание = подавление альфы; ранг 1 — карточка с самым сильным подавлением
        for rank_no, card in enumerate(sorted(valid, key=lambda c: c["alpha_change_pct"]), start=1):
            card["attention_rank"] = rank_no
        per_type: dict[str, list[float]] = {}
        for c in valid:
            per_type.setdefault(c["type"], []).append(-c["alpha_change_pct"])
        type_attention = {t: round(float(np.mean(v)), 1) for t, v in per_type.items()}
        result["cards"] = {
            "shown": show_cards,
            "reason": None if show_cards else (
                "альфа на фоне не реагирует на закрытие глаз" if not reactive else
                "мало карточек с чистым сигналом"),
            "valid": len(valid), "total": len(cards), "items": cards,
            "type_attention": type_attention,
            "type_order": sorted(type_attention, key=lambda t: -type_attention[t]),
        }

    # состояние на тесте: движения и признаки усталости
    qualities = [m["quality"] for m in result["modules"].values() if m["quality"] is not None]
    task_start = at("background_open_end")
    task_end = at("session_end") or signal.shape[1]
    fatigue = None
    if task_start is not None and task_end - task_start >= 6 * 60 * fs // 3:
        third = (task_end - task_start) // 3
        first = _ratio_theta_alpha(*_clean_epochs(_segment(signal, task_start, task_start + third), fs), fs, band)
        last = _ratio_theta_alpha(*_clean_epochs(_segment(signal, task_end - third, task_end), fs), fs, band)
        if first and last:
            fatigue = round(last / first - 1.0, 3)
    result["state"] = {
        "movement": bool(qualities) and min(qualities) < MIN_MODULE_QUALITY,
        "theta_alpha_change": fatigue,
        "fatigue_signs": fatigue is not None and fatigue >= FATIGUE_RISE,
    }
    return result
