# -*- coding: utf-8 -*-
"""Разбор побочных каналов: сопротивление электродов и предполагаемый пульс.

Канал 05: счётчик (шаг 1) плюс четыре uint32, сопротивление O1 O2 T3 T4 в омах.
Канал 08: счётчик (шаг 8) плюс восемь пар из трёх нулевых байт и трёхбайтового
значения. Гипотеза: фотоплетизмограф, 100 отсчётов в секунду. Подтверждение
только спектром: у настоящего пульса доминирующая частота 0.7-3 Гц.
"""
import json
import sys
from collections import defaultdict

import numpy as np
from scipy.signal import butter, sosfiltfilt, welch


def load(path):
    by_channel = defaultdict(list)
    for line in open(path, encoding="utf-8"):
        row = json.loads(line)
        by_channel[row["uuid"]].append((row["t"], bytes.fromhex(row["data"])))
    return by_channel


def resist_series(packets):
    """Сопротивление по четырём электродам, килоомы."""
    out = []
    for t, data in packets:
        if len(data) != 20:
            continue
        values = [int.from_bytes(data[4 + i * 4: 8 + i * 4], "little") / 1000.0
                  for i in range(4)]
        out.append({"t": round(t, 2),
                    "O1": round(values[0], 1), "O2": round(values[1], 1),
                    "T3": round(values[2], 1), "T4": round(values[3], 1)})
    return out


def ppg_series(packets):
    """Непрерывная волна предполагаемого пульсового канала."""
    samples = []
    for _, data in packets:
        if len(data) != 52:
            continue
        for i in range(8):
            offset = 4 + i * 6 + 3
            samples.append(int.from_bytes(data[offset:offset + 3], "little"))
    return np.array(samples, dtype=float)


def pulse_from_ppg(wave, fs=100.0):
    """Пульс из волны, если она настоящая.

    Проверка честности: доминирующая частота обязана лежать в 0.7-3 Гц
    и заметно возвышаться над фоном, иначе говорим «пульса нет».
    """
    if wave.size < fs * 20:
        return {"ok": False, "reason": "мало данных"}
    wave = wave - np.median(wave)
    sos = butter(3, [0.7, 3.0], btype="bandpass", fs=fs, output="sos")
    clean = sosfiltfilt(sos, wave)

    window = int(fs * 10)
    rates, times = [], []
    for start in range(0, len(clean) - window, int(fs * 5)):
        chunk = clean[start:start + window]
        freqs, psd = welch(chunk, fs=fs, nperseg=window)
        band = (freqs >= 0.7) & (freqs <= 3.0)
        peak_hz = float(freqs[band][np.argmax(psd[band])])
        prominence = float(psd[band].max() / (np.median(psd[band]) + 1e-12))
        if prominence > 6:
            rates.append(peak_hz * 60.0)
            times.append(start / fs)
    if len(rates) < 3:
        return {"ok": False, "reason": "пульсовая волна не выделилась"}
    return {"ok": True,
            "bpm_median": round(float(np.median(rates))),
            "bpm_min": round(float(np.min(rates))),
            "bpm_max": round(float(np.max(rates))),
            "series": [{"t": round(t, 1), "bpm": round(r)} for t, r in zip(times, rates)],
            "coverage_pct": round(len(rates) / max(1, (len(clean) - window) // int(fs * 5)) * 100)}


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/side_channels.jsonl"
    channels = load(path)
    print("пакетов: " + ", ".join("канал %s: %d" % (u, len(p))
                                  for u, p in sorted(channels.items())))
    resist = resist_series(channels.get("05", []))
    if resist:
        last = resist[-1]
        print("сопротивление, кОм: O1 %.0f  O2 %.0f  T3 %.0f  T4 %.0f"
              % (last["O1"], last["O2"], last["T3"], last["T4"]))
    wave = ppg_series(channels.get("08", []))
    print("отсчётов волны:", wave.size, "(%.0f секунд при 100 Гц)" % (wave.size / 100))
    pulse = pulse_from_ppg(wave)
    if pulse["ok"]:
        print("ПУЛЬС ПОДТВЕРЖДЁН: медиана %d уд/мин, диапазон %d..%d, покрытие %d%%"
              % (pulse["bpm_median"], pulse["bpm_min"], pulse["bpm_max"],
                 pulse["coverage_pct"]))
    else:
        print("пульс не подтверждён:", pulse["reason"])
    out = path.replace(".jsonl", "_разбор.json")
    json.dump({"resist": resist[-50:], "pulse": pulse},
              open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print("сохранено в", out)
