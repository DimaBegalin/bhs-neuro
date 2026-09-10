# -*- coding: utf-8 -*-
"""Мост поднимается без прибора и подхватывает его сам."""
import time

from bridge.waiting_device import WaitingDevice, CHANNELS


class FakeHeadband:
    def __init__(self) -> None:
        self.fs = 250
        self.connected = True
        self.packets_received = 7
        self.started_with = None

    def contact(self):
        return {name: 1.0 for name in CHANNELS}

    def battery(self):
        return 64

    def start(self, on_chunk):
        self.started_with = on_chunk

    def stop(self):
        self.started_with = None


def _wait_until(check, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return False


def test_bridge_comes_up_without_the_device(monkeypatch):
    """Ободок заряжается, а ноутбук включили: мост обязан подняться.

    Раньше он падал с DeviceNotFound, и менеджеру приходилось запускать
    его руками после включения прибора.
    """
    import bridge.waiting_device as wd
    monkeypatch.setattr(wd, "RETRY_S", 0.05)

    def missing():
        raise RuntimeError("прибор не подключён к системе")

    device = WaitingDevice(missing)
    try:
        assert device.connected is False
        assert device.contact() == {name: 0.0 for name in CHANNELS}
        assert device.battery() == 0
        assert device.packets_received == 0
        assert _wait_until(lambda: "не подключён" in device.last_error)
    finally:
        device.close()


def test_device_is_picked_up_when_it_appears(monkeypatch):
    import bridge.waiting_device as wd
    monkeypatch.setattr(wd, "RETRY_S", 0.05)
    box = {"ready": False}

    def factory():
        if not box["ready"]:
            raise RuntimeError("прибора ещё нет")
        return FakeHeadband()

    device = WaitingDevice(factory)
    try:
        assert device.connected is False
        box["ready"] = True
        assert _wait_until(lambda: device.connected), "прибор не подхватился"
        assert device.battery() == 64
        assert device.packets_received == 7
        assert device.last_error == ""
    finally:
        device.close()


def test_subscription_made_before_the_device_survives(monkeypatch):
    """Сервер подписывается на поток при старте, прибора тогда ещё нет."""
    import bridge.waiting_device as wd
    monkeypatch.setattr(wd, "RETRY_S", 0.05)
    box = {"ready": False}
    made = {}

    def factory():
        if not box["ready"]:
            raise RuntimeError("нет")
        made["device"] = FakeHeadband()
        return made["device"]

    def sink(chunk):
        pass

    device = WaitingDevice(factory)
    try:
        device.start(sink)          # подписка до появления прибора
        box["ready"] = True
        assert _wait_until(lambda: device.connected)
        assert made["device"].started_with is sink
    finally:
        device.close()


def test_side_channels_are_empty_without_the_device(monkeypatch):
    """Стоп сессии не должен падать, если прибора не было вовсе."""
    import bridge.waiting_device as wd
    monkeypatch.setattr(wd, "RETRY_S", 0.05)
    device = WaitingDevice(lambda: (_ for _ in ()).throw(RuntimeError("нет")))
    try:
        assert device.side_slice(0.0, 1.0) == []
        device.watchdog()      # не падает
        device.stop()
    finally:
        device.close()


# двойник ошибки моста: имя класса то же, CoreBluetooth в тестах не нужен
BluetoothDead = type("BluetoothDead", (RuntimeError,), {})


def test_dead_bluetooth_is_recognised_only_after_a_streak(monkeypatch):
    """Служба Bluetooth молчит второй раз подряд: прибор уже не найдётся.

    10.09 мост сутки стоял в таком состоянии при включённом ободке.
    Один пропуск ещё прощается: после сна ноутбука служба может замешкаться.
    """
    import bridge.waiting_device as wd
    monkeypatch.setattr(wd, "RETRY_S", 0.05)
    calls = []

    def dead():
        calls.append(1)
        raise BluetoothDead("системный Bluetooth не отвечает")

    device = WaitingDevice(dead)
    try:
        assert _wait_until(lambda: len(calls) >= 1)
        if len(calls) < 2:
            assert device.bluetooth_dead is False
        assert _wait_until(lambda: device.bluetooth_dead)
        assert "не отвечает" in device.last_error
    finally:
        device.close()


def test_missing_device_is_not_dead_bluetooth(monkeypatch):
    """Выключенный ободок это штатно, перезапускать мост из-за него нельзя."""
    import bridge.waiting_device as wd
    monkeypatch.setattr(wd, "RETRY_S", 0.05)
    calls = []

    def missing():
        calls.append(1)
        raise RuntimeError("прибор не подключён к системе")

    device = WaitingDevice(missing)
    try:
        assert _wait_until(lambda: len(calls) >= 3)
        assert device.bluetooth_dead is False
    finally:
        device.close()


def test_hung_search_counts_as_dead_bluetooth(monkeypatch):
    """Запрос к системе повис: попытка не заканчивается, значит служба мертва."""
    import bridge.waiting_device as wd
    monkeypatch.setattr(wd, "RETRY_S", 0.05)
    monkeypatch.setattr(wd, "STUCK_S", 0.2)
    release = __import__("threading").Event()

    def hung():
        release.wait(5.0)
        raise RuntimeError("прибор не подключён к системе")

    device = WaitingDevice(hung)
    try:
        assert device.bluetooth_dead is False
        assert _wait_until(lambda: device.bluetooth_dead, timeout=2.0)
    finally:
        release.set()
        device.close()
