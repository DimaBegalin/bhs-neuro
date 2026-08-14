"""Минимальный колбэк: только счётчик, никакого доступа к полям отсчёта.

Делит гипотезы: падает ли нативная библиотека сама по себе или на разборе данных.
"""
import faulthandler
import sys
import time

faulthandler.enable()

from neurosdk.scanner import Scanner
from neurosdk.cmn_types import SensorFamily, SensorCommand

FAMILIES = [getattr(SensorFamily, n) for n in dir(SensorFamily) if n.startswith("LE")]
counter = {"packets": 0, "samples": 0}


def on_signal(sensor, data):
    counter["packets"] += 1
    counter["samples"] += len(data)


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
print("подключился:", found[0].SerialNumber, flush=True)
time.sleep(5)

sensor.signalDataReceived = on_signal
sensor.set_signal_callbacks()
print("подписался лёгким колбэком", flush=True)

started = False
for attempt in range(6):
    try:
        sensor.exec_command(SensorCommand.StartSignal)
        started = True
        print(f"поток стартовал с попытки {attempt + 1}", flush=True)
        break
    except Exception as error:
        print(f"  попытка {attempt + 1}: {str(error)[:60]}", flush=True)
        time.sleep(2)

if not started:
    print("команда старта не прошла", flush=True)
    sensor.disconnect()
    sys.exit(2)

for i in range(8):
    time.sleep(2)
    print(f"  [{(i+1)*2}s] пакетов {counter['packets']}, отсчётов {counter['samples']}",
          flush=True)

sensor.exec_command(SensorCommand.StopSignal)
sensor.unset_signal_callbacks()
print("ИТОГ: пакетов", counter["packets"], "отсчётов", counter["samples"], flush=True)
sensor.disconnect()
