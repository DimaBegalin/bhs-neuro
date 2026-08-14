"""Индивидуальная частота альфа-пика и производные от неё полосы.

Основание: Klimesch (1999), Brain Research Reviews 29(2-3), 169-195 для
привязки полос к личному пику; Corcoran et al. (2018), Psychophysiology 55(7)
для устойчивой автоматической оценки.

Пик ищется поверх фона 1/f, а не поверх сырого спектра. Без вычитания фона
наклон спектра сам по себе даёт ложный максимум даже на чистом шуме.
"""
import numpy as np

BAND_OFFSETS = {
    "theta": (-6.0, -4.0),
    "alpha_low": (-4.0, -2.0),
    "alpha_high": (-2.0, 2.0),
}
BETA_TOP = 30.0
MIN_BAND_HZ = 1.0
# фон 1/f подгоняется по частотам вне альфа-окна. Нижняя граница держится
# выше среза фильтра: подавленные фильтром частоты искажают подгонку и
# порождают ложный пик на чистом шуме
FIT_RANGE = (6.0, 30.0)


def _background(freqs: np.ndarray, spectrum: np.ndarray,
                fmin: float, fmax: float,
                fit_range: tuple[float, float] = FIT_RANGE) -> np.ndarray:
    """Фон 1/f: прямая в логарифмических координатах по точкам вне альфа-окна."""
    fit_mask = ((freqs >= fit_range[0]) & (freqs <= fit_range[1])
                & ~((freqs >= fmin) & (freqs <= fmax)) & (spectrum > 0))
    if fit_mask.sum() < 4:
        return np.full_like(spectrum, float(np.median(spectrum)))
    slope, intercept = np.polyfit(np.log(freqs[fit_mask]),
                                  np.log(spectrum[fit_mask]), 1)
    with np.errstate(divide="ignore"):
        log_freqs = np.log(np.where(freqs > 0, freqs, 1e-6))
    return np.exp(slope * log_freqs + intercept)


def compute_iaf(freqs: np.ndarray, psd: np.ndarray, occipital: tuple[int, ...] = (2, 3),
                fmin: float = 7.0, fmax: float = 13.0,
                min_prominence: float = 1.5) -> tuple[float | None, float]:
    """Частота альфа-пика по затылочным каналам.

    Выраженность считается как отношение спектра к фону 1/f в окне поиска.
    Значение около единицы означает, что пика нет и есть только фон.
    Частота берётся центром тяжести превышения над фоном: это устойчивее
    простого максимума, когда пик широкий или зашумлённый.

    Возврат: (частота или None, выраженность пика).
    """
    spectrum = psd[list(occipital)].mean(axis=0)
    background = _background(freqs, spectrum, fmin, fmax)

    window = (freqs >= fmin) & (freqs <= fmax)
    if not window.any():
        return None, 0.0

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(background > 0, spectrum / background, 0.0)
    prominence = float(np.nanmax(ratio[window]))
    if prominence < min_prominence:
        return None, prominence

    excess = np.clip(spectrum[window] - background[window], 0.0, None)
    if excess.sum() <= 0:
        return None, prominence
    iaf = float((freqs[window] * excess).sum() / excess.sum())
    return iaf, prominence


def bands_from_iaf(iaf: float) -> dict[str, tuple[float, float]]:
    """Полосы, отсчитанные от личного пика. Нижняя граница обрезается по 1 Гц."""
    bands: dict[str, tuple[float, float]] = {}
    for name, (lo_off, hi_off) in BAND_OFFSETS.items():
        bands[name] = (max(MIN_BAND_HZ, iaf + lo_off), max(MIN_BAND_HZ, iaf + hi_off))
    bands["beta"] = (max(MIN_BAND_HZ, iaf + 2.0), BETA_TOP)
    return bands
