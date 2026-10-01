"""Проигрыватель записанной сессии вместо ободка (разработка на Mac).

Отдаёт сигнал из файла .npz версии 1 пакетами по 200 мс в реальном времени
(или быстрее, если задан speed) и по кругу. Умеет изображать сбои, которые
встречаются на живом ободке: пропадание пакетов и потерю связи.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.device.base import CHANNELS, OnChunk

CHUNK_S = 0.2


@dataclass(frozen=True)
class Fault:
    """Сбой на отрезке [at_s, at_s + duration_s) от начала потока.

    kind="gap": пакеты не приходят, связь формально жива (так виснет BLE).
    kind="lost": связь потеряна, connected=False, пока отрезок не кончится.
    """
    kind: str
    at_s: float
    duration_s: float


class ReplayDevice:
    def __init__(self, path: str | Path, speed: float = 1.0,
                 faults: tuple[Fault, ...] = ()) -> None:
        data = np.load(path)
        self.signal = np.asarray(data["signal"], dtype=float)
        if self.signal.shape[0] != len(CHANNELS) or self.signal.shape[1] == 0:
            raise ValueError(f"в {path} нет сигнала формы (4, n)")
        self.fs = int(data["fs"])
        self.name = f"Запись {Path(path).stem}"
        self.speed = speed
        self.faults = faults
        self.connected = True
        self._position = 0
        self._elapsed_s = 0.0
        self._on_chunk: OnChunk | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, on_chunk: OnChunk) -> None:
        self._on_chunk = on_chunk
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="replay", daemon=True)
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
        return {name: 1.0 if self.connected else 0.0 for name in CHANNELS}

    def battery(self) -> int | None:
        return 80

    def restart_stream(self) -> None:
        callback = self._on_chunk
        self.stop()
        if callback is not None:
            self.start(callback)

    def _active_fault(self) -> Fault | None:
        for fault in self.faults:
            if fault.at_s <= self._elapsed_s < fault.at_s + fault.duration_s:
                return fault
        return None

    def next_chunk(self) -> np.ndarray:
        """Следующий пакет по кругу. Отдельно от потока, чтобы тестировать без сна."""
        size = int(round(self.fs * CHUNK_S))
        end = self._position + size
        if end <= self.signal.shape[1]:
            chunk = self.signal[:, self._position:end]
        else:
            tail = self.signal[:, self._position:]
            chunk = np.concatenate([tail, self.signal[:, :end - self.signal.shape[1]]], axis=1)
        self._position = end % self.signal.shape[1]
        return chunk.copy()

    def _loop(self) -> None:
        period = CHUNK_S / self.speed
        next_at = time.monotonic()
        while not self._stop.is_set():
            fault = self._active_fault()
            self.connected = not (fault and fault.kind == "lost")
            if fault is None:
                chunk = self.next_chunk()
                if self._on_chunk is not None:
                    try:
                        self._on_chunk(chunk)
                    except Exception:
                        pass
            self._elapsed_s += CHUNK_S
            next_at += period
            self._stop.wait(max(0.0, next_at - time.monotonic()))
