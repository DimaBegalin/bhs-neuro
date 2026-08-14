"""Обёртка над pyneurosdk2. Порядок каналов и единицы приводятся здесь.

Наружу всегда отдаётся порядок T3, T4, O1, O2: тот же, что в brainflow
и в файлах сессии. Имена полей отсчёта сверяются выводом tools/probe_device.py.
"""
import time

import numpy as np
from neurosdk.scanner import Scanner
from neurosdk.cmn_types import SensorFamily, SensorCommand

CHANNELS = ["T3", "T4", "O1", "O2"]
# в SDK нет отдельного семейства Headband: ободок опознаётся как одно из
# семейств BrainBit, поэтому сканируем все и берём первое найденное
# ободок Waverox опознаётся как LEHeadband. Это семейство появилось
# только в pyneurosdk2 1.0.15, на 1.0.12 прибор не находится вовсе
FAMILIES = [SensorFamily.LEHeadband, SensorFamily.LEBrainBit,
            SensorFamily.LEBrainBit2, SensorFamily.LEBrainBitBlack,
            SensorFamily.LEBrainBitFlex, SensorFamily.LEBrainBitPro,
            SensorFamily.LENeuroEEG]
VOLTS_TO_MICROVOLTS = 1e6
GOOD_RESISTANCE_OHM = 2_000_000.0
SETTLE_S = 5.0
COMMAND_ATTEMPTS = 6
COMMAND_PAUSE_S = 2.0


class DeviceNotFound(RuntimeError):
    pass


def _frequency_to_hz(value, default: int = 250) -> int:
    """SDK отдаёт частоту перечислением вида FrequencyHz250, а не числом."""
    if isinstance(value, (int, float)):
        return int(value)
    name = str(getattr(value, "name", value))
    digits = "".join(ch for ch in name if ch.isdigit())
    return int(digits) if digits else default


class BrainBitDevice:
    def __init__(self, scan_seconds: float = 10.0) -> None:
        self.fs = 250
        self.connected = False
        self._sensor = None
        self._on_chunk = None
        self._contact = {name: 0.0 for name in CHANNELS}
        self._connect(scan_seconds)

    def _connect(self, scan_seconds: float) -> None:
        """Ищет прибор и подключается сразу, как только он появился в эфире.

        Ободок рекламирует себя недолго после нажатия кнопки и снова засыпает,
        поэтому ждать конца окна сканирования нельзя: проверяем каждые полсекунды
        и хватаем устройство в момент пробуждения.
        """
        scanner = Scanner(FAMILIES)
        scanner.start()
        deadline = time.monotonic() + scan_seconds
        found = []
        while time.monotonic() < deadline:
            found = scanner.sensors()
            if found:
                break
            time.sleep(0.5)
        scanner.stop()
        if not found:
            raise DeviceNotFound(
                "прибор не найден. Нажмите кнопку на ободке, индикатор должен мигать. "
                "Штатное приложение Mind Tracker при этом должно быть закрыто: "
                "устройство держит только одно подключение")
        self._sensor = scanner.create_sensor(found[0])
        self.info = found[0]
        self.fs = _frequency_to_hz(self._sensor.sampling_frequency)
        # канал команд у прибора готов не сразу после установления связи,
        # без этой паузы первая команда отвечает ERR_DATA_SEND
        time.sleep(SETTLE_S)
        self.connected = True

    def contact(self) -> dict:
        """Качество контакта по каналам от 0 до 1, больше это лучше."""
        return dict(self._contact)

    def battery(self) -> int:
        return int(self._sensor.batt_power)

    def measure_contact(self, seconds: float = 3.0) -> dict:
        """Режим сопротивления. Идёт до записи, одновременно с сигналом нельзя."""
        readings: list = []
        self._sensor.set_resist_callbacks(lambda s, data: readings.append(data))
        self._sensor.exec_command(SensorCommand.StartResist)
        time.sleep(seconds)
        self._sensor.exec_command(SensorCommand.StopResist)
        self._sensor.unset_resist_callbacks()
        if readings:
            last = readings[-1]
            for name in CHANNELS:
                raw = float(getattr(last, name))
                self._contact[name] = max(0.0, min(1.0, GOOD_RESISTANCE_OHM / max(raw, 1.0)))
        return dict(self._contact)

    def _command(self, command) -> bool:
        """Шлёт команду с повторами: прибор отвечает ERR_DATA_SEND, пока не готов."""
        last = None
        for _ in range(COMMAND_ATTEMPTS):
            try:
                self._sensor.exec_command(command)
                return True
            except Exception as error:
                last = error
                time.sleep(COMMAND_PAUSE_S)
        raise RuntimeError(f"команда {command} не прошла: {last}")

    def _subscribe(self, kind: str, handler) -> None:
        """Подписка на поток. У Headband колбэк присваивается атрибутом, а метод
        идёт без аргументов, у BrainBit колбэк передаётся прямо в метод."""
        setter = getattr(self._sensor, f"set_{kind}_callbacks")
        attribute = "signalDataReceived" if kind == "signal" else "resistDataReceived"
        try:
            setattr(self._sensor, attribute, handler)
            setter()
        except TypeError:
            setter(handler)

    def start(self, on_chunk) -> None:
        """Запускает поток сигнала и, если прибор умеет, сопротивление вместе с ним.

        Совмещённый режим держит качество контакта живым весь сеанс: диагност
        видит отвалившийся электрод сразу, а не после сессии.
        """
        self._on_chunk = on_chunk
        self._subscribe("signal", self._handle)
        try:
            self._subscribe("resist", self._handle_resist)
            self._command(SensorCommand.StartSignalAndResist)
            self._combined = True
        except Exception:
            self._command(SensorCommand.StartSignal)
            self._combined = False

    def stop(self) -> None:
        if getattr(self, "_combined", False):
            self._command(SensorCommand.StopSignalAndResist)
            self._sensor.unset_resist_callbacks()
        else:
            self._command(SensorCommand.StopSignal)
        self._sensor.unset_signal_callbacks()

    def _handle_resist(self, sensor, data) -> None:
        for name in CHANNELS:
            raw = float(getattr(data, name, 0.0))
            self._contact[name] = max(0.0, min(1.0, GOOD_RESISTANCE_OHM / max(raw, 1.0)))

    def raw_sample_fields(self, data) -> dict:
        """Первый отсчёт пакета как есть. Нужен при разборе единиц измерения."""
        first = data[0] if isinstance(data, list) else data
        return {name: float(getattr(first, name)) for name in CHANNELS}

    def _handle(self, sensor, data) -> None:
        chunk = np.array([[getattr(s, name) for s in data] for name in CHANNELS],
                         dtype=float) * VOLTS_TO_MICROVOLTS
        if self._on_chunk is not None:
            self._on_chunk(chunk)
