"""Ободок через официальный SDK производителя (Windows).

Подключение и команды берёт SDK. Разбор пакетов на Windows наш: SDK 1.0.15
не понимает пакеты ободка Headband с прошивкой 4.8.10 («Process channel
pack error» на сигнале и сопротивлении, 05.10.2026). Поэтому после запуска
потока мы в том же процессе подписываемся на сырые пакеты через WinRT
(bridge/win_ble_device.py) и разбираем их сами, как на Mac. Если подписка
не удалась, остаётся поток самого SDK.
"""
from __future__ import annotations

import logging
import sys

from app.device.base import DeviceNotFound, OnChunk

log = logging.getLogger(__name__)
RAW_WAIT_S = 5.0


def _ignore(_chunk) -> None:
    pass


class SdkDevice:
    def __init__(self, scan_seconds: float = 15.0, raw: bool | None = None) -> None:
        from bridge.device import BrainBitDevice, DeviceNotFound as SdkNotFound
        try:
            self._device = BrainBitDevice(scan_seconds=scan_seconds)
        except SdkNotFound as error:
            raise DeviceNotFound(str(error)) from error
        self.fs = self._device.fs
        info = getattr(self._device, "info", None)
        self.info = info
        self.name = str(getattr(info, "Name", "") or "Headband")
        self._raw = None
        self.raw_trace: list[str] = []
        self.raw_error = ""
        if raw if raw is not None else sys.platform == "win32":
            self._attach_raw()
        self.source = "sdk+raw" if self._raw is not None else "sdk"

    def _attach_raw(self) -> None:
        """Запускаем поток командой SDK и слушаем сырые пакеты сами."""
        import bridge.win_ble_device as raw_module
        try:
            self._device.start(_ignore)
            self._raw = raw_module.WinBleHeadbandDevice(wait_s=RAW_WAIT_S)
            self.raw_trace = list(self._raw.trace)
        except Exception as error:  # noqa: BLE001  без сырого канала остаётся SDK
            self._raw = None
            try:  # вернуть SDK в исходное состояние: поток запустит start
                self._device.stop()
            except Exception:  # noqa: BLE001
                pass
            self.raw_error = f"{type(error).__name__}: {error}"
            self.raw_trace = list(raw_module.LAST_TRACE)
            log.warning("сырые пакеты недоступны, поток SDK: %s", self.raw_error)

    @property
    def raw(self):
        return self._raw

    @property
    def connected(self) -> bool:
        if self._raw is not None:
            return bool(self._device.connected and self._raw.connected)
        return bool(self._device.connected)

    def start(self, on_chunk: OnChunk) -> None:
        if self._raw is not None:
            self._raw.start(on_chunk)
        else:
            self._device.start(on_chunk)

    def stop(self) -> None:
        if self._raw is not None:
            self._raw.stop()
        else:
            self._device.stop()

    def close(self) -> None:
        if self._raw is not None:
            self._raw.close()
        self._device.close()

    def contact(self) -> dict[str, float]:
        if self._raw is not None:
            return self._raw.contact()
        return self._device.contact()

    def battery(self) -> int | None:
        try:
            return int(self._device.battery())
        except Exception:
            return None

    def restart_stream(self) -> None:
        if self._raw is None:
            self._device.watchdog()
            return
        callback = self._raw._on_chunk
        self._device.watchdog()          # SDK заново шлёт команду запуска
        if not self._device._streaming:  # watchdog мог не поднять поток
            self._device.start(_ignore)
        self._raw.watchdog()
        if callback is not None:
            self._raw.start(callback)
