"""Синтетический ЭЭГ для тестов: розовый шум плюс управляемый альфа-пик."""
import numpy as np

CHANNELS = ("T3", "T4", "O1", "O2")


def _pink_noise(n_samples: int, rng: np.random.Generator) -> np.ndarray:
    """Шум со спектром 1/f, грубая модель фона ЭЭГ."""
    white = rng.normal(size=n_samples)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n_samples, d=1.0)
    freqs[0] = freqs[1]
    spectrum = spectrum / np.sqrt(freqs)
    out = np.fft.irfft(spectrum, n=n_samples)
    return out / np.std(out)


def make_eeg(
    duration_s: float,
    fs: int = 250,
    alpha_hz: float | None = None,
    alpha_amp: float = 0.0,
    n_channels: int = 4,
    seed: int = 0,
    occipital_only: bool = True,
) -> np.ndarray:
    """Сигнал формы (n_channels, n_samples) в микровольтах.

    alpha_hz задаёт частоту синусоиды, alpha_amp её амплитуду в мкВ.
    occipital_only кладёт альфу только в O1 и O2, как в реальном ЭЭГ.
    """
    rng = np.random.default_rng(seed)
    n_samples = int(round(duration_s * fs))
    t = np.arange(n_samples) / fs
    out = np.empty((n_channels, n_samples), dtype=float)
    for ch in range(n_channels):
        out[ch] = _pink_noise(n_samples, rng) * 8.0
        if alpha_hz is not None and alpha_amp > 0:
            is_occipital = CHANNELS[ch] in ("O1", "O2")
            if is_occipital or not occipital_only:
                phase = rng.uniform(0, 2 * np.pi)
                out[ch] += alpha_amp * np.sin(2 * np.pi * alpha_hz * t + phase)
    return out


def add_artifact(sig: np.ndarray, fs: int, start_s: float, dur_s: float,
                 amp: float = 400.0, channel: int | None = None) -> np.ndarray:
    """Вставляет высокоамплитудный кусок, имитируя движение или плохой контакт."""
    out = sig.copy()
    a = int(start_s * fs)
    b = a + int(dur_s * fs)
    rows = range(out.shape[0]) if channel is None else [channel]
    for ch in rows:
        out[ch, a:b] += np.random.default_rng(ch).normal(0, amp, size=b - a)
    return out
