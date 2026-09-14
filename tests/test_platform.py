"""Выбор канала и системных путей по платформе: macOS и Windows живут в одном коде."""
import os

from bridge.main import default_channel, headband_class


def test_default_channel_per_platform():
    assert default_channel("darwin") == "ble"
    assert default_channel("win32") == "sdk"
    assert default_channel("linux") == "sdk"


def test_headband_class_bleak_outside_macos():
    cls = headband_class("ble", platform="win32")
    assert cls.__name__ == "BleakHeadbandDevice"


def test_headband_class_sdk_everywhere():
    assert headband_class("sdk", platform="win32").__name__ == "BrainBitDevice"
    assert headband_class("sdk", platform="darwin").__name__ == "BrainBitDevice"


def test_windows_browser_candidates(monkeypatch):
    from report import to_pdf
    monkeypatch.setenv("PROGRAMFILES", r"C:\Program Files")
    monkeypatch.setenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\u\AppData\Local")
    paths = to_pdf._windows_candidates()
    assert any(p.endswith("msedge.exe") for p in paths)
    assert any(p.startswith(r"C:\Program Files (x86)") for p in paths)


def test_mind_db_find_returns_none_without_file(monkeypatch):
    from bridge import mind_db
    monkeypatch.setattr(mind_db, "DB_CANDIDATES", (os.path.join("нет", "такой", "data.mdb"),))
    assert mind_db.find_db() is None


def test_sdk_device_has_watchdog_contract():
    from bridge.device import BrainBitDevice
    assert callable(BrainBitDevice.watchdog)
