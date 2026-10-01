"""Ободок на Mac через системный Bluetooth (канал версии 1), только для тестов.

SDK производителя на macOS падает, поэтому поток слушается напрямую, вторым
подключением к прибору, который ведёт Mind Tracker. Mind Tracker должен
быть открыт на вкладке «Мониторинг»: команду запуска потока мы так и не
нашли (docs/ЖЕЛЕЗО.md). Рабочий продукт — Windows и SDK (ADR 0002).
"""
from __future__ import annotations

from app.device.base import DeviceNotFound, OnChunk


class MacBleDevice:
    def __init__(self, wait_s: float = 20.0) -> None:
        from bridge.ble_device import BleHeadbandDevice, DeviceNotFound as BleNotFound
        try:
            self._device = BleHeadbandDevice(wait_s=wait_s)
        except BleNotFound as error:
            raise DeviceNotFound(
                f"{error}. Откройте Mind Tracker, подключите в нём ободок и вкладку «Мониторинг»") from error
        self.fs = self._device.fs
        self.name = self._device.peripheral_name or "Headband (Mac, через Mind Tracker)"

    @property
    def connected(self) -> bool:
        return bool(self._device.connected)

    def start(self, on_chunk: OnChunk) -> None:
        self._device.start(on_chunk)

    def stop(self) -> None:
        self._device.stop()

    def close(self) -> None:
        self._device.stop()
        try:
            self._device._give_up()
        except Exception:
            pass

    def contact(self) -> dict[str, float]:
        return self._device.contact()

    def battery(self) -> int | None:
        return self._device.battery() or None

    def restart_stream(self) -> None:
        self._device.watchdog()
