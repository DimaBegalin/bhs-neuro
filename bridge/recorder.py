"""Накопление сырья и журнала событий, запись на диск."""
import json
import os

import numpy as np

CHANNELS = ["T3", "T4", "O1", "O2"]


class Recorder:
    def __init__(self, fs: int = 250, session_id: str = "session") -> None:
        self.fs = fs
        self.session_id = session_id
        self._chunks: list[np.ndarray] = []
        self.events: list[dict] = []
        self.t_start_s: float | None = None

    def push_samples(self, chunk: np.ndarray, t0_s: float) -> None:
        if self.t_start_s is None:
            self.t_start_s = float(t0_s)
        self._chunks.append(np.asarray(chunk, dtype=float))

    def push_event(self, kind: str, payload: dict, t_s: float) -> dict:
        event = {"kind": kind, "t_s": float(t_s), "payload": payload or {}}
        self.events.append(event)
        return event

    def signal(self) -> np.ndarray:
        if not self._chunks:
            return np.zeros((len(CHANNELS), 0))
        return np.concatenate(self._chunks, axis=1)

    def save(self, dir_path) -> tuple[str, str]:
        os.makedirs(dir_path, exist_ok=True)
        npz_path = os.path.join(str(dir_path), f"{self.session_id}.npz")
        events_path = os.path.join(str(dir_path), f"{self.session_id}.events.json")
        np.savez_compressed(
            npz_path,
            signal=self.signal(),
            fs=np.array(self.fs),
            t_start_s=np.array(self.t_start_s if self.t_start_s is not None else 0.0),
            channels=np.array(CHANNELS),
        )
        ordered = sorted(self.events, key=lambda e: e["t_s"])
        with open(events_path, "w", encoding="utf-8") as fh:
            json.dump(ordered, fh, ensure_ascii=False, indent=2)
        return npz_path, events_path
