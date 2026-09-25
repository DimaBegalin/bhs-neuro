# -*- coding: utf-8 -*-
"""Платформенные решения не должны импортировать чужие системные модули."""
import pytest

from bridge.main import default_channel, headband_class


def test_windows_uses_manufacturer_sdk_by_default():
    assert default_channel("win32") == "sdk"
    assert default_channel("linux") == "sdk"
    assert default_channel("darwin") == "ble"


def test_windows_does_not_try_to_import_macos_bluetooth():
    cls = headband_class("sdk", "win32")
    assert cls.__name__ == "BrainBitDevice"
    with pytest.raises(RuntimeError, match="Windows"):
        headband_class("ble", "win32")
