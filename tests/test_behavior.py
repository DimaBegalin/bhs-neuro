import pytest

from analyzer.behavior import block_behavior


def test_basic_counts():
    trials = [
        {"correct": True, "rt_ms": 1000},
        {"correct": True, "rt_ms": 1200},
        {"correct": False, "rt_ms": 900},
        {"correct": True, "rt_ms": 1100},
    ]
    m = block_behavior(trials)
    assert m["n_trials"] == 4
    assert m["accuracy"] == pytest.approx(0.75)
    assert m["median_rt_ms"] == pytest.approx(1050.0)
    assert m["rt_sd_ms"] > 0


def test_fast_guess_and_stall_shares():
    trials = [
        {"correct": False, "rt_ms": 200},   # быстрое угадывание
        {"correct": True, "rt_ms": 1000},
        {"correct": True, "rt_ms": 1000},
        {"correct": True, "rt_ms": 1000},
        {"correct": False, "rt_ms": 5000},  # залипание, больше трёх медиан
    ]
    m = block_behavior(trials)
    assert m["fast_guess_share"] == pytest.approx(0.2)
    assert m["stall_share"] == pytest.approx(0.2)


def test_empty_block_returns_zeros_not_crash():
    m = block_behavior([])
    assert m["n_trials"] == 0
    assert m["accuracy"] == 0.0
    assert m["median_rt_ms"] == 0.0
