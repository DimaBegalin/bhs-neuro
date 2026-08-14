import numpy as np
from scipy.signal import welch

from tests.fixtures.synthetic import make_eeg


def test_shape_and_units():
    sig = make_eeg(duration_s=4.0, fs=250, n_channels=4, seed=1)
    assert sig.shape == (4, 1000)
    # амплитуда фонового шума в разумном для ЭЭГ диапазоне, микровольты
    assert 1.0 < float(np.std(sig)) < 100.0


def test_injected_alpha_peak_is_findable():
    sig = make_eeg(duration_s=20.0, fs=250, alpha_hz=10.3, alpha_amp=12.0, seed=2)
    freqs, psd = welch(sig[2], fs=250, nperseg=500, noverlap=250)
    band = (freqs >= 7.0) & (freqs <= 13.0)
    peak = float(freqs[band][np.argmax(psd[band])])
    assert abs(peak - 10.3) < 0.4
