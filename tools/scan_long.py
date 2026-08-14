"""Долгое сканирование: ждём, пока ободок проснётся."""
import sys
import time

from neurosdk.scanner import Scanner
from neurosdk.cmn_types import SensorFamily

# ободок Waverox опознаётся как LEHeadband. Это семейство появилось
# только в pyneurosdk2 1.0.15, на 1.0.12 прибор не находится вовсе
FAMILIES = [SensorFamily.LEHeadband, SensorFamily.LEBrainBit,
            SensorFamily.LEBrainBit2, SensorFamily.LEBrainBitBlack,
            SensorFamily.LEBrainBitFlex, SensorFamily.LEBrainBitPro,
            SensorFamily.LENeuroEEG]

seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 60
scanner = Scanner(FAMILIES)
scanner.start()
print(f"сканирую {seconds} секунд, включите ободок кнопкой", flush=True)
seen = set()
for i in range(seconds // 2):
    time.sleep(2)
    for info in scanner.sensors():
        key = str(info.SerialNumber)
        if key not in seen:
            seen.add(key)
            print(f"[{i*2:>3}s] НАЙДЕНО имя={info.Name} серийник={info.SerialNumber} "
                  f"семейство={info.SensFamily}", flush=True)
    if seen:
        break
scanner.stop()
print("итог:", len(seen), "устройств", flush=True)
