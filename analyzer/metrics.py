"""Нейрометрики одного блока задач.

ERD как индекс корковой активации: Pfurtscheller и Lopes da Silva (1999),
Clinical Neurophysiology 110(11), 1842-1857.
Верхняя альфа и направленное внимание: Klimesch, Sauseng, Hanslmayr (2007),
Brain Research Reviews 53(1), 63-88.
Индекс вовлечённости beta/(alpha+theta): Pope, Bogart, Bartolome (1995),
Biological Psychology 40(1-2), 187-195.
"""
import numpy as np
from scipy.stats import linregress

from analyzer.spectra import psd_of_epochs, band_power

OCCIPITAL = (2, 3)
TEMPORAL = (0, 1)


def erd_percent(p_block: float, p_base: float) -> float:
    """Изменение мощности относительно покоя в процентах. Минус это десинхронизация."""
    if p_base <= 0:
        return 0.0
    return float((p_block - p_base) / p_base * 100.0)


def engagement_index(freqs: np.ndarray, psd: np.ndarray, bands: dict) -> float:
    beta = band_power(freqs, psd, *bands["beta"]).mean()
    alpha = (band_power(freqs, psd, *bands["alpha_low"]).mean()
             + band_power(freqs, psd, *bands["alpha_high"]).mean())
    theta = band_power(freqs, psd, *bands["theta"]).mean()
    denominator = alpha + theta
    if denominator <= 0:
        return 0.0
    return float(beta / denominator)


def attention_slope(values: np.ndarray, times_s: np.ndarray) -> float:
    """Наклон линейной регрессии показателя по времени внутри блока."""
    values = np.asarray(values, dtype=float)
    times_s = np.asarray(times_s, dtype=float)
    if values.size < 3:
        return 0.0
    return float(linregress(times_s, values).slope)


def block_neuro_metrics(block_epochs: np.ndarray, base_psd_pack: tuple, fs: int,
                        bands: dict, keep: np.ndarray) -> dict:
    """Метрики блока относительно baseline покоя с открытыми глазами."""
    base_freqs, base_psd = base_psd_pack
    freqs, psd = psd_of_epochs(block_epochs, fs=fs, keep=keep)

    def occipital_power(f, p, band):
        return float(band_power(f, p, *bands[band])[list(OCCIPITAL)].mean())

    def temporal_power(f, p, band):
        return float(band_power(f, p, *bands[band])[list(TEMPORAL)].mean())

    # вовлечённость по каждой принятой эпохе, чтобы измерить её ход во времени
    kept_idx = np.flatnonzero(keep)
    per_epoch = []
    for i in kept_idx:
        f_i, p_i = psd_of_epochs(block_epochs[i:i + 1], fs=fs)
        per_epoch.append(engagement_index(f_i, p_i, bands))
    times = kept_idx.astype(float) * 1.0  # шаг эпох 1 секунда при перекрытии 50%

    return {
        "erd_alpha_high": erd_percent(occipital_power(freqs, psd, "alpha_high"),
                                      occipital_power(base_freqs, base_psd, "alpha_high")),
        "erd_alpha_low": erd_percent(occipital_power(freqs, psd, "alpha_low"),
                                     occipital_power(base_freqs, base_psd, "alpha_low")),
        "theta_rise": erd_percent(temporal_power(freqs, psd, "theta"),
                                  temporal_power(base_freqs, base_psd, "theta")),
        "engagement": engagement_index(freqs, psd, bands),
        "attention_slope": attention_slope(np.array(per_epoch), times),
        "epochs_total": int(block_epochs.shape[0]),
        "epochs_rejected": int((~keep).sum()),
    }
