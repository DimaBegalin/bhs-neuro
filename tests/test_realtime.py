import numpy as np

from bridge.realtime import RealtimeMetrics
from analyzer.iaf import bands_from_iaf
from analyzer.spectra import psd_of_epochs
from analyzer.preprocess import epoch
from tests.fixtures.synthetic import make_eeg

FS = 250
BANDS = bands_from_iaf(10.0)


def _baseline(alpha_amp=14.0):
    sig = make_eeg(duration_s=30.0, fs=FS, alpha_hz=10.0, alpha_amp=alpha_amp, seed=41)
    return psd_of_epochs(epoch(sig, fs=FS), fs=FS)


def _feed(rt, alpha_amp, seconds=10.0, seed=42):
    sig = make_eeg(duration_s=seconds, fs=FS, alpha_hz=10.0, alpha_amp=alpha_amp, seed=seed)
    for start in range(0, sig.shape[1], 50):
        rt.push(sig[:, start:start + 50])


def test_snapshot_is_empty_before_enough_data():
    rt = RealtimeMetrics(fs=FS)
    rt.set_bands(BANDS)
    assert rt.snapshot()["focus"] is None


def test_relax_above_fifty_when_alpha_higher_than_baseline():
    rt = RealtimeMetrics(fs=FS)
    rt.set_bands(BANDS)
    rt.set_baseline(*_baseline(alpha_amp=8.0))
    _feed(rt, alpha_amp=20.0)
    snap = rt.snapshot()
    assert snap["relax"] > 50.0
    assert snap["focus"] < 50.0


def test_focus_above_fifty_when_alpha_suppressed():
    rt = RealtimeMetrics(fs=FS)
    rt.set_bands(BANDS)
    rt.set_baseline(*_baseline(alpha_amp=18.0))
    _feed(rt, alpha_amp=3.0)
    snap = rt.snapshot()
    assert snap["focus"] > 50.0
    assert snap["relax"] < 50.0


def test_artifact_keeps_last_value_and_marks_stale():
    rt = RealtimeMetrics(fs=FS)
    rt.set_bands(BANDS)
    rt.set_baseline(*_baseline())
    _feed(rt, alpha_amp=14.0)
    good = rt.snapshot()
    rng = np.random.default_rng(7)
    # артефакт должен заполнить всё окно анализа, иначе фильтр его сгладит
    for _ in range(80):
        rt.push(rng.normal(0, 900.0, size=(4, 50)))
    bad = rt.snapshot()
    assert bad["stale"] is True
    assert bad["focus"] == good["focus"]
