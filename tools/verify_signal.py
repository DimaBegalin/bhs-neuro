"""Финальная проверка: настоящий ли это ЭЭГ.

Декодируем весь дамп, прогоняем через наш штатный анализатор и ищем альфа-пик.
Если он находится в диапазоне 8-13 Гц, формат разобран верно и данные живые.
"""
import json

import numpy as np

from analyzer.preprocess import bandpass, notch, epoch, reject_epochs
from analyzer.spectra import psd_of_epochs, band_power
from analyzer.iaf import compute_iaf, bands_from_iaf

EEG = "7E400004-B534-F393-68A9-E50E24DCCA95"
CHANNELS = 4
SAMPLES = 8
BLOCK = 13
HEADER = 4
FS = 250
# отсчёты приходят как сырые значения 24-битного АЦП, переводим в микровольты
ADC_TO_MICROVOLTS = 2.4 * 1e6 / (6.0 * (1 << 23))


def decode(packet):
    out = [[] for _ in range(CHANNELS)]
    for s in range(SAMPLES):
        start = HEADER + s * BLOCK + 1     # первый байт блока служебный
        for c in range(CHANNELS):
            chunk = packet[start + c * 3: start + (c + 1) * 3]
            out[c].append(int.from_bytes(chunk, "little", signed=True))
    return out


packets = [bytes.fromhex(json.loads(line)["data"])
           for line in open("data/ble_dump.jsonl", encoding="utf-8")
           if json.loads(line)["uuid"] == EEG]

channels = [[] for _ in range(CHANNELS)]
for p in packets:
    parsed = decode(p)
    for c in range(CHANNELS):
        channels[c].extend(parsed[c])

raw = np.array(channels, dtype=float)
print(f"декодировано отсчётов на канал: {raw.shape[1]}, "
      f"это {raw.shape[1] / FS:.1f} секунд записи")

signal = (raw - raw.mean(axis=1, keepdims=True)) * ADC_TO_MICROVOLTS
print("размах после снятия постоянной составляющей, мкВ:",
      np.ptp(signal, axis=1).round(1))

clean = bandpass(notch(signal, fs=FS), fs=FS)
epochs = epoch(clean, fs=FS)
keep = reject_epochs(epochs, fs=FS)
print(f"принято эпох {int(keep.sum())} из {len(keep)}")
if not keep.any():
    print("все эпохи в артефактах")
    raise SystemExit(1)

freqs, psd = psd_of_epochs(epochs, fs=FS, keep=keep)
print("\nмощность по полосам, каналы T3 T4 O1 O2:")
for name, lo, hi in (("дельта", 1, 4), ("тета", 4, 8), ("альфа", 8, 13),
                     ("бета", 13, 30), ("сеть 50 Гц", 49, 51)):
    power = band_power(freqs, psd, lo, hi)
    print(f"  {name:>10}: {np.round(power, 1)}")

iaf, prominence = compute_iaf(freqs, psd)
print()
if iaf is None:
    print(f"альфа-пик не выделен, выраженность {prominence:.2f}")
else:
    print(f"АЛЬФА-ПИК {iaf:.2f} Гц, выраженность {prominence:.2f}")
    bands = bands_from_iaf(iaf)
    print("личные полосы:", {k: (round(v[0], 1), round(v[1], 1))
                             for k, v in bands.items()})
    print()
    print("вывод:", "формат разобран верно, сигнал живой"
          if 7.5 <= iaf <= 13.0 else "пик вне обычного диапазона")

np.savez_compressed("data/live_capture.npz", signal=signal, fs=np.array(FS),
                    t_start_s=np.array(0.0),
                    channels=np.array(["T3", "T4", "O1", "O2"]))
print("\nзапись сохранена в data/live_capture.npz")
