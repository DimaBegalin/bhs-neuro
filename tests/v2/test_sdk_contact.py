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
