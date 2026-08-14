import numpy as np
import pytest

from analyzer.preprocess import epoch
from analyzer.spectra import psd_of_epochs
from analyzer.iaf import compute_iaf, bands_from_iaf
from tests.fixtures.synthetic import make_eeg

FS = 250


@pytest.mark.parametrize("true_iaf", [8.4, 9.7, 10.3, 11.6])
def test_iaf_recovered_from_synthetic(true_iaf):
    sig = make_eeg(duration_s=60.0, fs=FS, alpha_hz=true_iaf, alpha_amp=14.0, seed=11)
    freqs, psd = psd_of_epochs(epoch(sig, fs=FS), fs=FS)
    iaf, prominence = compute_iaf(freqs, psd)
    assert iaf is not None
    assert abs(iaf - true_iaf) < 0.35
    assert prominence > 1.5


def test_iaf_none_when_no_peak():
    sig = make_eeg(duration_s=60.0, fs=FS, alpha_amp=0.0, seed=12)
    freqs, psd = psd_of_epochs(epoch(sig, fs=FS), fs=FS)
    iaf, prominence = compute_iaf(freqs, psd)
    assert iaf is None


def test_bands_are_derived_from_iaf():
    bands = bands_from_iaf(10.0)
    assert bands["theta"] == (4.0, 6.0)
    assert bands["alpha_low"] == (6.0, 8.0)
    assert bands["alpha_high"] == (8.0, 12.0)
    assert bands["beta"] == (12.0, 30.0)


def test_bands_clipped_at_one_hz():
    bands = bands_from_iaf(6.5)
    assert bands["theta"][0] == 1.0
