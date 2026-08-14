"""Собирает пакеты потока и проверяет гипотезы о его формате."""
import time
import struct

from CoreBluetooth import CBCentralManager, CBUUID
from Foundation import NSObject, NSRunLoop, NSDate

SERVICE = "7E400001-B534-F393-68A9-E50E24DCCA95"
EEG = "7E400004-B534-F393-68A9-E50E24DCCA95"
LISTEN_S = 20.0

packets = []


class Delegate(NSObject):
    def centralManagerDidUpdateState_(self, central):
        if central.state() != 5:
            return
        found = central.retrieveConnectedPeripheralsWithServices_(
            [CBUUID.UUIDWithString_(SERVICE)])
        if not found:
            print("прибор не подключён к системе", flush=True)
            return
        central.connectPeripheral_options_(found[0], None)

    def centralManager_didConnectPeripheral_(self, central, peripheral):
        peripheral.setDelegate_(self)
        peripheral.discoverServices_([CBUUID.UUIDWithString_(SERVICE)])

    def peripheral_didDiscoverServices_(self, peripheral, error):
        for service in peripheral.services():
            peripheral.discoverCharacteristics_forService_(None, service)

    def peripheral_didDiscoverCharacteristicsForService_error_(self, p, service, error):
        for characteristic in service.characteristics():
            if characteristic.UUID().UUIDString().upper() == EEG:
                p.setNotifyValue_forCharacteristic_(True, characteristic)

    def peripheral_didUpdateValueForCharacteristic_error_(self, p, characteristic, error):
        if characteristic.UUID().UUIDString().upper() == EEG:
            value = characteristic.value()
            if value is not None:
                packets.append(bytes(value))


delegate = Delegate.alloc().init()
manager = CBCentralManager.alloc().initWithDelegate_queue_(delegate, None)
deadline = time.time() + LISTEN_S
loop = NSRunLoop.currentRunLoop()
while time.time() < deadline:
    loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.2))

print(f"собрано пакетов: {len(packets)}", flush=True)
if len(packets) < 10:
    raise SystemExit("мало данных")

print("длины пакетов:", sorted({len(p) for p in packets}))
print()
print("первые байты трёх пакетов подряд:")
for p in packets[:3]:
    print("  ", p[:16].hex(" "))

print()
print("проверяю, где счётчик пакетов, по инкременту между соседними:")
for offset in range(0, 12):
    for size, fmt in ((2, "<H"), (4, "<I")):
        try:
            values = [struct.unpack_from(fmt, p, offset)[0] for p in packets[:40]]
        except struct.error:
            continue
        diffs = {values[i + 1] - values[i] for i in range(len(values) - 1)}
        if len(diffs) == 1 and 0 < list(diffs)[0] <= 16:
            print(f"  смещение {offset}, {size} байта: шаг {list(diffs)[0]}, "
                  f"начало {values[0]}")

print()
print("гипотеза: 12 байт заголовка, дальше 32 значения по 3 байта со знаком")
def parse_24bit(packet, header=12):
    body = packet[header:]
    out = []
    for i in range(0, len(body) - 2, 3):
        raw = int.from_bytes(body[i:i + 3], "little", signed=True)
        out.append(raw)
    return out

sample = parse_24bit(packets[5])
print(f"  значений в пакете: {len(sample)}")
print(f"  первые восемь: {sample[:8]}")
allv = [v for p in packets[:60] for v in parse_24bit(p)]
print(f"  размах по 60 пакетам: {min(allv)} .. {max(allv)}")

print()
print("альтернатива: 4 байта заголовка, 26 значений по 4 байта")
def parse_32bit(packet, header=4):
    body = packet[header:]
    return [int.from_bytes(body[i:i + 4], "little", signed=True)
            for i in range(0, len(body) - 3, 4)]
sample32 = parse_32bit(packets[5])
print(f"  значений: {len(sample32)}, первые четыре: {sample32[:4]}")
