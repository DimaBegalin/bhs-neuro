"""Чтение файлов сессии и нарезка сигнала по фазам из журнала событий."""
import json
from dataclasses import dataclass

import numpy as np


@dataclass
class LoadedSession:
    signal: np.ndarray
    fs: int
    events: list[dict]

    def _find(self, kind: str, payload_filter: dict | None) -> list[dict]:
        out = []
        for event in self.events:
            if event["kind"] != kind:
                continue
            if payload_filter and any(event["payload"].get(k) != v
                                      for k, v in payload_filter.items()):
                continue
            out.append(event)
        return out

    def slice(self, kind_start: str, kind_end: str,
              payload_filter: dict | None = None) -> np.ndarray:
        starts = self._find(kind_start, payload_filter)
        ends = self._find(kind_end, payload_filter)
        if not starts or not ends:
            raise KeyError(f"нет пары событий {kind_start} и {kind_end}")
        a = int(round(starts[0]["t_s"] * self.fs))
        b = int(round(ends[0]["t_s"] * self.fs))
        return self.signal[:, a:b]

    @property
    def trials_by_domain(self) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for event in self.events:
            if event["kind"] != "trial":
                continue
            domain = event["payload"]["domain"]
            grouped.setdefault(domain, []).append(event["payload"])
        return grouped


def load_session(npz_path: str, events_path: str) -> LoadedSession:
    data = np.load(npz_path)
    with open(events_path, encoding="utf-8") as fh:
        events = json.load(fh)
    return LoadedSession(signal=data["signal"], fs=int(data["fs"]), events=events)
