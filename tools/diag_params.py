"""Читаем всё, что прибор рассказывает о себе: режимы, параметры, права доступа.

Нужно, чтобы понять, почему канал команд отвечает ERR_DATA_SEND.
"""
import time
import sys

from neurosdk.scanner import Scanner
from neurosdk.cmn_types import SensorFamily, SensorCommand

FAMILIES = [getattr(SensorFamily, n) for n in dir(SensorFamily) if n.startswith("LE")]

scanner = Scanner(FAMILIES)
scanner.start()
found = []
deadline = time.monotonic() + 180
print("жду ободок, нажмите кнопку", flush=True)
while time.monotonic() < deadline:
    found = scanner.sensors()
    if found:
        break
    time.sleep(0.5)
scanner.stop()
if not found:
    print("прибор не найден", flush=True)
    sys.exit(1)

sensor = scanner.create_sensor(found[0])
print("подключился:", found[0].SerialNumber, sensor.state, flush=True)
time.sleep(4)

for name in ("batt_power", "version", "channels_count", "amp_mode", "firmware_mode",
             "gain", "data_offset", "sampling_frequency", "sampling_frequency_resist"):
    try:
        print(f"  {name} = {getattr(sensor, name)}", flush=True)
    except Exception as error:
        print(f"  {name} недоступен: {str(error)[:60]}", flush=True)

print("параметры прибора:", flush=True)
try:
    for param in sensor.parameters:
        print("   ", param, flush=True)
except Exception as error:
    print("  список параметров недоступен:", str(error)[:80], flush=True)

print("поддержка команд:", flush=True)
for command in (SensorCommand.StartSignal, SensorCommand.StartResist,
                SensorCommand.Idle, SensorCommand.StartSignalAndResist):
    try:
        print(f"  {command} -> {sensor.is_supported_command(command)}", flush=True)
    except Exception as error:
        print(f"  {command} -> ошибка {str(error)[:50]}", flush=True)

print("пробую записать amp_mode в PowerDown и обратно", flush=True)
try:
    print("  текущий режим:", sensor.amp_mode, flush=True)
except Exception as error:
    print("  режим не прочитался:", str(error)[:60], flush=True)

sensor.disconnect()
print("отключился", flush=True)
