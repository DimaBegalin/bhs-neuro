"""Пассивное прослушивание потока параллельно со штатным приложением.

На macOS соединение с BLE-устройством держит система, поэтому второй процесс
может подписаться на те же уведомления. Ничего не отправляем: если приложение
уже запустило поток, пакеты пойдут сами.
"""
import asyncio
from collections import defaultdict

from bleak import BleakClient, BleakScanner

ADDRESS = "A9D88C1F-2BC4-066A-E707-C807B4F6A473"
STATUS = "7e400002-b534-f393-68a9-e50e24dcca95"
STREAMS = ["7e400004-b534-f393-68a9-e50e24dcca95",
           "7e400005-b534-f393-68a9-e50e24dcca95",
           "7e400007-b534-f393-68a9-e50e24dcca95",
           "7e400008-b534-f393-68a9-e50e24dcca95"]

counters = defaultdict(int)
first = {}
lengths = defaultdict(set)


def make_handler(uuid):
    def handler(_, data: bytearray):
        counters[uuid] += 1
        lengths[uuid].add(len(data))
        if uuid not in first:
            first[uuid] = bytes(data)
    return handler


async def main() -> None:
    device = await BleakScanner.find_device_by_address(ADDRESS, timeout=8.0)
    print("подключаюсь параллельно с приложением", flush=True)
    async with BleakClient(device or ADDRESS, timeout=20.0) as client:
        print("подключился, приложение при этом не отключилось", flush=True)
        try:
            status = await client.read_gatt_char(STATUS)
            print(f"статус: {status.hex()} батарея {status[0]}", flush=True)
        except Exception as error:
            print("статус не прочитался:", str(error)[:60], flush=True)

        for uuid in STREAMS:
            try:
                await client.start_notify(uuid, make_handler(uuid))
            except Exception as error:
                print(f"  {uuid[:8]} подписка не удалась: {str(error)[:50]}", flush=True)
        print("слушаю 20 секунд, ничего не отправляю", flush=True)

        for i in range(4):
            await asyncio.sleep(5)
            total = sum(counters.values())
            print(f"  [{(i+1)*5}s] пакетов всего {total}", flush=True)

        print("=== итог ===", flush=True)
        for uuid in STREAMS:
            if counters[uuid]:
                print(f"поток {uuid[:8]}: пакетов {counters[uuid]}, "
                      f"длины {sorted(lengths[uuid])}, "
                      f"первый {first[uuid].hex()}", flush=True)
        if not sum(counters.values()):
            print("пакетов нет: приложение поток не запускало", flush=True)

        for uuid in STREAMS:
            try:
                await client.stop_notify(uuid)
            except Exception:
                pass


asyncio.run(main())
