import numpy as np

from analyzer.preprocess import epoch, reject_epochs
from analyzer.spectra import psd_of_epochs, band_power
from tests.fixtures.synthetic import make_eeg

FS = 250


def test_psd_shapes():
    sig = make_eeg(duration_s=20.0, fs=FS, seed=7)
    eps = epoch(sig, fs=FS)
    freqs, psd = psd_of_epochs(eps, fs=FS)
    assert psd.shape[0] == 4
    assert freqs.shape[0] == psd.shape[1]
    assert freqs[0] == 0.0


def test_band_power_higher_where_alpha_injected():
    sig = make_eeg(duration_s=20.0, fs=FS, alpha_hz=10.0, alpha_amp=15.0, seed=8)
    eps = epoch(sig, fs=FS)
    freqs, psd = psd_of_epochs(eps, fs=FS)
    alpha = band_power(freqs, psd, 8.0, 12.0)
    beta = band_power(freqs, psd, 20.0, 30.0)
    # альфа вложена только в затылочные каналы, индексы 2 и 3
    assert alpha[2] > beta[2] * 5
    assert alpha[3] > beta[3] * 5
    assert alpha[0] < alpha[2]


def test_keep_mask_is_respected():
    sig = make_eeg(duration_s=20.0, fs=FS, seed=9)
    eps = epoch(sig, fs=FS)
    keep = reject_epochs(eps, fs=FS)
    keep[:5] = False
    freqs, psd_all = psd_of_epochs(eps, fs=FS)
    _, psd_kept = psd_of_epochs(eps, fs=FS, keep=keep)
    assert not np.allclose(psd_all, psd_kept)
