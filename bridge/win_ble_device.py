"""Ободок на Windows через системный Bluetooth, вторым подключением к Mind Tracker.

То же, что bridge/ble_device.py на Mac: прибор ведёт штатное приложение
Mind Tracker BCI, а мы открываем то же устройство через WinRT и слушаем
тот же поток. Команду запуска потока не шлём (её так и не нашли), поэтому
в Mind Tracker должен быть открыт «Мониторинг».

Трогаем только прибор, который уже подключён к Windows. Иначе наше
обращение к GATT само подключит ободок, поток никто не запустит, а SDK
потом его не найдёт.

Все вызовы WinRT идут в одном своём потоке со своим циклом asyncio: так
не мешают окно WebView2 и апартамент COM главного потока.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid

from bridge.headband_protocol import (
    ADC_TO_MICROVOLTS, CHANNELS, PULSE, PULSE_PACKET_LEN, RESIST, RESIST_ORDER,
    RESIST_PACKET_LEN, SERVICE, SIGNAL, SIGNAL_PACKET_LEN, STATUS,
    contact_from_ohms, decode_packet, decode_resist)

FIRST_PACKET_S = 6.0
RETRY_S = 1.5
NOTIFY = (SIGNAL, RESIST, STATUS, PULSE)
# путь последней попытки: если конструктор упал, объекта нет, а лог нужен
LAST_TRACE: list[str] = []


class DeviceNotFound(RuntimeError):
    """Ободок не подключён к Windows: Mind Tracker закрыт или не подключил его."""


class NoStream(RuntimeError):
    """Ободок подключён и подписка прошла, но пакеты сигнала не идут."""


class WinBleHeadbandDevice:
    """Тот же контракт, что у BleHeadbandDevice: fs, connected, contact, battery, start, stop."""

    def __init__(self, wait_s: float = 15.0, first_packet_s: float = FIRST_PACKET_S,
                 connect: bool = True) -> None:
        self.fs = 250
        self.connected = False
        self.battery_level = 0
        self.packets_received = 0
        self.reconnects = 0
        self.peripheral_name = ""
        self.address = ""
        self.last_resist_raw: list | None = None
        self.trace: list[str] = []          # что видели при подключении, для лога проверки
        global LAST_TRACE
        LAST_TRACE = self.trace
        self._contact_quality = {name: 1.0 for name in CHANNELS}
        self._on_chunk = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop: asyncio.Event | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._device = None
        self._session = None
        self._subscribed: list = []          # (характеристика, токен) для отписки
        if connect:
            self._open(wait_s, first_packet_s)

    # подключение -------------------------------------------------------------

    def _open(self, wait_s: float, first_packet_s: float) -> None:
        self._thread = threading.Thread(target=self._run, args=(wait_s,),
                                        name="win-ble", daemon=True)
        self._thread.start()
        if not self._ready.wait(wait_s + 20.0):
            self.close()
            raise DeviceNotFound("системный Bluetooth не ответил вовремя")
        if self._error is not None:
            self.close()
            raise self._error
        deadline = time.monotonic() + first_packet_s
        while self.packets_received == 0 and time.monotonic() < deadline:
            time.sleep(0.1)
        if self.packets_received == 0:
            self.close()
            raise NoStream("ободок подключён, но сигнал не идёт: откройте в Mind Tracker "
                           "вкладку «Мониторинг» и подключитесь снова")

    def _run(self, wait_s: float) -> None:
        try:
            asyncio.run(self._main(wait_s))
        except BaseException as error:  # noqa: BLE001  до этой точки ошибка ещё не отдана
            if not self._ready.is_set():
                self._error = error
                self._ready.set()

    async def _main(self, wait_s: float) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        try:
            await self._connect(wait_s)
        except BaseException as error:
            self._error = error
            self._ready.set()
            return
        self._ready.set()
        await self._stop.wait()
        await self._release()

    def _note(self, text: str) -> None:
        self.trace.append(text)

    async def _connected_headbands(self) -> list:
        """Подключённые к Windows приборы с сервисом ободка (обычно один)."""
        from winrt.windows.devices.bluetooth import (BluetoothCacheMode, BluetoothConnectionStatus,
                                                     BluetoothLEDevice)
        from winrt.windows.devices.bluetooth.genericattributeprofile import GattCommunicationStatus
        from winrt.windows.devices.enumeration import DeviceInformation

        service = uuid.UUID(SERVICE)
        selector = BluetoothLEDevice.get_device_selector_from_connection_status(
            BluetoothConnectionStatus.CONNECTED)
        infos = list(await DeviceInformation.find_all_async_aqs_filter(selector))
        self._note("подключено к Windows: " + (", ".join(f"«{i.name}»" for i in infos) or "ничего"))
        found = []
        for info in infos:
            device = await BluetoothLEDevice.from_id_async(info.id)
            if device is None:
                continue
            if device.connection_status != BluetoothConnectionStatus.CONNECTED:
                device.close()
                continue
            result = await device.get_gatt_services_for_uuid_with_cache_mode_async(
                service, BluetoothCacheMode.CACHED)
            services = list(result.services) if result.services is not None else []
            self._note(f"«{info.name}»: сервис ободка {'есть' if services else 'нет'}"
                       f" ({GattCommunicationStatus(result.status).name})")
            if services:
                found.append((device, services[0]))
            else:
                device.close()
        return found

    async def _connect(self, wait_s: float) -> None:
        from winrt.windows.devices.bluetooth.genericattributeprofile import GattSession

        deadline = time.monotonic() + wait_s
        found: list = []
        while True:
            found = await self._connected_headbands()
            if found or time.monotonic() >= deadline:
                break
            await asyncio.sleep(RETRY_S)
        if not found:
            raise DeviceNotFound("ободок не подключён к Windows: откройте Mind Tracker BCI, "
                                 "подключите в нём ободок и вкладку «Мониторинг»")
        (device, service), rest = found[0], found[1:]
        for other, _ in rest:
            other.close()
        self._device = device
        self.peripheral_name = str(device.name or "")
        self.address = f"{int(device.bluetooth_address):012X}"
        # своя сессия держит связь, даже если Mind Tracker на миг отпустит прибор
        try:
            self._session = await GattSession.from_device_id_async(device.bluetooth_device_id)
            self._session.maintain_connection = True
        except Exception as error:  # noqa: BLE001  без неё тоже работает
            self._note(f"GattSession: {error}")
        device.add_connection_status_changed(self._on_status)
        await self._subscribe(service)
        self.connected = True

    async def _subscribe(self, service) -> None:
        from winrt.windows.devices.bluetooth import BluetoothCacheMode
        from winrt.windows.devices.bluetooth.genericattributeprofile import (
            GattClientCharacteristicConfigurationDescriptorValue as Cccd, GattCommunicationStatus)

        result = await service.get_characteristics_with_cache_mode_async(BluetoothCacheMode.CACHED)
        characteristics = list(result.characteristics) if result.characteristics is not None else []
        signal_ok = False
        for characteristic in characteristics:
            key = str(characteristic.uuid).upper()
            if key not in NOTIFY:
                continue
            token = characteristic.add_value_changed(
                lambda sender, args, key=key: self._on_value(key, bytes(args.characteristic_value)))
            self._subscribed.append((characteristic, token))
            status = await characteristic.write_client_characteristic_configuration_descriptor_async(
                Cccd.NOTIFY)
            self._note(f"подписка {key[4:8]}: {GattCommunicationStatus(status).name}")
            if key == SIGNAL and status == GattCommunicationStatus.SUCCESS:
                signal_ok = True
        if not signal_ok:
            raise RuntimeError("Windows не дал подписаться на сигнал ободка: " + "; ".join(self.trace[-4:]))

    async def _release(self) -> None:
        for characteristic, token in self._subscribed:
            try:
                characteristic.remove_value_changed(token)
            except Exception:  # noqa: BLE001
                pass
        self._subscribed.clear()
        for item in (self._session, self._device):
            if item is not None:
                try:
                    item.close()
                except Exception:  # noqa: BLE001
                    pass
        self._session = self._device = None
        self.connected = False

    def _on_status(self, device, _args) -> None:
        from winrt.windows.devices.bluetooth import BluetoothConnectionStatus
        self.connected = device.connection_status == BluetoothConnectionStatus.CONNECTED
        if not self.connected:
            self.reconnects += 1

    # данные ------------------------------------------------------------------

    def _on_value(self, key: str, data: bytes) -> None:
        if key == SIGNAL and len(data) >= SIGNAL_PACKET_LEN:
            self.packets_received += 1
            callback = self._on_chunk
            if callback is not None:
                callback(decode_packet(data) * ADC_TO_MICROVOLTS)
        elif key == RESIST and len(data) == RESIST_PACKET_LEN:
            values = decode_resist(data)
            self.last_resist_raw = list(values)
            for name, ohms in zip(RESIST_ORDER, values):
                self._contact_quality[name] = contact_from_ohms(ohms)
        elif key == STATUS and data:
            self.battery_level = int(data[0])
        # пульс (PULSE_PACKET_LEN) версия 2.0 пока не пишет

    # контракт ----------------------------------------------------------------

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

    def watchdog(self) -> None:
        """Пакеты встали: переподписываемся на том же устройстве."""
        loop, device = self._loop, self._device
        if loop is None or device is None:
            return
        self.reconnects += 1

        async def resubscribe() -> None:
            from winrt.windows.devices.bluetooth import BluetoothCacheMode
            for characteristic, token in self._subscribed:
                try:
                    characteristic.remove_value_changed(token)
                except Exception:  # noqa: BLE001
                    pass
            self._subscribed.clear()
            result = await device.get_gatt_services_for_uuid_with_cache_mode_async(
                uuid.UUID(SERVICE), BluetoothCacheMode.CACHED)
            if result.services:
                await self._subscribe(list(result.services)[0])

        future = asyncio.run_coroutine_threadsafe(resubscribe(), loop)
        try:
            future.result(10.0)
        except Exception as error:  # noqa: BLE001
            self._note(f"переподписка: {error}")

    def close(self) -> None:
        self._on_chunk = None
        loop, stop = self._loop, self._stop
        if loop is not None and stop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(stop.set)
            thread = getattr(self, "_thread", None)
            if thread is not None:
                thread.join(5.0)
        self.connected = False
