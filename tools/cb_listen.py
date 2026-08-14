"""Параллельное подключение к уже подключённому прибору через CoreBluetooth.

Штатное приложение держит соединение, поэтому обычный сканер устройство не видит:
оно не рекламируется. Системный API умеет отдавать уже подключённые устройства
по идентификатору сервиса, к ним можно подключиться вторым процессом.
"""
import sys
import time

import objc
from CoreBluetooth import (CBCentralManager, CBUUID)
from Foundation import NSObject, NSRunLoop, NSDate

SERVICE = "7E400001-B534-F393-68A9-E50E24DCCA95"
STATUS = "7E400002-B534-F393-68A9-E50E24DCCA95"
STREAMS = ["7E400004-B534-F393-68A9-E50E24DCCA95",
           "7E400005-B534-F393-68A9-E50E24DCCA95",
           "7E400007-B534-F393-68A9-E50E24DCCA95",
           "7E400008-B534-F393-68A9-E50E24DCCA95"]
import sys
LISTEN_S = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
DUMP_PATH = "data/ble_dump.jsonl"

state = {"peripheral": None, "packets": {}, "first": {}, "connected": False}
dump = []


class Delegate(NSObject):
    def centralManagerDidUpdateState_(self, central):
        if central.state() != 5:      # 5 это CBManagerStatePoweredOn
            print("Bluetooth не готов, состояние", central.state(), flush=True)
            return
        service = CBUUID.UUIDWithString_(SERVICE)
        connected = central.retrieveConnectedPeripheralsWithServices_([service])
        print(f"уже подключённых устройств с нашим сервисом: {len(connected)}", flush=True)
        for peripheral in connected:
            print(f"  {peripheral.name()} {peripheral.identifier().UUIDString()}", flush=True)
        if not connected:
            print("система не держит прибор с этим сервисом", flush=True)
            return
        state["peripheral"] = connected[0]
        central.connectPeripheral_options_(connected[0], None)

    def centralManager_didConnectPeripheral_(self, central, peripheral):
        print("подключился параллельно со штатным приложением", flush=True)
        state["connected"] = True
        peripheral.setDelegate_(self)
        peripheral.discoverServices_([CBUUID.UUIDWithString_(SERVICE)])

    def peripheral_didDiscoverServices_(self, peripheral, error):
        for service in peripheral.services():
            peripheral.discoverCharacteristics_forService_(None, service)

    def peripheral_didDiscoverCharacteristicsForService_error_(self, peripheral,
                                                               service, error):
        for characteristic in service.characteristics():
            uuid = characteristic.UUID().UUIDString().upper()
            props = characteristic.properties()
            print(f"  характеристика {uuid} свойства {props}", flush=True)
            if uuid in STREAMS or uuid == STATUS:
                peripheral.setNotifyValue_forCharacteristic_(True, characteristic)

    def peripheral_didUpdateValueForCharacteristic_error_(self, peripheral,
                                                          characteristic, error):
        uuid = characteristic.UUID().UUIDString().upper()
        value = characteristic.value()
        data = bytes(value) if value is not None else b""
        state["packets"][uuid] = state["packets"].get(uuid, 0) + 1
        dump.append((uuid, data.hex()))
        if uuid not in state["first"]:
            state["first"][uuid] = data
            print(f"ПЕРВЫЙ ПАКЕТ {uuid[:8]} длина {len(data)} данные {data.hex()[:60]}",
                  flush=True)


delegate = Delegate.alloc().init()
manager = CBCentralManager.alloc().initWithDelegate_queue_(delegate, None)

deadline = time.time() + LISTEN_S
loop = NSRunLoop.currentRunLoop()
while time.time() < deadline:
    loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.2))

import json
import os
os.makedirs("data", exist_ok=True)
with open(DUMP_PATH, "w", encoding="utf-8") as fh:
    for uuid, hexdata in dump:
        fh.write(json.dumps({"uuid": uuid, "data": hexdata}) + "\n")
print(f"сохранено пакетов в {DUMP_PATH}: {len(dump)}", flush=True)

print("=== итог ===", flush=True)
if not state["packets"]:
    print("пакетов не было", flush=True)
for uuid, count in state["packets"].items():
    print(f"{uuid}: пакетов {count}, первый {state['first'][uuid].hex()[:60]}", flush=True)
