"""Контакт ободка через SDK, когда SDK не разбирает пакеты сопротивления."""
from types import SimpleNamespace

from bridge.device import CHANNELS, BrainBitDevice


def _device():
    device = object.__new__(BrainBitDevice)   # без поиска прибора
    device._contact = {name: 0.0 for name in CHANNELS}
    return device


def test_unknown_contact_does_not_mark_all_channels_flat():
    assert _device().contact() == {name: 1.0 for name in CHANNELS}


def test_contact_follows_resistance_once_it_arrives():
    device = _device()
    ohms = {"T3": 50_000.0, "T4": 4_000_000.0, "O1": 100_000.0, "O2": 2_000_000.0}
    device._handle_resist(None, [SimpleNamespace(**ohms)])
    contact = device.contact()
    assert contact["T3"] == 1.0 and contact["T4"] == 0.5


class FakeSdk:
    def __init__(self, scan_seconds=15.0):
        self.fs, self.connected, self.info = 250, True, SimpleNamespace(Name="Headband")
        self._streaming, self._on_chunk, self.log = False, None, []

    def start(self, on_chunk):
        self._on_chunk = on_chunk
        if not self._streaming:
            self._streaming = True
            self.log.append("start")

    def stop(self):
        self._streaming = False
        self.log.append("stop")

    def watchdog(self):
        self.log.append("watchdog")

    def close(self):
        self.log.append("close")

    def contact(self):
        return {name: 0.3 for name in CHANNELS}

    def battery(self):
        return 42


class FakeRaw:
    trace = ["подписка 0004: SUCCESS"]

    def __init__(self, wait_s=5.0):
        self.connected, self._on_chunk, self.resubscribed = True, None, 0

    def start(self, on_chunk):
        self._on_chunk = on_chunk

    def stop(self):
        self._on_chunk = None

    def watchdog(self):
        self.resubscribed += 1

    def close(self):
        pass

    def contact(self):
        return {name: 0.9 for name in CHANNELS}


def _sdk(monkeypatch, raw_cls):
    import bridge.device
    import bridge.win_ble_device
    from app.device.sdk import SdkDevice
    monkeypatch.setattr(bridge.device, "BrainBitDevice", FakeSdk)
    monkeypatch.setattr(bridge.win_ble_device, "WinBleHeadbandDevice", raw_cls)
    return SdkDevice(raw=True)


def test_sdk_starts_stream_and_raw_packets_feed_the_session(monkeypatch):
    device = _sdk(monkeypatch, FakeRaw)
    assert device.source == "sdk+raw"
    assert device._device.log == ["start"]          # поток запущен командой SDK
    got = []
    device.start(got.append)
    device.raw._on_chunk("chunk")
    assert got == ["chunk"]
    assert device.contact()["O1"] == 0.9            # сопротивление из сырых пакетов
    assert device.battery() == 42


def test_falls_back_to_sdk_stream_when_raw_subscription_fails(monkeypatch):
    class Denied(FakeRaw):
        def __init__(self, wait_s=5.0):
            raise RuntimeError("SHARING_VIOLATION")
    device = _sdk(monkeypatch, Denied)
    assert device.source == "sdk" and "SHARING_VIOLATION" in device.raw_error
    assert device._device.log == ["start", "stop"]  # SDK вернули в исходное состояние
    got = []
    device.start(got.append)
    assert device._device._streaming and device._device._on_chunk == got.append


def test_restart_keeps_session_listener(monkeypatch):
    device = _sdk(monkeypatch, FakeRaw)
    got = []
    device.start(got.append)
    device.restart_stream()
    assert "watchdog" in device._device.log and device.raw.resubscribed == 1
    device.raw._on_chunk("after")
    assert got == ["after"]
