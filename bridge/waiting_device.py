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
# столько может длиться одна попытка, прежде чем считать, что запрос к
# системному Bluetooth повис. Сама попытка укладывается в 20 секунд ожидания
STUCK_S = 90.0
# сколько раз подряд служба Bluetooth должна промолчать, чтобы признать её
# мёртвой: один раз она может замешкаться после сна ноутбука
DEAD_STREAK = 2


class WaitingDevice:
    def __init__(self, factory, fs: int = 250) -> None:
        """factory создаёт настоящий прибор и бросает исключение, если его нет."""
        self._factory = factory
        self.fs = fs
        self._device = None
        self._on_chunk = None
        self.last_error = "прибор ещё не найден"
        self._attempt_started: float | None = None
        self._dead_streak = 0
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
    def bluetooth_dead(self) -> bool:
        """Системный Bluetooth в этом процессе перестал отвечать.

        Два признака: попытка поиска не заканчивается дольше STUCK_S (повис
        синхронный запрос к службе) или служба несколько раз подряд не
        сообщила даже своего состояния. Изнутри процесса это не лечится:
        10.09 мост в таком состоянии простоял сутки при включённом ободке.
        Сервер по этому признаку перезапускает процесс целиком.
        """
        started = self._attempt_started
        if started is not None and time.monotonic() - started > STUCK_S:
            return True
        return self._dead_streak >= DEAD_STREAK

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
            device = self._device
            if device is not None and not bool(getattr(device, "connected", False)):
                self._discard_device(device)
            if self._device is None:
                self._try_connect()
            self._stop.wait(RETRY_S)

    def _discard_device(self, device) -> None:
        with self._lock:
            if self._device is not device:
                return
            self._device = None
        try:
            if hasattr(device, "close"):
                device.close()
            else:
                device.stop()
        except Exception:
            pass

    def _try_connect(self) -> None:
        with self._lock:
            if self._device is not None:
                return
        # Поиск Bluetooth может висеть десятки секунд. Не держим lock всё это
        # время, иначе завершение приложения тоже зависнет на том же поиске.
        self._attempt_started = time.monotonic()
        try:
            device = self._factory()
        except Exception as error:
            self.last_error = str(error)[:120]
            self._dead_streak = (self._dead_streak + 1
                                 if _is_bluetooth_dead(error) else 0)
            return
        finally:
            self._attempt_started = None
        self._dead_streak = 0
        self.fs = getattr(device, "fs", self.fs)
        if self._on_chunk is not None:
            device.start(self._on_chunk)
        with self._lock:
            if self._stop.is_set() or self._device is not None:
                try:
                    device.close() if hasattr(device, "close") else device.stop()
                except Exception:
                    pass
                return
            self._device = device
        self.last_error = ""

    def close(self) -> None:
        self._stop.set()
        device = self._device
        if device is not None:
            self._discard_device(device)
        self._thread.join(timeout=2.0)


def _is_bluetooth_dead(error: Exception) -> bool:
    """Ошибка о мёртвой службе, а не об отсутствующем приборе.

    Класс берём по имени, чтобы не тянуть CoreBluetooth в тесты и в
    генератор: обёртка одинаково работает и там, где системного Bluetooth
    нет вовсе.
    """
    return any(cls.__name__ == "BluetoothDead" for cls in type(error).__mro__)
