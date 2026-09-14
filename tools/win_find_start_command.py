# -*- coding: utf-8 -*-
"""Ищет команду включения потока ободка. Для Windows и Linux, через bleak.

Зачем: на macOS поток включает штатное приложение, а мост подключается
вторым. На Windows так нельзя, и запасному каналу моста (bleak_device.py)
нужна своя команда в характеристике 7e400003. Скрипт подключается,
подписывается на потоки и по очереди шлёт кандидатов, пока не пойдут пакеты
сигнала. Найденное надо записать в .env: HEADBAND_START_COMMAND=<hex>.

Перед запуском: Mind Tracker закрыт, ободок включён кнопкой и мигает.
Запуск: .venv\\Scripts\\python.exe tools\\win_find_start_command.py
"""
import asyncio
import sys
from collections import defaultdict

from bleak import BleakClient, BleakScanner

sys.path.insert(0, ".")
from bridge.headband_protocol import (  # noqa: E402
    COMMAND, PULSE, RESIST, SERVICE, SIGNAL, STATUS, DEVICE_NAME)

STREAMS = [SIGNAL, RESIST, "7E400007-B534-F393-68A9-E50E24DCCA95", PULSE]
# однобайтовые команды и пары, как перебирали на macOS в find_start_command.py
CANDIDATES = [b"\x01", b"\x02", b"\x03", b"\x04", b"\x05", b"\x06",
              b"\x01\x00", b"\x00\x01", b"\x10", b"\x11"]
WAIT_S = 4.0

counters = defaultdict(int)


def _handler(characteristic, data):
    counters[str(characteristic.uuid).upper()] += 1


def _is_headband(device, adv):
    uuids = [str(u).upper() for u in (adv.service_uuids or [])]
    return SERVICE in uuids or (device.name or "").lower().startswith(DEVICE_NAME.lower())


async def main() -> None:
    print("ищу ободок в эфире, нажмите на нём кнопку...", flush=True)
    device = await BleakScanner.find_device_by_filter(_is_headband, timeout=20.0)
    if device is None:
        sys.exit("прибор не найден: он должен мигать, а Mind Tracker быть закрыт")
    print(f"нашёл {device.name} {device.address}", flush=True)

    async with BleakClient(device) as client:
        status = await client.read_gatt_char(STATUS)
        print(f"статус: {status.hex()}, заряд {status[0]}%", flush=True)
        for uuid in STREAMS:
            try:
                await client.start_notify(uuid, _handler)
            except Exception as error:
                print(f"  {uuid[4:8]}: подписка не удалась ({error})", flush=True)

        await asyncio.sleep(WAIT_S)
        if counters[SIGNAL]:
            print(f"поток уже идёт без команды: {counters[SIGNAL]} пакетов за {WAIT_S:.0f} с")
            print("команда не нужна, HEADBAND_START_COMMAND оставьте пустым")
            return

        for value in CANDIDATES:
            before = counters[SIGNAL]
            await client.write_gatt_char(COMMAND, value, response=False)
            await asyncio.sleep(WAIT_S)
            gained = counters[SIGNAL] - before
            print(f"команда {value.hex()}: пакетов сигнала {gained}", flush=True)
            if gained > 0:
                print(f"\nНАЙДЕНО. Впишите в .env строку: HEADBAND_START_COMMAND={value.hex()}")
                return
        print("\nни одна команда поток не включила. Побочные каналы за это время:")
        for uuid, count in counters.items():
            print(f"  {uuid[4:8]}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
