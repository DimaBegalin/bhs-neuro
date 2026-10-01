"""Запись сигнала и событий сессии, устойчивая к сбою программы.

Каждое событие несёт номер отсчёта сигнала в момент события: время событий
отсчитывается по самому сигналу, а не по часам компьютера, поэтому окна
карточек точно ложатся на ЭЭГ. Без ободка номер отсчёта пустой, а время
считается по монотонным часам от начала сессии.

Сигнал копится в памяти и каждые несколько секунд дописывается в файл
signal.part, события сразу пишутся в events.jsonl. Если программа упала,
recover() собирает из этих файлов обычную запись.
"""
from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

from app.device.base import CHANNELS
from app.storage import atomic_write_bytes, atomic_write_json

PART_DTYPE = np.float32
FLUSH_S = 5.0


class SessionRecorder:
    def __init__(self, folder: Path, fs: int | None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.fs = fs
        self._clock = clock
        self._started = clock()
        self._lock = threading.RLock()
        self._pending: list[np.ndarray] = []
        self._pending_samples = 0
        self._samples = 0
        self._part = self.folder / "signal.part"
        self._events = self.folder / "events.jsonl"
        self._part.write_bytes(b"")
        self._events.write_text("", encoding="utf-8")
        self.closed = False

    @property
    def samples(self) -> int:
        with self._lock:
            return self._samples

    def on_chunk(self, chunk: np.ndarray) -> None:
        if self.fs is None or self.closed:
            return
        with self._lock:
            self._pending.append(np.asarray(chunk, dtype=PART_DTYPE))
            self._pending_samples += chunk.shape[1]
            self._samples += chunk.shape[1]
            if self._pending_samples >= self.fs * FLUSH_S:
                self._flush()

    def _flush(self) -> None:
        if not self._pending:
            return
        block = np.concatenate(self._pending, axis=1)
        with self._part.open("ab") as fh:
            # по отсчётам: каждый отсчёт — 4 значения подряд, так файл можно
            # дописывать и читать без знания итоговой длины
            fh.write(np.ascontiguousarray(block.T).tobytes())
        self._pending.clear()
        self._pending_samples = 0

    def mark(self, kind: str, payload: dict | None = None) -> dict:
        with self._lock:
            event = {
                "kind": kind,
                "t_s": round(self._clock() - self._started, 4),
                "sample": self._samples if self.fs is not None else None,
                "payload": payload or {},
            }
            with self._events.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def finish(self) -> tuple[Path | None, Path]:
        """Сводит запись в signal.npz и events.json, временные файлы удаляет."""
        with self._lock:
            self._flush()
            self.closed = True
        return assemble(self.folder, self.fs)


def _read_part(path: Path) -> np.ndarray:
    raw = np.frombuffer(path.read_bytes(), dtype=PART_DTYPE)
    usable = raw.size - raw.size % len(CHANNELS)
    return raw[:usable].reshape(-1, len(CHANNELS)).T


def _read_events(path: Path) -> list[dict]:
    events = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                break  # последняя строка могла оборваться при сбое
    return events


def assemble(folder: Path, fs: int | None) -> tuple[Path | None, Path]:
    folder = Path(folder)
    part, events_path = folder / "signal.part", folder / "events.jsonl"
    npz_path = None
    if fs is not None and part.exists():
        signal = _read_part(part)
        packed = io.BytesIO()
        np.savez_compressed(packed, signal=signal, fs=np.array(fs),
                            channels=np.array(CHANNELS))
        npz_path = folder / "signal.npz"
        atomic_write_bytes(npz_path, packed.getvalue())
    events_json = folder / "events.json"
    atomic_write_json(events_json, _read_events(events_path))
    for leftover in (part, events_path):
        if leftover.exists():
            leftover.unlink()
    return npz_path, events_json


def recover(folder: Path, fs: int | None) -> bool:
    """Собирает запись оборванной сессии. True, если было что собирать."""
    folder = Path(folder)
    if not (folder / "events.jsonl").exists():
        return False
    assemble(folder, fs)
    return True
