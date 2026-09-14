"""Общий разбор пакетов ободка: им пользуются оба Bluetooth-канала."""
import numpy as np

from bridge.headband_protocol import (
    CHANNELS, RESIST_ORDER, SAMPLES_PER_PACKET, SIGNAL_PACKET_LEN,
    contact_from_ohms, contact_from_resist, decode_packet, decode_resist)


def build_signal_packet(values, counter: int = 0) -> bytes:
    """values формы (4 канала, 8 отсчётов) в сырых единицах АЦП."""
    packet = bytearray(counter.to_bytes(4, "little"))
    for s in range(SAMPLES_PER_PACKET):
        packet += b"\x00"
        for c in range(len(CHANNELS)):
            packet += int(values[c][s]).to_bytes(3, "little", signed=True)
    return bytes(packet)


def build_resist_packet(ohms, counter: int = 0) -> bytes:
    """ohms в порядке пакета: O1, O2, T3, T4."""
    packet = bytearray(counter.to_bytes(4, "little"))
    for value in ohms:
        packet += int(value).to_bytes(4, "little")
    return bytes(packet)


def test_signal_packet_length():
    assert len(build_signal_packet(np.zeros((4, 8)))) == SIGNAL_PACKET_LEN == 108


def test_decode_signal_roundtrip():
    values = np.arange(32).reshape(4, 8) * 1000 - 15000
    assert np.allclose(decode_packet(build_signal_packet(values)), values)


def test_decode_resist_order_and_contact():
    packet = build_resist_packet([20_000, 4_000_000, 80_000, 1])
    assert len(packet) == 20
    assert decode_resist(packet) == [20_000, 4_000_000, 80_000, 1]
    contact = contact_from_resist(packet)
    # порядок пакета O1 O2 T3 T4 раскладывается по именам, а не по позиции
    assert RESIST_ORDER == ("O1", "O2", "T3", "T4")
    assert contact["O1"] == 1.0
    assert contact["O2"] == 0.5
    assert contact["T3"] == 1.0
    assert contact["T4"] == 1.0


def test_contact_clamped_to_unit():
    assert contact_from_ohms(0) == 1.0
    assert contact_from_ohms(2_000_000) == 1.0
    assert 0.0 < contact_from_ohms(20_000_000) < 0.2
