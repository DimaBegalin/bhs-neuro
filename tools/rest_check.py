"""Контрольная запись покоя на живом приборе.

Главная проверка методики на реальном железе: садимся, закрываем глаза,
пишем минуту, ищем альфа-пик. Ожидание: 8-12 Гц с выраженностью выше 1,5.
Запуск: ./.venv/bin/python tools/rest_check.py [секунды]
"""
import sys
import time

import numpy as np

from analyzer.iaf import compute_iaf, bands_from_iaf
from analyzer.preprocess import bandpass, notch, epoch, reject_epochs
from analyzer.spectra import psd_of_epochs
from bridge.device import BrainBitDevice

SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 60


def main() -> None:
    print("ищу прибор")
    device = BrainBitDevice()
    print(f"подключился, частота {device.fs} Гц, батарея {device.battery()} процентов")

    chunks: list[np.ndarray] = []
    device.start(lambda chunk: chunks.append(chunk))
    print(f"пишу {SECONDS} секунд. Сядьте удобно и закройте глаза")
    for left in range(SECONDS, 0, -10):
        time.sleep(10)
        print(f"  осталось {left - 10} секунд, контакт {device.contact()}", flush=True)
    device.stop()

    signal = np.concatenate(chunks, axis=1) if chunks else np.zeros((4, 0))
    print("отсчётов записано:", signal.shape[1])
    if signal.shape[1] < device.fs * 10:
        print("данных слишком мало, проверьте посадку ободка")
        return

    print("размах по каналам, мкВ:", np.ptp(signal, axis=1).round(1))
    clean = bandpass(notch(signal, fs=device.fs), fs=device.fs)
    epochs = epoch(clean, fs=device.fs)
    keep = reject_epochs(epochs, fs=device.fs)
    print(f"принято эпох {int(keep.sum())} из {len(keep)}")
    if not keep.any():
        print("все эпохи в артефактах, контакт плохой")
        return

    freqs, psd = psd_of_epochs(epochs, fs=device.fs, keep=keep)
    iaf, prominence = compute_iaf(freqs, psd)
    if iaf is None:
        print(f"альфа-пик не выделен, выраженность {prominence:.2f}")
        print("проверьте затылочные электроды O1 и O2, волосы под ними")
        return

    print(f"альфа-пик {iaf:.2f} Гц, выраженность {prominence:.2f}")
    bands = bands_from_iaf(iaf)
    print("личные полосы:", {k: (round(v[0], 1), round(v[1], 1)) for k, v in bands.items()})
    verdict = "методика работает на живом сигнале" if 8.0 <= iaf <= 12.5 \
        else "пик вне обычного диапазона, нужна перепроверка посадки"
    print("вывод:", verdict)


if __name__ == "__main__":
    main()
