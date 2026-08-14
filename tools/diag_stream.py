"""Диагностика потока: пауза после подключения и повторы команды старта."""
import faulthandler
import sys
import time

faulthandler.enable()

from neurosdk.scanner import Scanner
from neurosdk.cmn_types import SensorFamily, SensorCommand

FAMILIES = [getattr(SensorFamily, n) for n in dir(SensorFamily) if n.startswith("LE")]
CHANNELS = ("T3", "T4", "O1", "O2")


def try_command(sensor, command, attempts=5, pause=2.0) -> bool:
    for i in range(attempts):
        try:
            sensor.exec_command(command)
            print(f"  {command} прошла с попытки {i + 1}", flush=True)
            return True
        except Exception as error:
            print(f"  {command} попытка {i + 1}: {str(error)[:70]}", flush=True)
            time.sleep(pause)
    return False


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
print(f"подключился к {found[0].SerialNumber}, состояние {sensor.state}", flush=True)

print("жду 6 секунд, пока канал дозреет", flush=True)
time.sleep(6)
print("батарея:", sensor.batt_power, "версия:", sensor.version, flush=True)

packets = {"n": 0, "first": None, "min": None, "max": None}


def on_signal(s, data):
    packets["n"] += 1
    if data:
        values = [float(getattr(data[0], name)) for name in CHANNELS]
        if packets["first"] is None:
            packets["first"] = values
        low, high = min(values), max(values)
        packets["min"] = low if packets["min"] is None else min(packets["min"], low)
        packets["max"] = high if packets["max"] is None else max(packets["max"], high)


sensor.signalDataReceived = on_signal
sensor.set_signal_callbacks()
print("подписался", flush=True)

print("пробую перевести в Idle", flush=True)
try_command(sensor, SensorCommand.Idle, attempts=2, pause=1.0)
time.sleep(1)

print("пробую StartSignal", flush=True)
if not try_command(sensor, SensorCommand.StartSignal, attempts=6, pause=2.5):
    print("старт сигнала не прошёл", flush=True)
    sensor.disconnect()
    sys.exit(2)

for i in range(10):
    time.sleep(2)
    print(f"  [{(i+1)*2}s] пакетов {packets['n']} первый {packets['first']} "
          f"диапазон {packets['min']} .. {packets['max']}", flush=True)

try_command(sensor, SensorCommand.StopSignal, attempts=2, pause=1.0)
sensor.unset_signal_callbacks()
print("итог пакетов:", packets["n"], flush=True)
sensor.disconnect()
