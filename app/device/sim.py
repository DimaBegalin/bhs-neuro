"""Синтетический ободок: шум и затылочная альфа, которая растёт при «закрытых глазах».

Нужен для автотестов и пробных прогонов, где не важна правдоподобность
сигнала, но важно, чтобы поток шёл и реакция Бергера была видна.
"""
from __future__ import annotations

import threading

import numpy as np

from app.device.base import CHANNELS, OnChunk

CHUNK_S = 0.2


class SimDevice:
    def __init__(self, fs: int = 250, speed: float = 1.0, seed: int = 0) -> None:
        self.fs = fs
        self.name = "Имитатор"
        self.connected = True
        self.eyes_closed = False
        self.speed = speed
        self._rng = np.random.default_rng(seed)
        self._t = 0
        self._on_chunk: OnChunk | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, on_chunk: OnChunk) -> None:
        self._on_chunk = on_chunk
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="sim", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None

    def close(self) -> None:
        self.stop()
        self.connected = False

    def contact(self) -> dict[str, float]:
        return {name: 1.0 for name in CHANNELS}

    def battery(self) -> int | None:
        return 90

    def restart_stream(self) -> None:
        callback = self._on_chunk
        self.stop()
        if callback is not None:
            self.start(callback)

    def next_chunk(self) -> np.ndarray:
        n = int(round(self.fs * CHUNK_S))
        t = (self._t + np.arange(n)) / self.fs
        self._t += n
        chunk = self._rng.normal(0.0, 12.0, (len(CHANNELS), n))
        alpha = (30.0 if self.eyes_closed else 8.0) * np.sin(2 * np.pi * 10.0 * t)
        chunk[2:] += alpha
        return chunk

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._on_chunk is not None:
                try:
                    self._on_chunk(self.next_chunk())
                except Exception:
                    pass
            self._stop.wait(CHUNK_S / self.speed)
