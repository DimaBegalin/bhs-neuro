import json

import numpy as np

from bridge.recorder import Recorder


def test_save_writes_npz_and_events(tmp_path):
    rec = Recorder(fs=250)
    rec.push_samples(np.zeros((4, 500)), t0_s=0.0)
    rec.push_samples(np.ones((4, 500)), t0_s=2.0)
    rec.push_event("calibration_eyes_closed_start", {}, t_s=0.1)
    rec.push_event("block_start", {"domain": "numeric"}, t_s=90.0)

    npz_path, events_path = rec.save(tmp_path)

    data = np.load(npz_path)
    assert data["signal"].shape == (4, 1000)
    assert int(data["fs"]) == 250
    assert list(data["channels"]) == ["T3", "T4", "O1", "O2"]

    events = json.loads(open(events_path, encoding="utf-8").read())
    assert len(events) == 2
    assert events[1]["kind"] == "block_start"
    assert events[1]["payload"]["domain"] == "numeric"
    assert events[1]["t_s"] == 90.0


def test_events_are_sorted_by_time(tmp_path):
    rec = Recorder(fs=250)
    rec.push_event("late", {}, t_s=10.0)
    rec.push_event("early", {}, t_s=1.0)
    _, events_path = rec.save(tmp_path)
    events = json.loads(open(events_path, encoding="utf-8").read())
    assert [e["kind"] for e in events] == ["early", "late"]
