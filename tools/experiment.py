"""Проверка, что метрики отражают реальное состояние.

Два отрезка: покой с закрытыми глазами и счёт в уме. Ожидание известно
заранее: на покое растёт расслабление, на счёте фокус и нагрузка.
Инструкции проговариваются голосом, чтобы человек не смотрел в экран.
"""
import asyncio
import json
import subprocess
import statistics

import websockets

LIVE = "ws://127.0.0.1:8765/live"
PHASE_S = 60


def say(text: str) -> None:
    subprocess.run(["say", "-v", "Milena", text], check=False)


async def collect(ws, seconds: int, label: str) -> dict:
    values = {"focus": [], "load": [], "relax": []}
    end = asyncio.get_event_loop().time() + seconds
    while asyncio.get_event_loop().time() < end:
        message = json.loads(await ws.recv())
        for key in values:
            if isinstance(message.get(key), (int, float)):
                values[key].append(message[key])
    result = {k: statistics.mean(v) if v else 0.0 for k, v in values.items()}
    print(f"{label}: фокус {result['focus']:.1f}, нагрузка {result['load']:.1f}, "
          f"расслабление {result['relax']:.1f}", flush=True)
    return result


async def main() -> None:
    async with websockets.connect(LIVE) as ws:
        say("Начинаем. Закройте глаза и сидите спокойно.")
        rest = await collect(ws, PHASE_S, "покой, глаза закрыты")

        say("Откройте глаза. Считайте про себя: от трёхсот отнимайте по семь. "
            "Считайте быстро, не отвлекайтесь.")
        task = await collect(ws, PHASE_S, "счёт в уме      ")

        say("Готово, можно расслабиться.")

    print()
    print("=== изменение при переходе от покоя к счёту ===")
    for key, name, expected in (("focus", "фокус", "рост"),
                                ("load", "нагрузка", "рост"),
                                ("relax", "расслабление", "падение")):
        delta = task[key] - rest[key]
        direction = "рост" if delta > 0 else "падение"
        mark = "совпало" if direction == expected else "против ожидания"
        print(f"  {name:>12}: {delta:+6.1f} ({direction}, ожидали {expected}) {mark}")


asyncio.run(main())
