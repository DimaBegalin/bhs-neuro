# -*- coding: utf-8 -*-
"""Платформенно-независимый протокол Bluetooth-ободка."""
import numpy as np

CHANNELS = ["T3", "T4", "O1", "O2"]
SERVICE = "7E400001-B534-F393-68A9-E50E24DCCA95"
STATUS = "7E400002-B534-F393-68A9-E50E24DCCA95"
SIGNAL = "7E400004-B534-F393-68A9-E50E24DCCA95"
RESIST = "7E400005-B534-F393-68A9-E50E24DCCA95"
PULSE = "7E400008-B534-F393-68A9-E50E24DCCA95"
SIDE_KEEP_S = 2400.0
GOOD_RESISTANCE_OHM = 2_000_000.0

HEADER = 4
BLOCK = 13
SAMPLES_PER_PACKET = 8
SIGNAL_PACKET_LEN = HEADER + BLOCK * SAMPLES_PER_PACKET
RESIST_PACKET_LEN = 20
PULSE_PACKET_LEN = 52
RESIST_ORDER = ("O1", "O2", "T3", "T4")
ADC_TO_MICROVOLTS = 2.4 * 1e6 / (6.0 * (1 << 23))


def decode_packet(packet: bytes) -> np.ndarray:
    """Пакет в массив формы (4 канала, 8 отсчётов) в единицах АЦП."""
    if len(packet) < SIGNAL_PACKET_LEN:
        raise ValueError(f"короткий пакет сигнала: {len(packet)} байт")
    out = np.empty((len(CHANNELS), SAMPLES_PER_PACKET), dtype=float)
    for sample in range(SAMPLES_PER_PACKET):
        start = HEADER + sample * BLOCK + 1
        for channel in range(len(CHANNELS)):
            chunk = packet[start + channel * 3:start + (channel + 1) * 3]
            out[channel, sample] = int.from_bytes(chunk, "little", signed=True)
    return out


def decode_resist(data: bytes) -> list[int]:
    if len(data) != RESIST_PACKET_LEN:
        raise ValueError(f"неверный пакет сопротивления: {len(data)} байт")
    return [int.from_bytes(data[4 + i * 4:8 + i * 4], "little")
            for i in range(4)]


def contact_from_ohms(ohms: float) -> float:
    return max(0.0, min(1.0, GOOD_RESISTANCE_OHM / max(float(ohms), 1.0)))
