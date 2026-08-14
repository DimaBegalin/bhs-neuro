# -*- coding: utf-8 -*-
"""Прибор, который может появиться позже.

Мост на ноутбуке менеджера запускается вместе с системой и работает весь
день. Ободок при этом то включён, то заряжается, то его надели следующему
ребёнку. Раньше мост требовал прибор в момент запуска и падал без него,
поэтому его приходилось перезапускать руками, а менеджеру объяснять, что
нажать. Здесь мост поднимается всегда, а прибор подхватывается сам, как
только появится, и так же сам подхватывается заново после обрыва.

Наружу отдаётся тот же контракт, что у настоящего прибора: fs, connected,
contact, battery, start, stop. Ни сервер, ни страница теста не знают,
что прибора может не быть.
"""
import threading
import time

CHANNELS = ["T3", "T4", "O1", "O2"]
RETRY_S = 6.0


class WaitingDevice:
    def __init__(self, factory, fs: int = 250) -> None:
        """factory создаёт настоящий прибор и бросает исключение, если его нет."""
        self._factory = factory
        self.fs = fs
        self._device = None
        self._on_chunk = None
        self.last_error = "прибор ещё не найден"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # --- контракт прибора ---

    @property
    def connected(self) -> bool:
        device = self._device
        return bool(device is not None and device.connected)

    @property
    def packets_received(self) -> int:
        return int(getattr(self._device, "packets_received", 0))

    def contact(self) -> dict:
        device = self._device
        if device is None:
            return {name: 0.0 for name in CHANNELS}
        return device.contact()

    def battery(self) -> int:
        device = self._device
        return int(device.battery()) if device is not None else 0

    def start(self, on_chunk) -> None:
        """Подписка запоминается и переносится на прибор, когда он появится."""
        self._on_chunk = on_chunk
        device = self._device
        if device is not None:
            device.start(on_chunk)

    def stop(self) -> None:
        device = self._device
        if device is not None:
            device.stop()

    def side_slice(self, start_monotonic: float, end_monotonic: float) -> list:
        device = self._device
        if device is None or not hasattr(device, "side_slice"):
            return []
        return device.side_slice(start_monotonic, end_monotonic)

    def watchdog(self) -> None:
        """Поток встал. Пробуем поднять прибор, а не сможем, ищем заново."""
        device = self._device
        if device is None:
            return
        try:
            if hasattr(device, "watchdog"):
                device.watchdog()
        except Exception as error:
            self.last_error = str(error)[:120]

    # --- поиск прибора ---

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._device is None:
                self._try_connect()
            self._stop.wait(RETRY_S)

    def _try_connect(self) -> None:
        with self._lock:
            if self._device is not None:
                return
            try:
                device = self._factory()
            except Exception as error:
                self.last_error = str(error)[:120]
                return
            self.fs = getattr(device, "fs", self.fs)
            if self._on_chunk is not None:
                device.start(self._on_chunk)
            self._device = device
            self.last_error = ""

    def close(self) -> None:
        self._stop.set()
