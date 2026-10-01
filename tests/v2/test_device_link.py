import numpy as np

from app.device.base import DeviceNotFound
from app.device.link import DeviceLink, channel_quality
from tests.v2.conftest import wait_until


class StubDevice:
    fs = 250
    name = "stub"

    def __init__(self):
        self.connected = True
        self.on_chunk = None
        self.restarts = 0
        self.closed = False

    def start(self, on_chunk):
        self.on_chunk = on_chunk

    def stop(self):
        pass

    def close(self):
        self.closed = True

    def contact(self):
        return {c: 1.0 for c in ("T3", "T4", "O1", "O2")}

    def battery(self):
        return 77

    def restart_stream(self):
        self.restarts += 1

    def push(self, sd=20.0, n=50):
        self.on_chunk(np.random.default_rng(0).normal(0, sd, (4, n)))


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _linked(device, clock=None):
    link = DeviceLink(lambda: device, stall_s=5.0, clock=clock or Clock(), watch=False)
    link.connect()
    assert wait_until(lambda: link.snapshot()["state"] == "streaming")
    return link


def test_chunks_reach_listeners_and_quality_is_good():
    device = StubDevice()
    link = _linked(device)
    got = []
    link.add_listener(got.append)
    for _ in range(12):
        device.push()
    snap = link.snapshot()
    assert len(got) == 12
    assert snap["packets"] == 12 and snap["battery"] == 77
    assert set(snap["quality"].values()) == {"good"}
    link.disconnect()
    assert device.closed


def test_silent_stream_is_restarted_once_then_declared_lost():
    clock, device = Clock(), StubDevice()
    link = _linked(device, clock)
    clock.t = 6.0
    link.check()
    assert link.snapshot()["state"] == "stalled" and device.restarts == 1
    clock.t = 8.0
    link.check()
    assert device.restarts == 1
    clock.t = 11.5
    link.check()
    assert link.snapshot()["state"] == "lost"


def test_stream_recovers_after_restart():
    clock, device = Clock(), StubDevice()
    link = _linked(device, clock)
    clock.t = 6.0
    link.check()
    device.push()
    assert link.snapshot()["state"] == "streaming"


def test_device_reporting_lost_connection():
    device = StubDevice()
    link = _linked(device)
    device.connected = False
    link.check()
    assert link.snapshot()["state"] == "lost"


def test_not_found_becomes_error_with_message():
    def factory():
        raise DeviceNotFound("прибор не найден")
    link = DeviceLink(factory)
    link.connect()
    assert wait_until(lambda: link.snapshot()["state"] == "error")
    assert "не найден" in link.snapshot()["message"]


def test_channel_quality_flat_and_noisy():
    rng = np.random.default_rng(1)
    window = rng.normal(0, 20, (4, 500))
    window[0] = 0.0
    window[1] *= 10
    q = channel_quality(window, {"T3": 1, "T4": 1, "O1": 1, "O2": 0.1})
    assert q == {"T3": "flat", "T4": "noisy", "O1": "good", "O2": "flat"}
