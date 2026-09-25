"""Накопление сырья и журнала событий, запись на диск."""
import os
import io
import threading

import numpy as np

from bridge.storage import atomic_write_bytes, atomic_write_json

CHANNELS = ["T3", "T4", "O1", "O2"]


class Recorder:
    def __init__(self, fs: int = 250, session_id: str = "session") -> None:
        self.fs = fs
        self.session_id = session_id
        self._chunks: list[np.ndarray] = []
        self.events: list[dict] = []
        self.t_start_s: float | None = None
        self._lock = threading.RLock()

    def push_samples(self, chunk: np.ndarray, t0_s: float) -> None:
        value = np.asarray(chunk, dtype=float)
        if value.ndim != 2 or value.shape[0] != len(CHANNELS):
            raise ValueError(f"ожидалось {len(CHANNELS)} канала, получено {value.shape}")
        with self._lock:
            if self.t_start_s is None:
                self.t_start_s = float(t0_s)
            # Копия отделяет запись от буфера SDK, который может переиспользоваться.
            self._chunks.append(value.copy())

    def push_event(self, kind: str, payload: dict, t_s: float) -> dict:
        event = {"kind": kind, "t_s": float(t_s), "payload": payload or {}}
        with self._lock:
            self.events.append(event)
        return event

    def signal(self) -> np.ndarray:
        with self._lock:
            if not self._chunks:
                return np.zeros((len(CHANNELS), 0))
            return np.concatenate(tuple(self._chunks), axis=1)

    def save(self, dir_path) -> tuple[str, str]:
        os.makedirs(dir_path, exist_ok=True)
        npz_path = os.path.join(str(dir_path), f"{self.session_id}.npz")
        events_path = os.path.join(str(dir_path), f"{self.session_id}.events.json")
        with self._lock:
            signal = (np.concatenate(tuple(self._chunks), axis=1)
                      if self._chunks else np.zeros((len(CHANNELS), 0)))
            started = self.t_start_s if self.t_start_s is not None else 0.0
            ordered = sorted((dict(event) for event in self.events),
                             key=lambda e: e["t_s"])
        packed = io.BytesIO()
        np.savez_compressed(packed, signal=signal, fs=np.array(self.fs),
                            t_start_s=np.array(started),
                            channels=np.array(CHANNELS))
        atomic_write_bytes(npz_path, packed.getvalue())
        atomic_write_json(events_path, ordered)
        return npz_path, events_path
