from analyzer.mirror_profile import (block_windows, calibration_window,
                                     build_mirror_profile)

EVENTS = [
    {"kind": "calibration_eyes_closed_start", "t_s": 0.0, "payload": {}},
    {"kind": "calibration_eyes_open_end", "t_s": 90.0, "payload": {}},
    {"kind": "block_start", "t_s": 100.0, "payload": {"domain": "numeric"}},
    {"kind": "block_end", "t_s": 170.0, "payload": {"domain": "numeric"}},
    {"kind": "block_start", "t_s": 180.0, "payload": {"domain": "spatial"}},
    {"kind": "block_end", "t_s": 250.0, "payload": {"domain": "spatial"}},
]
BEHAVIOR = {d: {"accuracy": 0.8, "median_rt_ms": 1000.0}
            for d in ("numeric", "spatial", "verbal", "working_memory")}


def _track(start, end, focus, load, relax, step=1.0):
    points, t = [], start
    while t <= end:
        points.append({"t_s": t, "focus": focus, "load": load, "relax": relax})
        t += step
    return points


def test_block_windows_are_paired_by_domain():
    windows = block_windows(EVENTS)
    assert windows["numeric"] == (100.0, 170.0)
    assert windows["spatial"] == (180.0, 250.0)


def test_calibration_window_found():
    assert calibration_window(EVENTS) == (0.0, 90.0)


def test_profile_averages_device_values_per_block():
    track = (_track(0, 90, 30, 20, 70)          # покой
             + _track(100, 170, 60, 50, 40)     # числовой блок
             + _track(180, 250, 80, 70, 20))    # пространственный блок
    profile = build_mirror_profile({"session_id": "s1"}, EVENTS, track, BEHAVIOR)
    numeric = next(c for c in profile["domains"] if c["domain"] == "numeric")
    spatial = next(c for c in profile["domains"] if c["domain"] == "spatial")
    assert numeric["focus"] == 60.0
    assert spatial["focus"] == 80.0
    assert profile["rest"]["focus"] == 30.0
    assert numeric["focus_vs_rest"] == 30.0
    assert spatial["focus_vs_rest"] == 50.0


def test_blocks_without_points_are_marked_empty():
    track = _track(0, 90, 30, 20, 70)
    profile = build_mirror_profile({"session_id": "s2"}, EVENTS, track, BEHAVIOR)
    numeric = next(c for c in profile["domains"] if c["domain"] == "numeric")
    assert numeric["focus"] is None
    assert profile["has_device_data"] is False
