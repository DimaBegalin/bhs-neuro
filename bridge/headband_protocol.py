# -*- coding: utf-8 -*-
"""Протокол ободка по Bluetooth: идентификаторы и разбор пакетов.

Вынесен отдельно, потому что читателей у прибора два: CoreBluetooth на macOS
и bleak на Windows. Байты у них одни и те же, различается только способ
подписаться на них, поэтому разбор живёт здесь, а системные обёртки
импортируют его. Модуль не тянет ничего платформенного и грузится везде,
в том числе в тестах.

Формат разобран 12.08.2026 на живом приборе:
пакет 108 байт это 4 байта счётчика (шаг 8) и восемь блоков по 13 байт,
в каждом блоке служебный байт и четыре значения по 3 байта little-endian
со знаком, порядок каналов T3, T4, O1, O2.
"""
import numpy as np

CHANNELS = ["T3", "T4", "O1", "O2"]
SERVICE = "7E400001-B534-F393-68A9-E50E24DCCA95"
STATUS = "7E400002-B534-F393-68A9-E50E24DCCA95"
COMMAND = "7E400003-B534-F393-68A9-E50E24DCCA95"
SIGNAL = "7E400004-B534-F393-68A9-E50E24DCCA95"
RESIST = "7E400005-B534-F393-68A9-E50E24DCCA95"
PULSE = "7E400008-B534-F393-68A9-E50E24DCCA95"
# имя, под которым прибор представляется в эфире
DEVICE_NAME = "Headband"
SIDE_KEEP_S = 2400.0
# порог хорошего контакта, тот же, что у библиотеки производителя в device.py.
# Стояло 150 кОм, и это была наша выдумка: сухие электроды дают сотни килоом
# даже на правильной посадке, поэтому мост звал плохими виски, которые
# штатное приложение считало нормой, и диагност поправлял то, что не сломано
GOOD_RESISTANCE_OHM = 2_000_000.0

HEADER = 4
BLOCK = 13
SAMPLES_PER_PACKET = 8
SIGNAL_PACKET_LEN = HEADER + BLOCK * SAMPLES_PER_PACKET
RESIST_PACKET_LEN = 20
PULSE_PACKET_LEN = 52
# порядок каналов в пакете сопротивления отличается от порядка сигнала
RESIST_ORDER = ("O1", "O2", "T3", "T4")
# отсчёты приходят сырыми значениями 24-битного АЦП
ADC_TO_MICROVOLTS = 2.4 * 1e6 / (6.0 * (1 << 23))


def decode_packet(packet: bytes) -> np.ndarray:
    """Пакет в массив формы (4 канала, 8 отсчётов) в сырых единицах АЦП."""
    out = np.empty((len(CHANNELS), SAMPLES_PER_PACKET), dtype=float)
    for s in range(SAMPLES_PER_PACKET):
        start = HEADER + s * BLOCK + 1
        for c in range(len(CHANNELS)):
            chunk = packet[start + c * 3: start + (c + 1) * 3]
            out[c, s] = int.from_bytes(chunk, "little", signed=True)
    return out


def decode_resist(data: bytes) -> list[int]:
    """Четыре сопротивления в омах в порядке пакета: O1, O2, T3, T4."""
    return [int.from_bytes(data[4 + i * 4: 8 + i * 4], "little") for i in range(4)]


def contact_from_ohms(ohms: float) -> float:
    """Качество контакта от 0 до 1 по сопротивлению электрода."""
    return max(0.0, min(1.0, GOOD_RESISTANCE_OHM / max(float(ohms), 1.0)))


def contact_from_resist(data: bytes) -> dict:
    """Пакет сопротивления в качество контакта по каналам, в порядке сигнала."""
    return {name: contact_from_ohms(ohms)
            for name, ohms in zip(RESIST_ORDER, decode_resist(data))}
