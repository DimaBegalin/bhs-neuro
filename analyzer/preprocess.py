"""Предобработка сигнала: фильтры, нарезка на эпохи, отбраковка."""
import numpy as np
from scipy.signal import butter, sosfiltfilt, iirnotch, filtfilt, welch


def bandpass(sig: np.ndarray, fs: int, low: float = 1.0, high: float = 40.0) -> np.ndarray:
    sos = butter(4, [low, high], btype="bandpass", fs=fs, output="sos")
    return sosfiltfilt(sos, sig, axis=-1)


def notch(sig: np.ndarray, fs: int, freq: float = 50.0, q: float = 30.0) -> np.ndarray:
    b, a = iirnotch(w0=freq, Q=q, fs=fs)
    return filtfilt(b, a, sig, axis=-1)


def epoch(sig: np.ndarray, fs: int, epoch_s: float = 2.0, overlap: float = 0.5) -> np.ndarray:
    """Нарезает на окна с перекрытием. Возврат: (n_epochs, n_channels, n_samples)."""
    win = int(round(epoch_s * fs))
    step = int(round(win * (1.0 - overlap)))
    n = sig.shape[-1]
    starts = range(0, n - win + 1, step)
    return np.stack([sig[:, s:s + win] for s in starts], axis=0)


# порог по размаху подобран под сухие электроды прибора: у них собственный
# дрейф такой, что классические 150 мкВ бракуют почти всё
DEFAULT_PTP_UV = 400.0


def reject_epochs(epochs: np.ndarray, fs: int, ptp_uv: float = DEFAULT_PTP_UV,
                  hf_ratio: float = 0.35) -> np.ndarray:
    """True это принятая эпоха.

    Отбраковка по двум причинам: размах выше ptp_uv (движение, срыв контакта)
    и доля мощности выше 30 Гц больше hf_ratio (мышечный шум челюсти и шеи).
    Эпоха бракуется целиком, если испорчен хотя бы один канал.
    """
    n_epochs = epochs.shape[0]
    keep = np.ones(n_epochs, dtype=bool)
    for i in range(n_epochs):
        block = epochs[i]
        ptp = np.ptp(block, axis=-1)
        if float(ptp.max()) > ptp_uv:
            keep[i] = False
            continue
        freqs, psd = welch(block, fs=fs, nperseg=min(256, block.shape[-1]), axis=-1)
        total = psd[:, (freqs >= 1) & (freqs <= 45)].sum(axis=-1)
        high = psd[:, (freqs > 30) & (freqs <= 45)].sum(axis=-1)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(total > 0, high / total, 1.0)
        if float(np.nanmax(ratio)) > hf_ratio:
            keep[i] = False
    return keep
