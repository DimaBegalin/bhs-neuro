"""Чтение потока напрямую по BLE, без падающей библиотеки SDK.

Сервис 7e400001 это вариант Nordic UART: 7e400003 принимает команды,
остальные характеристики шлют уведомления. Подписываемся на все потоки,
перебираем однобайтовые команды и смотрим, откуда пойдут данные.
"""
import asyncio
from collections import defaultdict

from bleak import BleakClient, BleakScanner

SERVICE = "7e400001-b534-f393-68a9-e50e24dcca95"
COMMAND = "7e400003-b534-f393-68a9-e50e24dcca95"
STATUS = "7e400002-b534-f393-68a9-e50e24dcca95"
STREAMS = ["7e400004-b534-f393-68a9-e50e24dcca95",
           "7e400005-b534-f393-68a9-e50e24dcca95",
           "7e400007-b534-f393-68a9-e50e24dcca95",
           "7e400008-b534-f393-68a9-e50e24dcca95"]
CANDIDATES = [b"\x01", b"\x02", b"\x03", b"\x05"]

counters = defaultdict(int)
samples = {}


def make_handler(uuid):
    def handler(_, data: bytearray):
        counters[uuid] += 1
        if uuid not in samples:
            samples[uuid] = bytes(data)
    return handler


# устройство уже сопряжено с системой, поэтому оно не рекламируется
# и сканером не находится: подключаемся напрямую по адресу
ADDRESS = "A9D88C1F-2BC4-066A-E707-C807B4F6A473"


async def main() -> None:
    device = await BleakScanner.find_device_by_address(ADDRESS, timeout=10.0)
    target = device or ADDRESS
    print(f"подключаюсь к {ADDRESS}", flush=True)

    async with BleakClient(target) as client:
        print("подключился", flush=True)
        status = await client.read_gatt_char(STATUS)
        print(f"статус: {status.hex()} батарея по первому байту {status[0]}", flush=True)

        for uuid in STREAMS:
            await client.start_notify(uuid, make_handler(uuid))
        print("подписался на все потоки", flush=True)

        for value in CANDIDATES:
            before = sum(counters.values())
            await client.write_gatt_char(COMMAND, value, response=False)
            await asyncio.sleep(4.0)
            after = sum(counters.values())
            print(f"команда {value.hex()}: пришло пакетов {after - before}", flush=True)
            if after > before:
                for uuid, count in counters.items():
                    if count:
                        print(f"   поток {uuid[:8]} пакетов {count} "
                              f"пример {samples[uuid].hex()[:60]} "
                              f"длина {len(samples[uuid])}", flush=True)
                print("собираю ещё 6 секунд", flush=True)
                await asyncio.sleep(6.0)
                for uuid, count in counters.items():
                    if count:
                        print(f"   итог поток {uuid[:8]}: пакетов {count}", flush=True)
                await client.write_gatt_char(COMMAND, b"\x00", response=False)
                break

        for uuid in STREAMS:
            try:
                await client.stop_notify(uuid)
            except Exception:
                pass
    print("готово", flush=True)


asyncio.run(main())
