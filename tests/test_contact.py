# -*- coding: utf-8 -*-
"""Оценка контакта электродов по сопротивлению."""
import pytest

from bridge.device import GOOD_RESISTANCE_OHM as SDK_THRESHOLD


def _quality(ohms: float) -> float:
    from bridge.ble_device import GOOD_RESISTANCE_OHM
    return max(0.0, min(1.0, GOOD_RESISTANCE_OHM / max(ohms, 1.0)))


def test_both_channels_judge_contact_by_the_same_threshold():
    """Прямой Bluetooth и библиотека производителя должны сходиться.

    Разошлись однажды: мост звал плохими виски на 300-600 кОм, а штатное
    приложение показывало их нормой, и диагност поправлял исправную посадку.
    """
    from bridge.ble_device import GOOD_RESISTANCE_OHM
    assert GOOD_RESISTANCE_OHM == SDK_THRESHOLD


@pytest.mark.parametrize("kohm", [176.6, 227.6, 311.2, 586.7])
def test_dry_electrodes_at_hundreds_of_kiloohms_count_as_good(kohm):
    """Живые показания с визита 13.08: сухие электроды на голове."""
    assert _quality(kohm * 1000) == 1.0


def test_electrode_off_the_head_is_reported_as_lost():
    assert _quality(20_000_000) < 0.2


def test_quality_never_leaves_zero_to_one():
    assert _quality(1) == 1.0
    assert _quality(0) == 1.0
    assert 0.0 <= _quality(1e12) <= 1.0
