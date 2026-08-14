import numpy as np
import pytest

from analyzer.profile import (zscores, build_domain_map, quality_verdict,
                              build_profile, METHOD_VERSION)

DOMAINS = ["numeric", "spatial", "verbal", "working_memory"]


def _blocks(accs, erds, thetas):
    out = {}
    for name, acc, erd, th in zip(DOMAINS, accs, erds, thetas):
        out[name] = {
            "behavior": {"accuracy": acc, "median_rt_ms": 1000.0, "rt_sd_ms": 100.0,
                         "fast_guess_share": 0.0, "stall_share": 0.0, "n_trials": 12},
            "neuro": {"erd_alpha_high": erd, "erd_alpha_low": erd / 2,
                      "theta_rise": th, "engagement": 0.5, "attention_slope": -0.01,
                      "epochs_total": 69, "epochs_rejected": 4},
        }
    return out


def test_zscores_are_centered():
    z = zscores([1.0, 2.0, 3.0, 4.0])
    assert abs(float(z.mean())) < 1e-9
    assert z[0] < 0 < z[-1]


def test_zscores_constant_input_gives_zeros():
    assert np.allclose(zscores([5.0, 5.0, 5.0, 5.0]), 0.0)


def test_strong_domain_is_high_accuracy_low_cost():
    blocks = _blocks(accs=[0.6, 0.95, 0.55, 0.7],
                     erds=[-45.0, -12.0, -50.0, -30.0],
                     thetas=[40.0, 5.0, 45.0, 20.0])
    cards = build_domain_map(blocks)
    best = max(cards, key=lambda c: c["efficiency"])
    worst = min(cards, key=lambda c: c["efficiency"])
    assert best["domain"] == "spatial"
    assert worst["domain"] == "verbal"
    assert {c["domain"] for c in cards} == set(DOMAINS)


def test_quality_verdict_rejects_bad_calibration():
    ok, reasons = quality_verdict(0.7, {d: 0.1 for d in DOMAINS}, iaf=10.2)
    assert ok is False
    assert any("калибров" in r for r in reasons)


def test_quality_verdict_rejects_missing_iaf():
    ok, reasons = quality_verdict(0.1, {d: 0.1 for d in DOMAINS}, iaf=None)
    assert ok is False
    assert any("пик" in r for r in reasons)


def test_quality_verdict_accepts_clean_session():
    ok, reasons = quality_verdict(0.12, {d: 0.2 for d in DOMAINS}, iaf=10.2)
    assert ok is True and reasons == []


def test_profile_without_neuro_when_quality_low():
    blocks = _blocks([0.7] * 4, [-30.0] * 4, [20.0] * 4)
    for d in DOMAINS:
        blocks[d]["neuro"]["epochs_rejected"] = 60
        blocks[d]["neuro"]["epochs_total"] = 69
    profile = build_profile(session_meta={"session_id": "s1", "lang": "ru"},
                            iaf=10.2, prominence=3.0,
                            bands={"theta": (4.2, 6.2)}, blocks=blocks)
    assert profile["has_eeg"] is False
    assert profile["domains"][0]["efficiency"] is None
    assert profile["method_version"] == METHOD_VERSION
    assert profile["quality"]["reasons"]


def test_profile_keeps_neuro_when_clean():
    blocks = _blocks([0.6, 0.95, 0.55, 0.7], [-45.0, -12.0, -50.0, -30.0],
                     [40.0, 5.0, 45.0, 20.0])
    profile = build_profile(session_meta={"session_id": "s2", "lang": "kk"},
                            iaf=10.2, prominence=3.0,
                            bands={"theta": (4.2, 6.2)}, blocks=blocks)
    assert profile["has_eeg"] is True
    assert profile["iaf"] == pytest.approx(10.2)
    assert all(c["efficiency"] is not None for c in profile["domains"])
