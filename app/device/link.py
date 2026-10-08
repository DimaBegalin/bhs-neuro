"""Связь с ободком: подключение в фоне, постоянный поток, сторож, качество.

После подключения поток идёт всё время, а сессия лишь подписывается на него.
Так менеджер видит качество сигнала ещё до старта, а запись не зависит от
того, успел ли прибор «проснуться» к началу сессии.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Callable

import numpy as np

from app.device.base import CHANNELS, Device, DeviceNotFound, OnChunk

log = logging.getLogger(__name__)

QUALITY_WINDOW_S = 2.0
# пороги стандартного отклонения за 2 с после удаления тренда: ниже —
# электрод не касается кожи или канал мёртв, выше — движение или наводка.
# Типичная ЭЭГ ободка на Mac: 15–40 мкВ.
FLAT_UV = 2.0
NOISY_UV = 100.0
MIN_CONTACT = 0.5


def channel_quality(window: np.ndarray, contact: dict[str, float]) -> dict[str, str]:
    """good / flat / noisy по каждому каналу за последнее окно."""
    result: dict[str, str] = {}
    n = window.shape[1]
    if n < 10:
        return {name: "flat" for name in CHANNELS}
    x = np.arange(n)
    for i, name in enumerate(CHANNELS):
        trend = np.polyval(np.polyfit(x, window[i], 1), x)
        sd = float(np.std(window[i] - trend))
        if sd < FLAT_UV or contact.get(name, 1.0) < MIN_CONTACT:
            result[name] = "flat"
        elif sd > NOISY_UV:
            result[name] = "noisy"
        else:
            result[name] = "good"
    return result


class DeviceLink:
    """Состояния: idle → searching → streaming ⇄ stalled → lost / error."""

    def __init__(self, factory: Callable[[], Device], stall_s: float = 5.0,
                 clock: Callable[[], float] = time.monotonic, watch: bool = True) -> None:
        self._factory = factory
        self._stall_s = stall_s
        self._clock = clock
        self._lock = threading.RLock()
        self._listeners: list[OnChunk] = []
        self._device: Device | None = None
        self._state = "idle"
        self._message = ""
        self._packets = 0
        self._last_chunk_at: float | None = None
        self._restarted_at: float | None = None
        self._window: deque[np.ndarray] = deque()
        self._window_samples = 0
        self._watchdog: threading.Thread | None = None
        self._closing = threading.Event()
        self._watch_enabled = watch

    # подключение -----------------------------------------------------------

    def connect(self) -> None:
        """Ищет ободок в фоне. Повторный вызов во время поиска ничего не делает."""
        with self._lock:
            if self._state in ("searching", "streaming", "stalled"):
                return
            self._state = "searching"
            self._message = ""
        threading.Thread(target=self._connect, name="device-connect", daemon=True).start()

    def _connect(self) -> None:
        log.info("ободок: ищу")
        try:
            device = self._factory()
            device.start(self._on_chunk)
        except DeviceNotFound as error:
            self._set("error", str(error))
            return
        except Exception as error:  # SDK бросает свои типы
            log.exception("подключение к ободку")
            self._set("error", f"не удалось подключиться: {error}")
            return
        with self._lock:
            self._device = device
            self._last_chunk_at = self._clock()
            self._restarted_at = None
            self._state = "streaming"
            self._message = ""
        log.info("ободок: подключён, %s, %s Гц", getattr(device, "name", "?"), getattr(device, "fs", "?"))
        self._closing.clear()
        if self._watch_enabled and (self._watchdog is None or not self._watchdog.is_alive()):
            self._watchdog = threading.Thread(target=self._watch, name="device-watchdog",
                                              daemon=True)
            self._watchdog.start()

    def reconnect(self) -> None:
        """Закрыть текущее подключение и искать заново (между учениками)."""
        self.disconnect()
        self.connect()

    def disconnect(self) -> None:
        self._closing.set()
        with self._lock:
            device, self._device = self._device, None
            self._state = "idle"
            self._window.clear()
            self._window_samples = 0
        if device is not None:
            try:
                device.close()
            except Exception:
                log.exception("закрытие ободка")

    # поток ------------------------------------------------------------------

    def add_listener(self, listener: OnChunk) -> None:
        with self._lock:
            self._listeners.append(listener)

    def remove_listener(self, listener: OnChunk) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def _on_chunk(self, chunk: np.ndarray) -> None:
        with self._lock:
            self._packets += 1
            self._last_chunk_at = self._clock()
            if self._state == "stalled":
                self._state, self._message = "streaming", ""
            self._window.append(chunk)
            self._window_samples += chunk.shape[1]
            fs = self._device.fs if self._device is not None else 250
            while self._window and self._window_samples - self._window[0].shape[1] >= fs * QUALITY_WINDOW_S:
                self._window_samples -= self._window.popleft().shape[1]
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(chunk)
            except Exception:
                log.exception("получатель сигнала")

    # сторож -----------------------------------------------------------------

    def check(self) -> None:
        """Один шаг сторожа. Вынесен отдельно, чтобы тестировать без потоков.

        Пакетов нет stall_s: поток пересобирается один раз. Нет ещё stall_s
        после пересборки, или прибор сам сообщил о потере связи: lost.
        """
        with self._lock:
            device = self._device
            if device is None or self._state not in ("streaming", "stalled"):
                return
            now = self._clock()
            silent = now - (now if self._last_chunk_at is None else self._last_chunk_at)
            if not device.connected:
                self._state, self._message = "lost", "связь с ободком потеряна"
                return
            if silent < self._stall_s:
                return
            if self._restarted_at is None:
                self._state, self._message = "stalled", "сигнал не приходит, перезапускаю поток"
                self._restarted_at = now
                restart = True
            elif now - self._restarted_at >= self._stall_s:
                self._state, self._message = "lost", "ободок перестал присылать сигнал"
                return
            else:
                restart = False
        if restart:
            try:
                device.restart_stream()
            except Exception as error:
                self._set("lost", f"не удалось перезапустить поток: {error}")

    def _watch(self) -> None:
        while not self._closing.wait(1.0):
            self.check()

    # состояние для интерфейса ----------------------------------------------

    def _set(self, state: str, message: str) -> None:
        log.warning("ободок: %s — %s", state, message)  # на экране текст пропадает, в логе остаётся
        with self._lock:
            self._state, self._message = state, message

    @property
    def fs(self) -> int | None:
        with self._lock:
            return self._device.fs if self._device is not None else None

    @property
    def streaming(self) -> bool:
        with self._lock:
            return self._state in ("streaming", "stalled")

    def snapshot(self) -> dict:
        with self._lock:
            device = self._device
            window = (np.concatenate(tuple(self._window), axis=1)
                      if self._window else np.zeros((len(CHANNELS), 0)))
            state, message, packets = self._state, self._message, self._packets
        contact = device.contact() if device is not None else {}
        return {
            "state": state,
            "message": message,
            "name": device.name if device is not None else "",
            "fs": device.fs if device is not None else None,
            "battery": device.battery() if device is not None else None,
            "packets": packets,
            "quality": channel_quality(window, contact) if device is not None else {},
        }
