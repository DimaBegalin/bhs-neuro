"""Что приложение ждёт от источника сигнала.

Источник отдаёт пакеты формы (4, n) в микровольтах в порядке T3, T4, O1, O2.
Колбэк вызывается из чужого потока (SDK, проигрыватель), поэтому
получатель сам отвечает за потокобезопасность.
"""
from __future__ import annotations

from typing import Callable, Protocol

import numpy as np

CHANNELS = ("T3", "T4", "O1", "O2")

OnChunk = Callable[[np.ndarray], None]


class DeviceNotFound(RuntimeError):
    """Ободок не появился в эфире за отведённое время."""


class Device(Protocol):
    fs: int
    connected: bool
    name: str

    def start(self, on_chunk: OnChunk) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...

    def contact(self) -> dict[str, float]:
        """Качество контакта по каналам от 0 до 1."""
        ...

    def battery(self) -> int | None: ...

    def restart_stream(self) -> None:
        """Пересобрать поток, если связь жива, а пакеты остановились."""
        ...
