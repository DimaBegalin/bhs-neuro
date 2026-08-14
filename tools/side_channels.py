"""Пассивный сбор нерасшифрованных каналов прибора во время живой сессии.

Слушаем всё, кроме основного потока сигнала (его пишет мост): статус 0002,
поток 0005 (похож на сопротивление электродов), 0007 (предположительно
пульсовой канал) и 0008 (похож на датчик движения). Только подписка,
никаких команд: идёт боевой тест, вмешиваться нельзя.
"""
import json
import sys
import time

from CoreBluetooth import CBCentralManager, CBUUID
from Foundation import NSObject
from libdispatch import dispatch_queue_create

SERVICE = "7E400001-B534-F393-68A9-E50E24DCCA95"
STREAMS = ["7E400002-B534-F393-68A9-E50E24DCCA95",
           "7E400005-B534-F393-68A9-E50E24DCCA95",
           "7E400007-B534-F393-68A9-E50E24DCCA95",
           "7E400008-B534-F393-68A9-E50E24DCCA95"]
SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 420.0
OUT = "data/side_channels.jsonl"

state = {"peripheral": None, "n": 0}
sink = open(OUT, "w", encoding="utf-8")
t0 = time.monotonic()


class D(NSObject):
    def centralManagerDidUpdateState_(self, central):
        if central.state() != 5:
            return
        found = central.retrieveConnectedPeripheralsWithServices_(
            [CBUUID.UUIDWithString_(SERVICE)])
        if not found:
            print("прибор не найден", flush=True)
            return
        state["peripheral"] = found[0]
        central.connectPeripheral_options_(found[0], None)

    def centralManager_didConnectPeripheral_(self, central, peripheral):
        state["peripheral"] = peripheral
        peripheral.setDelegate_(self)
        peripheral.discoverServices_([CBUUID.UUIDWithString_(SERVICE)])
        print("подключился пассивно", flush=True)

    def peripheral_didDiscoverServices_(self, peripheral, error):
        for service in peripheral.services():
            peripheral.discoverCharacteristics_forService_(None, service)

    def peripheral_didDiscoverCharacteristicsForService_error_(self, p, service, error):
        for ch in service.characteristics():
            if ch.UUID().UUIDString().upper() in STREAMS:
                p.setNotifyValue_forCharacteristic_(True, ch)

    def peripheral_didUpdateValueForCharacteristic_error_(self, p, ch, error):
        uuid = ch.UUID().UUIDString().upper()
        value = ch.value()
        if uuid in STREAMS and value is not None:
            state["n"] += 1
            sink.write(json.dumps({"t": round(time.monotonic() - t0, 3),
                                   "uuid": uuid[6:8], "data": bytes(value).hex()}) + "\n")


delegate = D.alloc().init()
manager = CBCentralManager.alloc().initWithDelegate_queue_(
    delegate, dispatch_queue_create(b"bhs.side", None))

deadline = time.monotonic() + SECONDS
while time.monotonic() < deadline:
    time.sleep(2)
sink.close()
print("собрано пакетов побочных каналов:", state["n"], flush=True)
