"""Единый источник времени сессии. Всё в системе штампуется отсюда."""
import time


class SessionClock:
    def __init__(self) -> None:
        self._t0 = time.monotonic()

    def now_s(self) -> float:
        return time.monotonic() - self._t0

    def reset(self) -> None:
        self._t0 = time.monotonic()
