"""Канал на bleak без настоящего Bluetooth: поиск, подписки, обрыв, сторож.

Настоящий прибор в тестах заменён поддельным клиентом с тем же контрактом,
что у BleakClient: connect, start_notify, read_gatt_char, write_gatt_char,
disconnect и колбэк обрыва.
"""
import time

import numpy as np
import pytest

from bridge.bleak_device import BleakHeadbandDevice, DeviceNotFound, start_command_from_env
from bridge.headband_protocol import COMMAND, PULSE, RESIST, SIGNAL, STATUS
from tests.test_headband_protocol import build_resist_packet, build_signal_packet


class FakeDevice:
    name = "Headband"
    address = "AA:BB"


class FakeClient:
    created: list["FakeClient"] = []

    def __init__(self, device, disconnected_callback, fail_connect: bool = False):
        self.device = device
        self.on_disconnect = disconnected_callback
        self.fail_connect = fail_connect
        self.handlers: dict[str, object] = {}
        self.written: list[tuple[str, bytes]] = []
        self.disconnected = False
        FakeClient.created.append(self)

    async def connect(self):
        if self.fail_connect:
            raise RuntimeError("Bluetooth is turned off")

    async def start_notify(self, uuid, handler):
        self.handlers[uuid] = handler

    async def read_gatt_char(self, uuid):
        assert uuid == STATUS
        return bytes([68, 0, 0x2d, 8])

    async def write_gatt_char(self, uuid, data, response=None):
        self.written.append((uuid, bytes(data)))

    async def disconnect(self):
        self.disconnected = True

    # --- со стороны прибора ---

    class _Char:
        def __init__(self, uuid): self.uuid = uuid

    def push(self, uuid: str, data: bytes) -> None:
        self.handlers[uuid](self._Char(uuid.lower()), bytearray(data))

    def drop(self) -> None:
        self.on_disconnect(self)


def _finder_returning(device):
    async def finder(timeout):
        return device
    return finder


@pytest.fixture(autouse=True)
def _clean():
    FakeClient.created.clear()
    yield


def _make(start_command: bytes = b""):
    return BleakHeadbandDevice(wait_s=2.0, finder=_finder_returning(FakeDevice()),
                               client_factory=FakeClient, start_command=start_command)


def test_connects_and_subscribes_to_all_streams():
    device = _make()
    try:
        assert device.connected
        assert device.battery() == 68
        assert device.peripheral_name == "Headband"
        client = FakeClient.created[-1]
        assert set(client.handlers) == {SIGNAL, RESIST, STATUS, PULSE}
        assert client.written == []      # без команды в .env ничего не шлём
    finally:
        device.close()


def test_signal_packets_reach_subscriber_in_microvolts():
    device = _make()
    try:
        chunks = []
        device.start(chunks.append)
        client = FakeClient.created[-1]
        values = np.full((4, 8), 1000)
        client.push(SIGNAL, build_signal_packet(values))
        client.push(SIGNAL, build_signal_packet(values))
        assert device.packets_received == 2
        assert len(chunks) == 2 and chunks[0].shape == (4, 8)
        assert np.allclose(chunks[0], 1000 * 2.4e6 / (6.0 * (1 << 23)))
        device.stop()
        client.push(SIGNAL, build_signal_packet(values))
        assert len(chunks) == 2
    finally:
        device.close()


def test_contact_follows_resist_packets_and_side_log():
    device = _make()
    try:
        client = FakeClient.created[-1]
        t0 = time.monotonic()
        client.push(RESIST, build_resist_packet([20_000, 4_000_000, 80_000, 100]))
        client.push(PULSE, bytes(52))
        contact = device.contact()
        assert contact["O2"] == 0.5 and contact["O1"] == 1.0
        assert device.last_resist_raw == [20_000, 4_000_000, 80_000, 100]
        rows = device.side_slice(t0, time.monotonic())
        assert [ch for _, ch, _ in rows] == ["05", "08"]
    finally:
        device.close()


def test_reconnects_after_drop():
    device = _make()
    try:
        first = FakeClient.created[-1]
        first.drop()
        deadline = time.time() + 6
        while time.time() < deadline and len(FakeClient.created) < 2:
            time.sleep(0.05)
        while time.time() < deadline and not device.connected:
            time.sleep(0.05)
        assert len(FakeClient.created) == 2
        assert device.connected
        assert device.reconnects == 1
    finally:
        device.close()


def test_watchdog_forces_reconnect():
    device = _make()
    try:
        device.watchdog()
        deadline = time.time() + 6
        while time.time() < deadline and not (len(FakeClient.created) >= 2 and device.connected):
            time.sleep(0.05)
        assert len(FakeClient.created) == 2
    finally:
        device.close()


def test_not_found_raises_with_reason():
    with pytest.raises(DeviceNotFound, match="не найден"):
        BleakHeadbandDevice(wait_s=1.0, finder=_finder_returning(None),
                            client_factory=FakeClient, start_command=b"")


def test_bluetooth_off_is_explained():
    def factory(device, cb):
        return FakeClient(device, cb, fail_connect=True)
    with pytest.raises(DeviceNotFound, match="выключен"):
        BleakHeadbandDevice(wait_s=1.0, finder=_finder_returning(FakeDevice()),
                            client_factory=factory, start_command=b"")


def test_start_command_sent_when_configured(tmp_path):
    env = tmp_path / ".env"
    env.write_text("SUPABASE_URL=x\nHEADBAND_START_COMMAND=01 00\n", encoding="utf-8")
    assert start_command_from_env(str(env)) == b"\x01\x00"
    assert start_command_from_env(str(tmp_path / "нет")) is None
    device = _make(start_command=b"\x01")
    try:
        assert FakeClient.created[-1].written == [(COMMAND, b"\x01")]
    finally:
        device.close()


def test_matches_waiting_device_contract():
    from bridge.fake_device import FakeDevice as Generator
    for name in ("contact", "battery", "start", "stop"):
        assert callable(getattr(BleakHeadbandDevice, name))
        assert callable(getattr(Generator, name))
    for name in ("watchdog", "side_slice", "close"):
        assert callable(getattr(BleakHeadbandDevice, name))
