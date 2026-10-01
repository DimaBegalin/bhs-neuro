"""Ободок через официальный SDK производителя (Windows).

Подключение, повторы команд и разбор отсчётов уже отлажены в версии 1
(bridge.device) и проверяются утилитой этапа 0. Здесь только приведение
к интерфейсу Device.
"""
from __future__ import annotations

from app.device.base import DeviceNotFound, OnChunk


class SdkDevice:
    def __init__(self, scan_seconds: float = 15.0) -> None:
        from bridge.device import BrainBitDevice, DeviceNotFound as SdkNotFound
        try:
            self._device = BrainBitDevice(scan_seconds=scan_seconds)
        except SdkNotFound as error:
            raise DeviceNotFound(str(error)) from error
        self.fs = self._device.fs
        info = getattr(self._device, "info", None)
        self.name = str(getattr(info, "Name", "") or "Headband")

    @property
    def connected(self) -> bool:
        return bool(self._device.connected)

    def start(self, on_chunk: OnChunk) -> None:
        self._device.start(on_chunk)

    def stop(self) -> None:
        self._device.stop()

    def close(self) -> None:
        self._device.close()

    def contact(self) -> dict[str, float]:
        return self._device.contact()

    def battery(self) -> int | None:
        try:
            return int(self._device.battery())
        except Exception:
            return None

    def restart_stream(self) -> None:
        self._device.watchdog()
