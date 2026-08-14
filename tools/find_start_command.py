"""Ищет команду, запускающую поток, чтобы не зависеть от штатного приложения.

Подключаемся напрямую, подписываемся на потоки и перебираем однобайтовые
команды в характеристику управления, пока не пойдут пакеты.
"""
import time

from CoreBluetooth import CBCentralManager, CBUUID
from Foundation import NSObject
from libdispatch import dispatch_queue_create
import objc

SERVICE = "7E400001-B534-F393-68A9-E50E24DCCA95"
COMMAND = "7E400003-B534-F393-68A9-E50E24DCCA95"
STREAMS = ["7E400004-B534-F393-68A9-E50E24DCCA95",
           "7E400005-B534-F393-68A9-E50E24DCCA95",
           "7E400007-B534-F393-68A9-E50E24DCCA95",
           "7E400008-B534-F393-68A9-E50E24DCCA95"]
CANDIDATES = [b"\x01", b"\x02", b"\x03", b"\x04", b"\x05", b"\x06",
              b"\x01\x00", b"\x00\x01", b"\x10", b"\x11"]

state = {"peripheral": None, "command": None, "packets": 0, "ready": False}


class D(NSObject):
    def centralManagerDidUpdateState_(self, central):
        if central.state() != 5:
            return
        found = central.retrieveConnectedPeripheralsWithServices_(
            [CBUUID.UUIDWithString_(SERVICE)])
        if not found:
            print("прибор не подключён к системе", flush=True)
            return
        state["peripheral"] = found[0]
        central.connectPeripheral_options_(found[0], None)

    def centralManager_didConnectPeripheral_(self, central, peripheral):
        state["peripheral"] = peripheral
        peripheral.setDelegate_(self)
        peripheral.discoverServices_([CBUUID.UUIDWithString_(SERVICE)])

    def peripheral_didDiscoverServices_(self, peripheral, error):
        for service in peripheral.services():
            peripheral.discoverCharacteristics_forService_(None, service)

    def peripheral_didDiscoverCharacteristicsForService_error_(self, p, service, error):
        for characteristic in service.characteristics():
            uuid = characteristic.UUID().UUIDString().upper()
            if uuid in STREAMS:
                p.setNotifyValue_forCharacteristic_(True, characteristic)
            if uuid == COMMAND:
                state["command"] = characteristic
        state["ready"] = True

    def peripheral_didUpdateValueForCharacteristic_error_(self, p, characteristic, error):
        if characteristic.UUID().UUIDString().upper() in STREAMS:
            state["packets"] += 1


delegate = D.alloc().init()
queue = dispatch_queue_create(b"bhs.find", None)
manager = CBCentralManager.alloc().initWithDelegate_queue_(delegate, queue)

deadline = time.time() + 25
while time.time() < deadline and not state["ready"]:
    time.sleep(0.3)
if not state["ready"]:
    print("не подключился", flush=True)
    raise SystemExit(1)
print("подключился, подписался, перебираю команды", flush=True)
time.sleep(2)

for value in CANDIDATES:
    before = state["packets"]
    try:
        state["peripheral"].writeValue_forCharacteristic_type_(
            value, state["command"], 1)      # 1 это запись без подтверждения
    except Exception as error:
        print(f"  {value.hex()}: записать не вышло {str(error)[:40]}", flush=True)
        continue
    time.sleep(3.5)
    gained = state["packets"] - before
    print(f"  команда {value.hex()}: пришло пакетов {gained}", flush=True)
    if gained > 20:
        print(f"\nНАШЛАСЬ: {value.hex()} запускает поток", flush=True)
        break
