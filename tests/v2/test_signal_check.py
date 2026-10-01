import numpy as np

from app.eeg.signal_check import check_recording, judge

FS = 250


def _eeg(seconds: float, alpha_uv: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * FS)) / FS
    sig = rng.normal(0, 15, (4, t.size))
    sig[2:] += alpha_uv * np.sin(2 * np.pi * 10.0 * t)
    return sig


def test_live_eeg_passes_all_checks():
    result = check_recording(_eeg(30, 40, 1), _eeg(30, 8, 2), FS)
    assert result["alpha_reactivity"] > 1.5
    assert 9.5 < result["iaf_hz"] < 10.5
    assert all(v["ok"] for v in judge(result, FS, 249.0, 0.1))


def test_wrong_unit_multiplier_is_caught():
    result = check_recording(_eeg(30, 40, 1) * 1e6, _eeg(30, 8, 2) * 1e6, FS)
    verdicts = {v["name"]: v["ok"] for v in judge(result, FS, 249.0, 0.1)}
    assert not verdicts["Единицы сигнала"]


def test_noise_without_alpha_shows_no_reactivity():
    result = check_recording(_eeg(30, 0, 1), _eeg(30, 0, 2), FS)
    verdicts = {v["name"]: v["ok"] for v in judge(result, FS, 249.0, 0.1)}
    assert not verdicts["Реакция альфы на закрытые глаза"]


def test_lost_packets_and_gaps_are_caught():
    result = check_recording(_eeg(30, 40, 1), _eeg(30, 8, 2), FS)
    verdicts = {v["name"]: v["ok"] for v in judge(result, FS, 200.0, 1.2)}
    assert not verdicts["Частота и полнота потока"]
    assert not verdicts["Разрывы потока"]
