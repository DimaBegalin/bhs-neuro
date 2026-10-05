"""Канал через Mind Tracker на Windows: выбор пути и разбор потока без WinRT."""
import numpy as np
import pytest

from app.device.base import DeviceNotFound
from app.device.win_ble import auto_device
from bridge.headband_protocol import (ADC_TO_MICROVOLTS, RESIST, SIGNAL, STATUS,
                                      contact_from_ohms)
from bridge.win_ble_device import WinBleHeadbandDevice
from tests.test_ble_decode import _build_packet


def _missing(text):
    def factory():
        raise DeviceNotFound(text)
    return factory


def test_auto_prefers_mind_tracker():
    assert auto_device(via_app=lambda: "app", via_sdk=lambda: "sdk") == "app"


def test_auto_falls_back_to_sdk_when_headband_not_connected_to_windows():
    assert auto_device(via_app=_missing("нет у Windows"), via_sdk=lambda: "sdk") == "sdk"


def test_auto_reports_both_reasons():
    with pytest.raises(DeviceNotFound, match="нет у Windows.*Без Mind Tracker: не найден"):
        auto_device(via_app=_missing("нет у Windows"), via_sdk=_missing("не найден"))


def test_auto_does_not_hide_stream_errors_behind_sdk():
    def no_stream():
        raise RuntimeError("сигнал не идёт")
    with pytest.raises(RuntimeError, match="сигнал не идёт"):
        auto_device(via_app=no_stream, via_sdk=lambda: "sdk")


def test_signal_resist_and_battery_are_decoded_like_on_mac():
    device = WinBleHeadbandDevice(connect=False)
    device.connected = True
    chunks = []
    device.start(chunks.append)
    values = np.arange(32).reshape(4, 8) * 1000
    device._on_value(SIGNAL, _build_packet(values))
    assert device.packets_received == 1
    assert np.allclose(chunks[0], values * ADC_TO_MICROVOLTS)

    ohms = [50_000, 4_000_000, 100_000, 2_000_000]   # порядок O1, O2, T3, T4
    device._on_value(RESIST, (1).to_bytes(4, "little")
                     + b"".join(v.to_bytes(4, "little") for v in ohms))
    contact = device.contact()
    assert contact["O1"] == 1.0 and contact["O2"] == contact_from_ohms(4_000_000)
    assert device.last_resist_raw == ohms

    device._on_value(STATUS, bytes([68, 0, 45, 8]))
    assert device.battery() == 68


def test_packets_counted_even_before_session_subscribes():
    device = WinBleHeadbandDevice(connect=False)
    device._on_value(SIGNAL, _build_packet(np.zeros((4, 8))))
    device._on_value(SIGNAL, b"\x00" * 20)        # короткий пакет не считается
    assert device.packets_received == 1
