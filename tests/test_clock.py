import time

from bridge.clock import SessionClock


def test_clock_starts_near_zero_and_grows():
    clock = SessionClock()
    first = clock.now_s()
    assert 0.0 <= first < 0.05
    time.sleep(0.02)
    assert clock.now_s() > first


def test_clock_is_monotonic_across_calls():
    clock = SessionClock()
    samples = [clock.now_s() for _ in range(200)]
    assert samples == sorted(samples)
