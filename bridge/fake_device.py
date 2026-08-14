"""Источник сигнала вместо прибора: разработка и репетиция без железа.

Имитирует живого человека: альфа плавно гуляет, изредка проскакивают артефакты.
Так экран монитора можно отлаживать без ребёнка и без прибора.
"""
import threading
import time

import numpy as np

CHANNELS = ["T3", "T4", "O1", "O2"]


class FakeDevice:
    def __init__(self, fs: int = 250, alpha_hz: float = 10.2) -> None:
        self.fs = fs
        self.alpha_hz = alpha_hz
        self.connected = True
        self._on_chunk = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._phase = 0.0

    def contact(self) -> dict:
        return {name: 1.0 for name in CHANNELS}

    def battery(self) -> int:
        return 88

    def start(self, on_chunk) -> None:
        self._on_chunk = on_chunk
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _loop(self) -> None:
        rng = np.random.default_rng(0)
        chunk_samples = self.fs // 5  # пакеты по 200 мс
        while not self._stop.is_set():
            t = (self._phase + np.arange(chunk_samples)) / self.fs
            self._phase += chunk_samples
            # амплитуда альфы дышит с периодом около 40 секунд
            amp = 11.0 + 7.0 * np.sin(2 * np.pi * t.mean() / 40.0)
            chunk = rng.normal(0, 8.0, size=(len(CHANNELS), chunk_samples))
            chunk[2] += amp * np.sin(2 * np.pi * self.alpha_hz * t)
            chunk[3] += amp * np.sin(2 * np.pi * self.alpha_hz * t)
            if self._on_chunk is not None:
                self._on_chunk(chunk)
            time.sleep(chunk_samples / self.fs)
