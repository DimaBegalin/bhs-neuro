import numpy as np

from analyzer.preprocess import bandpass, notch, epoch, reject_epochs
from tests.fixtures.synthetic import make_eeg, add_artifact

FS = 250


def test_epoch_shapes_with_overlap():
    sig = make_eeg(duration_s=10.0, fs=FS, seed=3)
    eps = epoch(sig, fs=FS, epoch_s=2.0, overlap=0.5)
    # шаг 1 секунда, окно 2 секунды: 9 полных окон в 10 секундах
    assert eps.shape == (9, 4, 500)


def test_notch_kills_50hz():
    t = np.arange(FS * 8) / FS
    sig = make_eeg(duration_s=8.0, fs=FS, seed=4)
    sig = sig + 30.0 * np.sin(2 * np.pi * 50.0 * t)
    cleaned = notch(sig, fs=FS, freq=50.0)
    from scipy.signal import welch
    f, p_before = welch(sig[0], fs=FS, nperseg=500)
    _, p_after = welch(cleaned[0], fs=FS, nperseg=500)
    idx = int(np.argmin(np.abs(f - 50.0)))
    assert p_after[idx] < p_before[idx] * 0.05


def test_bandpass_keeps_alpha_removes_drift():
    sig = make_eeg(duration_s=8.0, fs=FS, alpha_hz=10.0, alpha_amp=15.0, seed=5)
    drift = np.linspace(0, 300, sig.shape[1])
    cleaned = bandpass(sig + drift, fs=FS, low=1.0, high=40.0)
    assert abs(float(np.mean(cleaned[2]))) < 1.0
    from scipy.signal import welch
    f, p = welch(cleaned[2], fs=FS, nperseg=500)
    band = (f >= 8) & (f <= 12)
    assert p[band].max() > p[(f >= 20) & (f <= 30)].max()


def test_reject_epochs_marks_artifact_window():
    sig = make_eeg(duration_s=12.0, fs=FS, seed=6)
    sig = add_artifact(sig, fs=FS, start_s=4.0, dur_s=2.0, amp=400.0)
    eps = epoch(sig, fs=FS)
    keep = reject_epochs(eps, fs=FS)
    assert keep.dtype == bool and keep.shape == (11,)
    # эпохи, попавшие на артефакт, отбракованы
    assert not keep[3:6].any()
    # чистые эпохи в начале записи приняты
    assert keep[0:2].all()
