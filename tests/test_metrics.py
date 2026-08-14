import numpy as np

from analyzer.preprocess import epoch, reject_epochs
from analyzer.spectra import psd_of_epochs
from analyzer.iaf import bands_from_iaf
from analyzer.metrics import (erd_percent, engagement_index, attention_slope,
                              block_neuro_metrics)
from tests.fixtures.synthetic import make_eeg

FS = 250
BANDS = bands_from_iaf(10.0)


def test_erd_is_negative_when_power_drops():
    assert erd_percent(50.0, 100.0) == -50.0
    assert erd_percent(150.0, 100.0) == 50.0


def test_erd_handles_zero_baseline():
    assert erd_percent(10.0, 0.0) == 0.0


def test_engagement_rises_when_alpha_falls():
    calm = make_eeg(duration_s=20.0, fs=FS, alpha_hz=10.0, alpha_amp=18.0, seed=21)
    busy = make_eeg(duration_s=20.0, fs=FS, alpha_hz=10.0, alpha_amp=4.0, seed=21)
    f_c, p_c = psd_of_epochs(epoch(calm, fs=FS), fs=FS)
    f_b, p_b = psd_of_epochs(epoch(busy, fs=FS), fs=FS)
    assert engagement_index(f_b, p_b, BANDS) > engagement_index(f_c, p_c, BANDS)


def test_attention_slope_sign():
    times = np.arange(10, dtype=float)
    assert attention_slope(np.linspace(1.0, 0.5, 10), times) < 0
    assert attention_slope(np.linspace(0.5, 1.0, 10), times) > 0
    assert abs(attention_slope(np.ones(10), times)) < 1e-9


def test_block_metrics_detect_alpha_desync():
    base = make_eeg(duration_s=30.0, fs=FS, alpha_hz=10.0, alpha_amp=18.0, seed=22)
    task = make_eeg(duration_s=70.0, fs=FS, alpha_hz=10.0, alpha_amp=6.0, seed=23)
    base_eps = epoch(base, fs=FS)
    base_pack = psd_of_epochs(base_eps, fs=FS, keep=reject_epochs(base_eps, fs=FS))
    task_eps = epoch(task, fs=FS)
    keep = reject_epochs(task_eps, fs=FS)
    m = block_neuro_metrics(task_eps, base_pack, fs=FS, bands=BANDS, keep=keep)
    assert m["erd_alpha_high"] < -30.0
    assert m["epochs_total"] == task_eps.shape[0]
    assert m["epochs_rejected"] == int((~keep).sum())
    assert set(m) == {"erd_alpha_high", "erd_alpha_low", "theta_rise", "engagement",
                      "attention_slope", "epochs_total", "epochs_rejected"}
