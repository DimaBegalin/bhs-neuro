"""Ободок на Windows вторым подключением к Mind Tracker BCI и выбор канала.

Прямое подключение через SDK на ноутбуке не заработало, поэтому рабочий
порядок как на Mac: Mind Tracker держит ободок, мы слушаем тот же поток
(bridge/win_ble_device.py). auto_device сначала ищет ободок, уже
подключённый к Windows, и только если такого нет, идёт через SDK.
"""
from __future__ import annotations

from app.device.base import DeviceNotFound

AUTO_WAIT_S = 3.0


class WinBleDevice:
    def __init__(self, wait_s: float = 15.0) -> None:
        from bridge.win_ble_device import DeviceNotFound as BleNotFound, WinBleHeadbandDevice
        try:
            self._device = WinBleHeadbandDevice(wait_s=wait_s)
        except BleNotFound as error:
            raise DeviceNotFound(str(error)) from error
        self.fs = self._device.fs
        self.name = self._device.peripheral_name or "Headband (через Mind Tracker)"

    @property
    def connected(self) -> bool:
        return bool(self._device.connected)

    def start(self, on_chunk) -> None:
        self._device.start(on_chunk)

    def stop(self) -> None:
        self._device.stop()

    def close(self) -> None:
        self._device.close()

    def contact(self) -> dict[str, float]:
        return self._device.contact()

    def battery(self) -> int | None:
        return self._device.battery() or None

    def restart_stream(self) -> None:
        self._device.watchdog()


def auto_device(via_app=None, via_sdk=None):
    """Mind Tracker, затем SDK. Фабрики подменяются в тестах.

    Ошибки, кроме «не найден», не прячутся за SDK: если ободок у Windows
    есть, но поток не идёт, менеджеру нужна именно эта причина.
    """
    if via_app is None:
        via_app = lambda: WinBleDevice(wait_s=AUTO_WAIT_S)  # noqa: E731
    if via_sdk is None:
        from app.device.sdk import SdkDevice
        via_sdk = SdkDevice
    try:
        return via_app()
    except DeviceNotFound as app_error:
        try:
            return via_sdk()
        except DeviceNotFound as sdk_error:
            raise DeviceNotFound(f"{app_error}. Без Mind Tracker: {sdk_error}") from sdk_error
