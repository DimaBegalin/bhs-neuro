"""Спектральная оценка методом Уэлча по принятым эпохам."""
import numpy as np
from scipy.signal import welch

# np.trapezoid появился в numpy 2.0, на более старых версиях имя было np.trapz
_integrate = getattr(np, "trapezoid", None) or np.trapz


def psd_of_epochs(epochs: np.ndarray, fs: int, keep: np.ndarray | None = None
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Средняя мощность по принятым эпохам.

    Возврат: (freqs формы (n_freqs,), psd формы (n_channels, n_freqs)).
    """
    if keep is not None:
        epochs = epochs[keep]
    if epochs.shape[0] == 0:
        raise ValueError("не осталось ни одной принятой эпохи")
    nperseg = epochs.shape[-1]
    freqs, psd = welch(epochs, fs=fs, window="hann", nperseg=nperseg, axis=-1)
    return freqs, psd.mean(axis=0)


def band_power(freqs: np.ndarray, psd: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Интеграл мощности в полосе [lo, hi] по каждому каналу."""
    lo = max(1.0, float(lo))
    mask = (freqs >= lo) & (freqs <= hi)
    if not mask.any():
        return np.zeros(psd.shape[0])
    return _integrate(psd[:, mask], freqs[mask], axis=-1)
