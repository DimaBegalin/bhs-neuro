"""Разведка GATT-профиля ободка напрямую, без SDK.

Нужна на случай, если официальная библиотека остаётся нерабочей на macOS:
зная сервисы и характеристики, поток можно читать самостоятельно.
"""
import asyncio

from bleak import BleakClient, BleakScanner

NAME_PREFIX = "head"


async def main() -> None:
    print("ищу ободок до 120 секунд, нажмите кнопку", flush=True)
    device = None
    for _ in range(8):
        found = await BleakScanner.discover(timeout=15.0)
        for candidate in found:
            if (candidate.name or "").lower().startswith(NAME_PREFIX):
                device = candidate
                break
        if device:
            break
    if device is None:
        print("ободок не найден", flush=True)
        return

    print(f"найден: {device.name} {device.address}", flush=True)
    async with BleakClient(device) as client:
        print("подключился напрямую, читаю профиль", flush=True)
        for service in client.services:
            print(f"сервис {service.uuid}  {service.description}", flush=True)
            for char in service.characteristics:
                props = ",".join(char.properties)
                print(f"    характеристика {char.uuid}  [{props}]", flush=True)
                if "read" in char.properties:
                    try:
                        value = await client.read_gatt_char(char.uuid)
                        printable = value.decode("utf-8", "ignore").strip()
                        print(f"        значение: {value.hex()[:40]} "
                              f"{repr(printable) if printable.isprintable() else ''}",
                              flush=True)
                    except Exception as error:
                        print(f"        читать нельзя: {str(error)[:50]}", flush=True)


asyncio.run(main())
