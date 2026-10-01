import json

import numpy as np

from app.session.recorder import SessionRecorder, recover


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def test_events_carry_sample_index_and_signal_round_trips(tmp_path):
    clock = Clock()
    rec = SessionRecorder(tmp_path, fs=250, clock=clock)
    signal = np.arange(4 * 3000, dtype=float).reshape(4, 3000)
    for start in range(0, 1500, 50):
        rec.on_chunk(signal[:, start:start + 50])
    clock.t = 6.0
    event = rec.mark("card_show", {"card": "R1"})
    for start in range(1500, 3000, 50):
        rec.on_chunk(signal[:, start:start + 50])
    assert event["sample"] == 1500 and event["t_s"] == 6.0
    npz, events = rec.finish()
    data = np.load(npz)
    assert int(data["fs"]) == 250
    np.testing.assert_allclose(data["signal"], signal.astype(np.float32))
    assert json.loads(events.read_text(encoding="utf-8"))[0]["payload"] == {"card": "R1"}
    assert not (tmp_path / "signal.part").exists()


def test_crash_leaves_recoverable_part_files(tmp_path):
    rec = SessionRecorder(tmp_path, fs=250)
    for _ in range(40):  # 40 × 50 = 2000 отсчётов = 8 с, сброс на диск был
        rec.on_chunk(np.ones((4, 50)))
    rec.mark("background_start")
    del rec  # программа «упала»: finish не вызван
    assert recover(tmp_path, 250)
    data = np.load(tmp_path / "signal.npz")
    assert data["signal"].shape == (4, 1250)  # сброшено на диск до «падения»
    assert json.loads((tmp_path / "events.json").read_text(encoding="utf-8"))[0]["kind"] == "background_start"


def test_without_headband_events_have_no_sample(tmp_path):
    rec = SessionRecorder(tmp_path, fs=None)
    rec.on_chunk(np.ones((4, 50)))
    assert rec.mark("x")["sample"] is None
    npz, _ = rec.finish()
    assert npz is None
