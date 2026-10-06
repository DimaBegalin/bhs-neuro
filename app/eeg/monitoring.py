"""Нейромониторинг сессии: качество сигнала по модулям и состояние на тесте.

В рекомендацию не входит (ADR 0001). Фоновой записи в начале нет (убрана
06.10.2026, чтобы сократить тест), поэтому внимание к карточкам не
считается: подавление альфы не с чем сравнивать. Альфа — стандартная полоса.
"""
from __future__ import annotations

import numpy as np

from analyzer.preprocess import bandpass, epoch, notch, reject_epochs
from analyzer.spectra import band_power, psd_of_epochs
from app.eeg.signal_check import OCCIPITAL

ALPHA_BAND = (8.0, 12.0)
MIN_MODULE_QUALITY = 0.6
FATIGUE_RISE = 0.3


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


def _ratio_theta_alpha(epochs, keep, fs) -> float | None:
    if keep.sum() == 0:
        return None
    freqs, psd = psd_of_epochs(epochs, fs, keep)
    theta = band_power(freqs, psd, 4.0, 7.0)[list(OCCIPITAL)].mean()
    alpha = band_power(freqs, psd, *ALPHA_BAND)[list(OCCIPITAL)].mean()
    return float(theta / alpha) if alpha > 0 else None


def monitoring(signal: np.ndarray, fs: int, events: list[dict]) -> dict:
    """signal (4, n) мкВ; events из events.json."""
    starts = [e for e in events if e["kind"] == "module_start" and e.get("sample") is not None]
    ends = {e["payload"].get("module"): e["sample"] for e in events
            if e["kind"] == "module_end" and e.get("sample") is not None}
    modules = {}
    for start in starts:
        name = start["payload"].get("module")
        _, keep = _clean_epochs(_segment(signal, start["sample"], ends.get(name)), fs)
        modules[name] = {"quality": round(float(keep.mean()), 3) if keep.size else None}

    # состояние на тесте: движения и признаки усталости (θ/α в последней трети к первой)
    qualities = [m["quality"] for m in modules.values() if m["quality"] is not None]
    task_start = starts[0]["sample"] if starts else None
    ended = [e["sample"] for e in events if e["kind"] == "session_end" and e.get("sample") is not None]
    task_end = ended[0] if ended else signal.shape[1]
    fatigue = None
    if task_start is not None and task_end - task_start >= 6 * 60 * fs // 3:
        third = (task_end - task_start) // 3
        first = _ratio_theta_alpha(*_clean_epochs(_segment(signal, task_start, task_start + third), fs), fs)
        last = _ratio_theta_alpha(*_clean_epochs(_segment(signal, task_end - third, task_end), fs), fs)
        if first and last:
            fatigue = round(last / first - 1.0, 3)
    return {
        "modules": modules,
        "state": {
            "movement": bool(qualities) and min(qualities) < MIN_MODULE_QUALITY,
            "theta_alpha_change": fatigue,
            "fatigue_signs": fatigue is not None and fatigue >= FATIGUE_RISE,
        },
    }
