"""Сбор живой записи параллельно со штатным приложением и сразу разбор.

Приложение управляет прибором, мы читаем тот же поток вторым подключением
через системный API и считаем альфа-пик своим анализатором.
"""
import sys
import time

import numpy as np
from CoreBluetooth import CBCentralManager, CBUUID
from Foundation import NSObject, NSRunLoop, NSDate

from analyzer.preprocess import bandpass, notch, epoch, reject_epochs
from analyzer.spectra import psd_of_epochs, band_power
from analyzer.iaf import compute_iaf, bands_from_iaf

SERVICE = "7E400001-B534-F393-68A9-E50E24DCCA95"
EEG = "7E400004-B534-F393-68A9-E50E24DCCA95"
CHANNELS = 4
SAMPLES = 8
BLOCK = 13
HEADER = 4
FS = 250
ADC_TO_MICROVOLTS = 2.4 * 1e6 / (6.0 * (1 << 23))
SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 60

packets = []


def decode(packet):
    out = [[] for _ in range(CHANNELS)]
    for s in range(SAMPLES):
        start = HEADER + s * BLOCK + 1
        for c in range(CHANNELS):
            chunk = packet[start + c * 3: start + (c + 1) * 3]
            out[c].append(int.from_bytes(chunk, "little", signed=True))
    return out


class Delegate(NSObject):
    def centralManagerDidUpdateState_(self, central):
        if central.state() != 5:
            return
        found = central.retrieveConnectedPeripheralsWithServices_(
            [CBUUID.UUIDWithString_(SERVICE)])
        if not found:
            print("прибор не подключён к системе, откройте приложение", flush=True)
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
                print("подписался на поток, пишу", flush=True)

    def peripheral_didUpdateValueForCharacteristic_error_(self, p, characteristic, error):
        if characteristic.UUID().UUIDString().upper() == EEG:
            value = characteristic.value()
            if value is not None:
                packets.append(bytes(value))


delegate = Delegate.alloc().init()
manager = CBCentralManager.alloc().initWithDelegate_queue_(delegate, None)

print(f"собираю {SECONDS} секунд. Наденьте ободок и закройте глаза", flush=True)
loop = NSRunLoop.currentRunLoop()
deadline = time.time() + SECONDS
last_report = time.time()
while time.time() < deadline:
    loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.2))
    if time.time() - last_report >= 10:
        last_report = time.time()
        print(f"  пакетов {len(packets)}, это {len(packets) * SAMPLES / FS:.0f} секунд",
              flush=True)

print(f"\nвсего пакетов {len(packets)}", flush=True)
if len(packets) < 100:
    print("данных мало: приложение должно быть открыто на вкладке Мониторинг")
    raise SystemExit(1)

channels = [[] for _ in range(CHANNELS)]
for p in packets:
    parsed = decode(p)
    for c in range(CHANNELS):
        channels[c].extend(parsed[c])

raw = np.array(channels, dtype=float)
signal = (raw - raw.mean(axis=1, keepdims=True)) * ADC_TO_MICROVOLTS
print(f"записано {raw.shape[1] / FS:.1f} секунд")
print("размах по каналам T3 T4 O1 O2, мкВ:", np.ptp(signal, axis=1).round(1))

clean = bandpass(notch(signal, fs=FS), fs=FS)
epochs = epoch(clean, fs=FS)
keep = reject_epochs(epochs, fs=FS)
print(f"принято эпох {int(keep.sum())} из {len(keep)}")
if not keep.any():
    print("контакт плохой, все эпохи в артефактах")
    raise SystemExit(1)

freqs, psd = psd_of_epochs(epochs, fs=FS, keep=keep)
print("\nмощность по полосам, каналы T3 T4 O1 O2:")
for name, lo, hi in (("тета", 4, 8), ("альфа", 8, 13), ("бета", 13, 30)):
    print(f"  {name:>6}: {np.round(band_power(freqs, psd, lo, hi), 1)}")

iaf, prominence = compute_iaf(freqs, psd)
print()
if iaf is None:
    print(f"альфа-пик не выделен, выраженность {prominence:.2f}")
    print("поправьте ободок: затылочные электроды должны плотно прилегать")
else:
    print(f"АЛЬФА-ПИК {iaf:.2f} Гц, выраженность {prominence:.2f}")
    bands = bands_from_iaf(iaf)
    print("личные полосы:", {k: (round(v[0], 1), round(v[1], 1))
                             for k, v in bands.items()})
    print("вывод:", "методика работает на живом сигнале"
          if 7.5 <= iaf <= 13.0 else "пик вне обычного диапазона")

np.savez_compressed("data/live_rest.npz", signal=signal, fs=np.array(FS),
                    t_start_s=np.array(0.0),
                    channels=np.array(["T3", "T4", "O1", "O2"]))
print("\nзапись сохранена в data/live_rest.npz")
