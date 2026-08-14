"""Полный перебор раскладок пакета: заголовок, хвост, ширина, порядок байтов,
и две схемы укладки каналов.

Критерий: у настоящего ЭЭГ соседние отсчёты одного канала близки, поэтому
разброс разностей заметно меньше разброса самих значений.
"""
import json

import numpy as np

EEG = "7E400004-B534-F393-68A9-E50E24DCCA95"
PACKET_SAMPLES = 8       # подтверждено шагом счётчика пакетов
CHANNELS = 4

packets = [bytes.fromhex(json.loads(line)["data"])
           for line in open("data/ble_dump.jsonl", encoding="utf-8")
           if json.loads(line)["uuid"] == EEG]
size = len(packets[0])
print(f"пакетов ЭЭГ: {len(packets)}, длина {size}")


def unpack(packet, header, tail, width, order, signed=True):
    body = packet[header:len(packet) - tail if tail else None]
    count = len(body) // width
    return [int.from_bytes(body[i * width:(i + 1) * width], order, signed=signed)
            for i in range(count)]


def smoothness(series):
    arr = np.asarray(series, dtype=float)
    if arr.std() == 0:
        return 99.0
    return float(np.diff(arr).std() / arr.std())


results = []
need = PACKET_SAMPLES * CHANNELS
for width in (2, 3, 4):
    for header in range(0, 17):
        tail = size - header - need * width
        if tail < 0:
            continue
        for order in ("little", "big"):
            for signed in (True, False):
                # схема А: отсчёты подряд, внутри отсчёта четыре канала
                chan_a, chan_b = [], []
                for p in packets[:150]:
                    vals = unpack(p, header, tail, width, order, signed)
                    if len(vals) < need:
                        break
                    chan_a.extend(vals[0:need:CHANNELS])
                    # схема Б: канал целиком, потом следующий канал
                    chan_b.extend(vals[0:PACKET_SAMPLES])
                if len(chan_a) < 100:
                    continue
                results.append((smoothness(chan_a), "по отсчётам", header, tail,
                                width, order, signed))
                results.append((smoothness(chan_b), "по каналам", header, tail,
                                width, order, signed))

results.sort()
print("\n=== лучшие раскладки ===")
for score, scheme, header, tail, width, order, signed in results[:8]:
    print(f"  гладкость {score:.3f} | {scheme} | заголовок {header} хвост {tail} "
          f"| {width} байта {order}{' со знаком' if signed else ''}")

score, scheme, header, tail, width, order, signed = results[0]
print(f"\n=== победитель: {scheme}, заголовок {header}, хвост {tail}, "
      f"{width} байта {order} ===")
values = np.array([unpack(p, header, tail, width, order, signed)
                   for p in packets[:300]], dtype=float)
print(f"  значений в пакете: {values.shape[1]}")
if scheme == "по отсчётам":
    channels = [values[:, i::CHANNELS].ravel() for i in range(CHANNELS)]
else:
    channels = [values[:, i * PACKET_SAMPLES:(i + 1) * PACKET_SAMPLES].ravel()
                for i in range(CHANNELS)]
for i, chan in enumerate(channels):
    print(f"  канал {i}: размах {chan.min():.0f} .. {chan.max():.0f}, "
          f"разброс {chan.std():.0f}, гладкость {smoothness(chan):.3f}")

np.save("data/decoded_channels.npy", np.array(channels))
print("\nканалы сохранены в data/decoded_channels.npy")
