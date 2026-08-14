"""Ловит ободок в момент пробуждения и снимает контрольную запись покоя.

Запускается заранее, дальше человек нажимает кнопку на ободке когда удобно.
"""
import sys
import time

import numpy as np

from analyzer.iaf import compute_iaf, bands_from_iaf
from analyzer.preprocess import bandpass, notch, epoch, reject_epochs
from analyzer.spectra import psd_of_epochs
from bridge.device import BrainBitDevice

WAIT_S = int(sys.argv[1]) if len(sys.argv) > 1 else 180
REST_S = int(sys.argv[2]) if len(sys.argv) > 2 else 60


def main() -> None:
    print(f"жду ободок до {WAIT_S} секунд. Нажмите кнопку, индикатор должен мигать",
          flush=True)
    device = BrainBitDevice(scan_seconds=WAIT_S)
    info = getattr(device, "info", None)
    print(f"ПОДКЛЮЧИЛСЯ: имя={getattr(info, 'Name', '')} "
          f"серийник={getattr(info, 'SerialNumber', '')} "
          f"семейство={getattr(info, 'SensFamily', '')}", flush=True)
    print(f"частота {device.fs} Гц, батарея {device.battery()} процентов", flush=True)

    chunks: list[np.ndarray] = []
    device.start(lambda chunk: chunks.append(chunk))
    print(f"пишу {REST_S} секунд, сядьте удобно и закройте глаза", flush=True)
    for step in range(REST_S // 10):
        time.sleep(10)
        total = sum(c.shape[1] for c in chunks)
        print(f"  {(step + 1) * 10}s, отсчётов {total}, контакт {device.contact()}",
              flush=True)
    device.stop()

    signal = np.concatenate(chunks, axis=1) if chunks else np.zeros((4, 0))
    print("итого отсчётов:", signal.shape[1], flush=True)
    if signal.shape[1] < device.fs * 10:
        print("данных мало, проверьте посадку ободка")
        return

    print("размах по каналам, мкВ:", np.ptp(signal, axis=1).round(1), flush=True)
    np.savez_compressed("data/rest_check.npz", signal=signal,
                        fs=np.array(device.fs), t_start_s=np.array(0.0),
                        channels=np.array(["T3", "T4", "O1", "O2"]))

    clean = bandpass(notch(signal, fs=device.fs), fs=device.fs)
    epochs = epoch(clean, fs=device.fs)
    keep = reject_epochs(epochs, fs=device.fs)
    print(f"принято эпох {int(keep.sum())} из {len(keep)}", flush=True)
    if not keep.any():
        print("все эпохи в артефактах, контакт плохой")
        return

    freqs, psd = psd_of_epochs(epochs, fs=device.fs, keep=keep)
    iaf, prominence = compute_iaf(freqs, psd)
    if iaf is None:
        print(f"альфа-пик не выделен, выраженность {prominence:.2f}")
        return
    print(f"АЛЬФА-ПИК {iaf:.2f} Гц, выраженность {prominence:.2f}", flush=True)
    bands = bands_from_iaf(iaf)
    print("личные полосы:", {k: (round(v[0], 1), round(v[1], 1)) for k, v in bands.items()})
    print("вывод:", "методика работает на живом сигнале" if 8.0 <= iaf <= 12.5
          else "пик вне обычного диапазона, проверить посадку")


if __name__ == "__main__":
    main()
