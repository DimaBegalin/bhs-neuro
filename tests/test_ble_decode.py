"""Декодер пакета проверяется на синтетическом пакете с известными значениями."""
import numpy as np

from bridge.headband_protocol import decode_packet, CHANNELS, SAMPLES_PER_PACKET


def _build_packet(values):
    """values формы (4 канала, 8 отсчётов) в сырых единицах АЦП."""
    packet = bytearray()
    packet += (0).to_bytes(4, "little")
    for s in range(SAMPLES_PER_PACKET):
        packet += b"\x00"                      # служебный байт блока
        for c in range(len(CHANNELS)):
            packet += int(values[c][s]).to_bytes(3, "little", signed=True)
    return bytes(packet)


def test_packet_length_matches_device():
    packet = _build_packet(np.zeros((4, 8)))
    assert len(packet) == 108


def test_decode_returns_channels_and_samples():
    values = np.arange(32).reshape(4, 8) * 1000
    decoded = decode_packet(_build_packet(values))
    assert decoded.shape == (4, 8)
    assert np.allclose(decoded, values)


def test_decode_handles_negative_values():
    values = np.full((4, 8), -12345)
    decoded = decode_packet(_build_packet(values))
    assert np.allclose(decoded, -12345)


def test_channel_order_is_fixed():
    assert CHANNELS == ["T3", "T4", "O1", "O2"]
