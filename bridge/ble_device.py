"""Источник сигнала через системный Bluetooth, без библиотеки производителя.

Официальный SDK на macOS падает с segmentation fault при доставке данных,
поэтому поток читается напрямую. Прибор при этом ведёт штатное приложение,
а мы подключаемся вторым и слушаем тот же поток: система это позволяет.

Формат разобран 12.08.2026 на живом приборе:
пакет 108 байт это 4 байта счётчика (шаг 8) и восемь блоков по 13 байт,
в каждом блоке служебный байт и четыре значения по 3 байта little-endian
со знаком, порядок каналов T3, T4, O1, O2.
"""
import time

import objc
from CoreBluetooth import CBCentralManager, CBUUID
from Foundation import NSObject
from libdispatch import dispatch_queue_create
from bridge.headband_protocol import (
    ADC_TO_MICROVOLTS, BLOCK, CHANNELS, GOOD_RESISTANCE_OHM, HEADER, PULSE,
    PULSE_PACKET_LEN, RESIST, RESIST_ORDER, RESIST_PACKET_LEN, SERVICE,
    SIDE_KEEP_S, SIGNAL, SIGNAL_PACKET_LEN, SAMPLES_PER_PACKET, STATUS,
    contact_from_ohms, decode_packet, decode_resist)


class DeviceNotFound(RuntimeError):
    pass


class BluetoothDead(DeviceNotFound):
    """Системный Bluetooth в этом процессе перестал отвечать.

    Это не «ободок выключен»: сама служба не присылает состояние или не
    отвечает на запросы. Внутри процесса это не лечится, помогает только
    его перезапуск, поэтому ошибка выделена в отдельный класс: обёртка
    прибора по ней понимает, что пора перезапускаться.
    """


# состояния CBManagerState: без разрешения и с выключенным Bluetooth колбэк
# приходит, но прибор искать бессмысленно, и менеджеру надо сказать причину
STATE_MESSAGES = {
    2: "Bluetooth на этом компьютере недоступен",
    3: "у программы нет разрешения Bluetooth: Системные настройки, "
       "Конфиденциальность и безопасность, Bluetooth, включить python",
    4: "Bluetooth на ноутбуке выключен",
}


class _Delegate(NSObject):
    def initWithOwner_(self, owner):
        self = objc.super(_Delegate, self).init()
        if self is None:
            return None
        self.owner = owner
        return self

    def centralManagerDidUpdateState_(self, central):
        """Только запоминаем состояние. Никаких запросов к системе отсюда.

        Колбэк выполняется на очереди менеджера. Раньше отсюда же шёл
        синхронный запрос списка подключённых приборов, и 10.09 он повис:
        служба Bluetooth перестала отвечать, каждая новая попытка (раз в шесть
        секунд) оставляла ещё один зависший поток, и за несколько часов их
        стало 512, это предел пула. После этого ни один новый менеджер не
        получал колбэков вовсе, и мост сутки писал «не удалось подключиться
        за 20 секунд» при включённом и подключённом ободке. Теперь запросы
        идут из своего потока, где зависание видно и лечится перезапуском.
        """
        self.owner._on_state(int(central.state()))

    def centralManager_didFailToConnectPeripheral_error_(self, central, peripheral, error):
        self.owner._fail("система отказала в подключении к прибору: "
                         + str(error)[:80])

    def centralManager_didConnectPeripheral_(self, central, peripheral):
        self.owner.peripheral = peripheral
        peripheral.setDelegate_(self)
        peripheral.discoverServices_([CBUUID.UUIDWithString_(SERVICE)])

    def peripheral_didDiscoverServices_(self, peripheral, error):
        for service in peripheral.services():
            peripheral.discoverCharacteristics_forService_(None, service)

    def peripheral_didDiscoverCharacteristicsForService_error_(self, p, service, error):
        for characteristic in service.characteristics():
            uuid = characteristic.UUID().UUIDString().upper()
            if uuid in (SIGNAL, RESIST, STATUS, PULSE):
                p.setNotifyValue_forCharacteristic_(True, characteristic)
        self.owner.connected = True

    def centralManager_didDisconnectPeripheral_error_(self, central, peripheral, error):
        """Связь рвётся сама по себе, поэтому поднимаем её обратно.

        Без этого сессия ребёнка оборвётся посреди теста и сигнал потеряется.
        """
        self.owner.connected = False
        self.owner.reconnects += 1
        central.connectPeripheral_options_(peripheral, None)

    def peripheral_didUpdateValueForCharacteristic_error_(self, p, characteristic, error):
        uuid = characteristic.UUID().UUIDString().upper()
        value = characteristic.value()
        if value is None:
            return
        data = bytes(value)
        if uuid == SIGNAL and len(data) >= SIGNAL_PACKET_LEN:
            self.owner._on_packet(data)
        elif uuid == RESIST and len(data) == RESIST_PACKET_LEN:
            self.owner._on_resist(data)
        elif uuid == PULSE and len(data) == PULSE_PACKET_LEN:
            self.owner._on_side("08", data)
        elif uuid == STATUS and data:
            self.owner.battery_level = int(data[0])


class BleHeadbandDevice:
    """Тот же контракт, что у FakeDevice: fs, connected, contact, battery, start, stop."""

    def __init__(self, wait_s: float = 20.0) -> None:
        self.fs = 250
        self.connected = False
        self.battery_level = 0
        self.packets_received = 0
        self.reconnects = 0
        self.peripheral = None
        self.peripheral_name = ""
        self._on_chunk = None
        self._error = None
        self.state = None            # состояние системного Bluetooth
        self._connect_requested = False
        import collections
        self.side_log = collections.deque()   # (монотонное время, канал, байты)
        self._contact_quality = {name: 1.0 for name in CHANNELS}
        self.last_resist_raw: list | None = None   # для диагностики посадки
        self._t0 = time.monotonic()
        self._delegate = _Delegate.alloc().initWithOwner_(self)
        # своя очередь обязательна: с очередью по умолчанию колбэки уходят
        # в главный поток, а он занят сервером, и данные не доходят
        self._queue = dispatch_queue_create(b"bhs.neuro.ble", None)
        self._manager = CBCentralManager.alloc().initWithDelegate_queue_(
            self._delegate, self._queue)

        deadline = time.time() + wait_s
        while time.time() < deadline and not self.connected:
            if self._error:
                self._give_up()
                raise DeviceNotFound(self._error)
            if self.state == 5 and not self._connect_requested:
                self._request_connect()
            time.sleep(0.2)
        if not self.connected:
            self._give_up()
            if self.state is None:
                # служба даже не сообщила своё состояние: это не про ободок
                raise BluetoothDead("системный Bluetooth не отвечает")
            raise DeviceNotFound("прибор виден системе, но не ответил на "
                                 f"подключение за {wait_s:.0f} секунд")

    def _on_state(self, state: int) -> None:
        self.state = state
        message = STATE_MESSAGES.get(state)
        if message:
            self._fail(message)

    def _request_connect(self) -> None:
        """Ищем прибор среди подключённых к системе и подключаемся вторым.

        Вызывается из потока поиска, а не из колбэка системы: запрос
        синхронный, и если служба Bluetooth повисла, повиснет этот поток,
        а не системный пул. Такое зависание обёртка прибора замечает.
        """
        self._connect_requested = True
        found = self._manager.retrieveConnectedPeripheralsWithServices_(
            [CBUUID.UUIDWithString_(SERVICE)])
        if not found:
            self._fail("прибор не подключён к системе: включите ободок "
                       "и подключите его в приложении")
            return
        # ссылку на устройство обязательно держим: иначе оно освобождается
        # до того, как соединение установится
        self.peripheral = found[0]
        self.peripheral_name = str(found[0].name())
        self._manager.connectPeripheral_options_(found[0], None)

    def _give_up(self) -> None:
        """Неудачная попытка не должна оставлять висящий запрос подключения."""
        if self.peripheral is not None and not self.connected:
            try:
                self._manager.cancelPeripheralConnection_(self.peripheral)
            except Exception:
                pass

    def _fail(self, message: str) -> None:
        self._error = message

    def _on_packet(self, packet: bytes) -> None:
        self.packets_received += 1
        if self._on_chunk is not None:
            self._on_chunk(decode_packet(packet) * ADC_TO_MICROVOLTS)

    def _trim_side(self) -> None:
        edge = time.monotonic() - SIDE_KEEP_S
        while self.side_log and self.side_log[0][0] < edge:
            self.side_log.popleft()

    def _on_side(self, channel: str, data: bytes) -> None:
        self.side_log.append((time.monotonic(), channel, data))
        self._trim_side()

    def _on_resist(self, data: bytes) -> None:
        """Живое сопротивление O1 O2 T3 T4: обновляет контакт и пишется в журнал."""
        values = decode_resist(data)
        self.last_resist_raw = list(values)
        for name, ohms in zip(RESIST_ORDER, values):
            self._contact_quality[name] = contact_from_ohms(ohms)
        self._on_side("05", data)

    def side_slice(self, start_monotonic: float, end_monotonic: float) -> list:
        self._trim_side()
        return [(t, ch, raw) for t, ch, raw in list(self.side_log)
                if start_monotonic <= t <= end_monotonic]

    def watchdog(self) -> None:
        """Если пакеты перестали идти, пересобираем подключение.

        Старая ссылка на устройство может протухнуть: ободок выключали,
        он переподключался системой, и повторный connect по ней уходит
        в никуда. Поэтому сначала спрашиваем систему, каким она видит
        прибор сейчас, и подключаемся к свежей ссылке.
        """
        self.reconnects += 1
        try:
            found = self._manager.retrieveConnectedPeripheralsWithServices_(
                [CBUUID.UUIDWithString_(SERVICE)])
        except Exception:
            found = None
        fresh = found[0] if found else self.peripheral
        if fresh is None:
            return
        if self.peripheral is not None:
            self._manager.cancelPeripheralConnection_(self.peripheral)
        self.peripheral = fresh
        self._manager.connectPeripheral_options_(fresh, None)

    def contact(self) -> dict:
        """Живой контакт из потока сопротивления: 150 кОм и ниже это хорошо."""
        if not self.connected:
            return {name: 0.0 for name in CHANNELS}
        return dict(self._contact_quality)

    def battery(self) -> int:
        return self.battery_level

    def start(self, on_chunk) -> None:
        self._on_chunk = on_chunk

    def stop(self) -> None:
        self._on_chunk = None
