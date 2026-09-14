# -*- coding: utf-8 -*-
"""Источник сигнала через bleak: системный Bluetooth на Windows и Linux.

Тот же прибор и те же байты, что читает ble_device.py на macOS через
CoreBluetooth, но способ подключиться другой. На macOS мост подключается
вторым к прибору, который уже держит штатное приложение, и слушает готовый
поток. На Windows так нельзя: прибор, занятый другим приложением, в эфире
не виден, а bleak находит устройства только по рекламе. Поэтому здесь мост
это единственный клиент прибора: сам находит его, сам подключается и сам
должен включить поток.

Честное ограничение: команда включения потока в характеристике 7e400003
пока не найдена (на macOS её не искали всерьёз, поток включало штатное
приложение). Пока она не найдена, этот канал подписывается на поток и ждёт:
если прибор уже стримит, всё работает, если нет, сигнала не будет. Команду
можно задать строкой HEADBAND_START_COMMAND в .env в шестнадцатеричном виде,
подобрать её помогает tools/win_find_start_command.py. Основной канал на
Windows поэтому библиотека производителя (bridge/device.py), а этот запасной.

Контракт тот же, что у BleHeadbandDevice и FakeDevice: fs, connected,
contact, battery, start, stop, packets_received, watchdog, side_slice.
"""
import asyncio
import collections
import os
import threading
import time

from bridge.headband_protocol import (
    ADC_TO_MICROVOLTS, CHANNELS, COMMAND, DEVICE_NAME, PULSE, PULSE_PACKET_LEN,
    RESIST, RESIST_ORDER, RESIST_PACKET_LEN, SERVICE, SIDE_KEEP_S, SIGNAL,
    SIGNAL_PACKET_LEN, STATUS, contact_from_ohms, decode_packet, decode_resist)

RECONNECT_PAUSE_S = 2.0
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        ".env")


class DeviceNotFound(RuntimeError):
    pass


def start_command_from_env(path: str = ENV_PATH) -> bytes | None:
    """Команда включения потока из .env, если менеджеру её выдали.

    Строка вида HEADBAND_START_COMMAND=01 или 0100. Пусто значит не слать
    ничего: наугад писать в канал команд прибора нельзя.
    """
    if not os.path.exists(path):
        return None
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("HEADBAND_START_COMMAND="):
                value = line.partition("=")[2].strip().replace(" ", "")
                return bytes.fromhex(value) if value else None
    except (OSError, ValueError):
        return None
    return None


def _looks_like_headband(device, adv) -> bool:
    uuids = [str(u).upper() for u in (getattr(adv, "service_uuids", None) or [])]
    if SERVICE in uuids:
        return True
    name = (getattr(device, "name", None) or getattr(adv, "local_name", None) or "")
    return name.lower().startswith(DEVICE_NAME.lower())


async def _default_finder(timeout: float):
    from bleak import BleakScanner
    return await BleakScanner.find_device_by_filter(_looks_like_headband, timeout=timeout)


def _default_client_factory(device, disconnected_callback):
    from bleak import BleakClient
    return BleakClient(device, disconnected_callback=disconnected_callback)


class BleakHeadbandDevice:
    def __init__(self, wait_s: float = 20.0, finder=None, client_factory=None,
                 start_command: bytes | None = None) -> None:
        """Ищет прибор и подключается, иначе бросает DeviceNotFound.

        finder и client_factory подменяются в тестах: настоящий Bluetooth
        там не нужен, проверяется поведение обёртки.
        """
        self.fs = 250
        self.connected = False
        self.battery_level = 0
        self.packets_received = 0
        self.reconnects = 0
        self.peripheral_name = ""
        self.side_log = collections.deque()   # (монотонное время, канал, байты)
        self.last_resist_raw: list | None = None
        self._contact_quality = {name: 1.0 for name in CHANNELS}
        self._on_chunk = None
        self._finder = finder or _default_finder
        self._client_factory = client_factory or _default_client_factory
        self._start_command = (start_command if start_command is not None
                               else start_command_from_env())
        self._wait_s = wait_s
        self._client = None
        self._error: str | None = None
        self._first_result = threading.Event()
        self._stop = threading.Event()
        self._loop = asyncio.new_event_loop()
        self._lost: asyncio.Event | None = None
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="bhs.neuro.bleak")
        self._thread.start()

        # первое подключение ждём синхронно: контракт обёртки прибора такой
        # же, как у CoreBluetooth, WaitingDevice создаёт прибор и ловит ошибку
        self._first_result.wait(wait_s + 10.0)
        if not self.connected:
            self.close()
            raise DeviceNotFound(self._error or "прибор не ответил на подключение "
                                 f"за {wait_s:.0f} секунд")

    # --- цикл подключения в своём потоке ---

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._session())
        finally:
            self._loop.close()

    async def _session(self) -> None:
        """Держит связь, пока обёртку не закрыли: связь рвётся, поднимаем её.

        Первая неудача это исключение наружу, дальнейшие обрывы лечатся сами:
        без этого сессия ребёнка оборвётся посреди теста и сигнал потеряется.
        """
        first = True
        while not self._stop.is_set():
            self._lost = asyncio.Event()
            try:
                await self._connect_once()
            except Exception as error:
                self._error = _explain(error)
                self.connected = False
                if first:
                    self._first_result.set()
                    return
                await asyncio.sleep(RECONNECT_PAUSE_S)
                continue
            first = False
            self._first_result.set()
            await self._lost.wait()
            self.connected = False
            if self._stop.is_set():
                break
            self.reconnects += 1
            await asyncio.sleep(RECONNECT_PAUSE_S)
        await self._disconnect_quietly()

    async def _connect_once(self) -> None:
        device = await self._finder(self._wait_s)
        if device is None:
            raise DeviceNotFound("прибор не найден в эфире: нажмите кнопку на ободке, "
                                 "штатное приложение при этом должно быть закрыто")
        self.peripheral_name = str(getattr(device, "name", "") or DEVICE_NAME)
        client = self._client_factory(device, self._on_disconnect)
        await client.connect()
        self._client = client
        for uuid in (SIGNAL, RESIST, STATUS, PULSE):
            try:
                await client.start_notify(uuid, self._on_notify)
            except Exception:
                # канала может не быть на другой прошивке: сигнал важнее
                if uuid == SIGNAL:
                    raise
        try:
            status = await client.read_gatt_char(STATUS)
            if status:
                self.battery_level = int(status[0])
        except Exception:
            pass
        if self._start_command:
            await client.write_gatt_char(COMMAND, self._start_command, response=False)
        self.connected = True

    async def _disconnect_quietly(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        try:
            await client.disconnect()
        except Exception:
            pass

    def _on_disconnect(self, _client) -> None:
        if self._lost is not None:
            self._loop.call_soon_threadsafe(self._lost.set)

    def _on_notify(self, characteristic, data) -> None:
        uuid = str(getattr(characteristic, "uuid", characteristic)).upper()
        data = bytes(data)
        if uuid == SIGNAL and len(data) >= SIGNAL_PACKET_LEN:
            self.packets_received += 1
            if self._on_chunk is not None:
                self._on_chunk(decode_packet(data) * ADC_TO_MICROVOLTS)
        elif uuid == RESIST and len(data) == RESIST_PACKET_LEN:
            values = decode_resist(data)
            self.last_resist_raw = list(values)
            for name, ohms in zip(RESIST_ORDER, values):
                self._contact_quality[name] = contact_from_ohms(ohms)
            self._on_side("05", data)
        elif uuid == PULSE and len(data) == PULSE_PACKET_LEN:
            self._on_side("08", data)
        elif uuid == STATUS and data:
            self.battery_level = int(data[0])

    # --- побочные каналы ---

    def _trim_side(self) -> None:
        edge = time.monotonic() - SIDE_KEEP_S
        while self.side_log and self.side_log[0][0] < edge:
            self.side_log.popleft()

    def _on_side(self, channel: str, data: bytes) -> None:
        self.side_log.append((time.monotonic(), channel, data))
        self._trim_side()

    def side_slice(self, start_monotonic: float, end_monotonic: float) -> list:
        self._trim_side()
        return [(t, ch, raw) for t, ch, raw in list(self.side_log)
                if start_monotonic <= t <= end_monotonic]

    # --- контракт прибора ---

    def watchdog(self) -> None:
        """Пакеты перестали идти: рвём связь сами, цикл поднимет её заново."""
        self.reconnects += 1
        if self._lost is not None:
            self._loop.call_soon_threadsafe(self._lost.set)

    def contact(self) -> dict:
        if not self.connected:
            return {name: 0.0 for name in CHANNELS}
        return dict(self._contact_quality)

    def battery(self) -> int:
        return self.battery_level

    def start(self, on_chunk) -> None:
        self._on_chunk = on_chunk

    def stop(self) -> None:
        self._on_chunk = None

    def close(self) -> None:
        self._stop.set()
        if self._lost is not None and not self._loop.is_closed():
            try:
                self._loop.call_soon_threadsafe(self._lost.set)
            except RuntimeError:
                pass
        self._thread.join(timeout=5.0)


def _explain(error: Exception) -> str:
    """Ошибки bleak в слова, которые менеджер поймёт со страницы теста."""
    name = type(error).__name__
    text = str(error)
    if name == "BleakBluetoothNotAvailableError" or "turned off" in text.lower():
        return "Bluetooth на ноутбуке выключен или недоступен"
    if name == "BleakDeviceNotFoundError":
        return "прибор пропал из эфира: нажмите кнопку на ободке"
    if isinstance(error, DeviceNotFound):
        return text
    return f"не удалось подключиться к прибору: {text[:90]}"
