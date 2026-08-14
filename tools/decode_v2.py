"""Разбор пакета по структуре 4 байта счётчика и 8 блоков по 13 байт.

Тринадцать байт на отсчёт это либо четыре значения по 26 бит подряд,
либо четыре значения по 3 байта плюс служебный байт.
"""
import json

import numpy as np

EEG = "7E400004-B534-F393-68A9-E50E24DCCA95"
CHANNELS = 4
SAMPLES = 8
BLOCK = 13

packets = [bytes.fromhex(json.loads(line)["data"])
           for line in open("data/ble_dump.jsonl", encoding="utf-8")
           if json.loads(line)["uuid"] == EEG]
print(f"пакетов {len(packets)}, длина {len(packets[0])}")


def smoothness(series):
    arr = np.asarray(series, dtype=float)
    if arr.std() == 0:
        return 99.0
    return float(np.diff(arr).std() / arr.std())


def signed(value, bits):
    limit = 1 << (bits - 1)
    return value - (1 << bits) if value >= limit else value


def variant_26bit(packet, header=4, msb_first=True):
    """Четыре значения по 26 бит в каждом блоке из 13 байт."""
    out = [[] for _ in range(CHANNELS)]
    for s in range(SAMPLES):
        block = packet[header + s * BLOCK: header + (s + 1) * BLOCK]
        if len(block) < BLOCK:
            return None
        bits = int.from_bytes(block, "big")
        for c in range(CHANNELS):
            shift = (CHANNELS - 1 - c) * 26 if msb_first else c * 26
            out[c].append(signed((bits >> shift) & 0x3FFFFFF, 26))
    return out


def variant_3byte(packet, header=4, order="little", extra_first=False):
    """Четыре значения по 3 байта плюс один служебный байт в блоке."""
    out = [[] for _ in range(CHANNELS)]
    for s in range(SAMPLES):
        start = header + s * BLOCK + (1 if extra_first else 0)
        for c in range(CHANNELS):
            chunk = packet[start + c * 3: start + (c + 1) * 3]
            if len(chunk) < 3:
                return None
            out[c].append(int.from_bytes(chunk, order, signed=True))
    return out


variants = {
    "26 бит, старший канал первым": lambda p: variant_26bit(p, 4, True),
    "26 бит, младший канал первым": lambda p: variant_26bit(p, 4, False),
    "3 байта little, служебный в конце": lambda p: variant_3byte(p, 4, "little", False),
    "3 байта big, служебный в конце": lambda p: variant_3byte(p, 4, "big", False),
    "3 байта little, служебный вначале": lambda p: variant_3byte(p, 4, "little", True),
    "3 байта big, служебный вначале": lambda p: variant_3byte(p, 4, "big", True),
}

print("\n=== проверка вариантов ===")
scores = []
for name, parser in variants.items():
    channels = [[] for _ in range(CHANNELS)]
    ok = True
    for p in packets[:200]:
        parsed = parser(p)
        if parsed is None:
            ok = False
            break
        for c in range(CHANNELS):
            channels[c].extend(parsed[c])
    if not ok:
        continue
    score = float(np.mean([smoothness(c) for c in channels]))
    spread = float(np.mean([np.std(c) for c in channels]))
    scores.append((score, name, channels, spread))
    print(f"  {name}: гладкость {score:.3f}, средний разброс {spread:.0f}")

scores.sort(key=lambda x: x[0])
score, name, channels, spread = scores[0]
print(f"\n=== лучший: {name}, гладкость {score:.3f} ===")
arr = np.array(channels, dtype=float)
for i in range(CHANNELS):
    print(f"  канал {i}: {arr[i].min():.0f} .. {arr[i].max():.0f}, "
          f"разброс {arr[i].std():.0f}")
np.save("data/decoded_v2.npy", arr)
print("сохранено в data/decoded_v2.npy")
