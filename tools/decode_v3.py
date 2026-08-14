"""Полная сетка смещений: где начинаются данные и где внутри блока стоят каналы.

Критерий прежний, гладкость, но добавлен второй: у верной раскладки каналы
слабо коррелируют между собой, а при съехавшей разбивке в каждый канал
подмешиваются чужие отсчёты и корреляция подскакивает.
"""
import json
import itertools

import numpy as np

EEG = "7E400004-B534-F393-68A9-E50E24DCCA95"
CHANNELS = 4
SAMPLES = 8
BLOCK = 13

packets = [bytes.fromhex(json.loads(line)["data"])
           for line in open("data/ble_dump.jsonl", encoding="utf-8")
           if json.loads(line)["uuid"] == EEG]
print(f"пакетов {len(packets)}, длина {len(packets[0])}")


def parse(packet, start, inner, order, signed):
    """start это смещение первого блока, inner это смещение данных внутри блока."""
    out = np.empty((CHANNELS, SAMPLES))
    for s in range(SAMPLES):
        base = start + s * BLOCK + inner
        if base + 12 > len(packet):
            return None
        for c in range(CHANNELS):
            chunk = packet[base + c * 3: base + (c + 1) * 3]
            out[c, s] = int.from_bytes(chunk, order, signed=signed)
    return out


def score(series):
    """Чем меньше, тем больше похоже на настоящий сигнал."""
    smooth = np.mean([np.diff(c).std() / c.std() if c.std() > 0 else 9
                      for c in series])
    corr = np.abs(np.corrcoef(series))
    cross = (corr.sum() - np.trace(corr)) / (CHANNELS * (CHANNELS - 1))
    return smooth, cross


results = []
sample = packets[:250]
for start, inner, order, signed in itertools.product(
        range(0, 13), range(0, 2), ("little", "big"), (True, False)):
    collected = [[] for _ in range(CHANNELS)]
    ok = True
    for p in sample:
        parsed = parse(p, start, inner, order, signed)
        if parsed is None:
            ok = False
            break
        for c in range(CHANNELS):
            collected[c].extend(parsed[c])
    if not ok:
        continue
    series = np.array(collected)
    if series.shape[1] < 100:
        continue
    smooth, cross = score(series)
    results.append((smooth, cross, start, inner, order, signed))

results.sort(key=lambda r: r[0])
print("\n=== десять лучших по гладкости ===")
print(f"{'гладкость':>10} {'связь каналов':>14}  начало  внутри  порядок  знак")
for smooth, cross, start, inner, order, signed in results[:10]:
    print(f"{smooth:>10.3f} {cross:>14.3f}  {start:>6} {inner:>7}  {order:>7}  "
          f"{'да' if signed else 'нет'}")

smooth, cross, start, inner, order, signed = results[0]
print(f"\nлучшая раскладка: начало {start}, внутри блока {inner}, "
      f"{order}, знак {'да' if signed else 'нет'}")
print(f"гладкость {smooth:.3f}, связь каналов {cross:.3f}")
