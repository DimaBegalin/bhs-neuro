"""Разведка прибора: найти, подключиться, показать каналы, частоту и контакт.

Запускать при первом знакомстве с железом. Вывод переносится в docs/ЖЕЛЕЗО.md,
по нему сверяются имена полей пакета данных в bridge/device.py.
"""
import time

from neurosdk.scanner import Scanner
from neurosdk.cmn_types import SensorFamily

# в SDK нет отдельного семейства Headband: ободок опознаётся как одно из
# семейств BrainBit, поэтому сканируем все и берём первое найденное
# ободок Waverox опознаётся как LEHeadband. Это семейство появилось
# только в pyneurosdk2 1.0.15, на 1.0.12 прибор не находится вовсе
FAMILIES = [SensorFamily.LEHeadband, SensorFamily.LEBrainBit,
            SensorFamily.LEBrainBit2, SensorFamily.LEBrainBitBlack,
            SensorFamily.LEBrainBitFlex, SensorFamily.LEBrainBitPro,
            SensorFamily.LENeuroEEG]


def main() -> None:
    scanner = Scanner(FAMILIES)
    scanner.start()
    print("ищу устройства 10 секунд, включите ободок")
    time.sleep(10)
    scanner.stop()
    found = scanner.sensors()
    print(f"найдено: {len(found)}")
    for info in found:
        print(f"  имя={info.Name} серийник={info.SerialNumber} семейство={info.SensFamily}")
    if not found:
        print("ничего не найдено. Проверьте, что Mind Tracker закрыт: "
              "прибор держит только одно подключение")
        return

    sensor = scanner.create_sensor(found[0])
    print("батарея:", sensor.batt_power)
    print("частота сигнала:", sensor.sampling_frequency)
    print("частота сопротивления:", sensor.sampling_frequency_resist)

    packets: list = []
    sensor.set_signal_callbacks(lambda s, data: packets.append(data))
    sensor.exec_command(__import__("neurosdk.cmn_types", fromlist=["SensorCommand"])
                        .SensorCommand.StartSignal)
    time.sleep(5)
    print("пакетов сигнала за 5 секунд:", len(packets))
    if packets:
        sample = packets[0][0]
        print("поля отсчёта:", [a for a in dir(sample) if not a.startswith("_")])
    sensor.disconnect()


if __name__ == "__main__":
    main()
