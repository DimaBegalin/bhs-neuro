from tools.pilot_report import convergence


def _profile(pairs, has_eeg=True):
    domains = []
    for name, (accuracy, cost) in pairs.items():
        domains.append({"domain": name, "accuracy": accuracy, "cost": cost,
                        "median_rt_ms": 1000.0, "efficiency": 0.0,
                        "attention_slope": -0.01})
    return {"has_eeg": has_eeg, "domains": domains,
            "quality": {"reasons": [] if has_eeg else ["сигнал"]}}


CONSISTENT = _profile({"numeric": (0.6, 0.8), "spatial": (0.9, -0.9),
                       "verbal": (0.5, 1.0), "working_memory": (0.8, -0.9)})
INCONSISTENT = _profile({"numeric": (0.6, -0.8), "spatial": (0.9, 0.9),
                         "verbal": (0.5, -1.0), "working_memory": (0.8, 0.9)})


def test_consistent_sessions_give_negative_direction():
    result = convergence([CONSISTENT] * 10)
    assert result["n_sessions"] == 10
    assert result["mean_within_child_correlation"] < -0.5
    assert result["share_negative_direction"] == 1.0
    assert result["verdict"] == "оставить нейро-слой"


def test_inconsistent_sessions_flag_the_problem():
    result = convergence([INCONSISTENT] * 10)
    assert result["mean_within_child_correlation"] > 0
    assert result["verdict"] == "отключить нейро-слой"


def test_sessions_without_eeg_counted_but_not_correlated():
    result = convergence([CONSISTENT] * 7 + [_profile({"numeric": (0.6, 0.0)}, has_eeg=False)] * 3)
    assert result["n_sessions"] == 10
    assert result["n_with_eeg"] == 7
    assert result["quality_share"] == 0.7


def test_verdict_is_negative_when_quality_is_low():
    """Даже при идеальной сходимости плохой сигнал закрывает нейро-слой."""
    result = convergence([CONSISTENT] * 5 + [_profile({"numeric": (0.6, 0.0)}, has_eeg=False)] * 5)
    assert result["quality_share"] == 0.5
    assert result["verdict"] == "отключить нейро-слой"
