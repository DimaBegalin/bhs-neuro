"""Запуск моста. По умолчанию идёт к реальному прибору, с --fake к генератору."""
import argparse
import sys

import uvicorn

from bridge.clock import SessionClock
from bridge.realtime import RealtimeMetrics
from bridge.recorder import Recorder
from bridge.server import create_app

MACOS = sys.platform == "darwin"


def default_channel(platform: str = sys.platform) -> str:
    """Каким способом читать прибор на этой системе.

    На macOS прямой Bluetooth через CoreBluetooth: библиотека производителя
    там падает при доставке данных, а прямой канал проверен на живом приборе
    и умеет подключаться вторым к потоку штатного приложения.

    На Windows наоборот: библиотека производителя это её родная система, она
    сама включает поток и сопротивление, а подключиться вторым к чужому
    потоку система не даёт. Прямой канал там идёт через bleak и остаётся
    запасным, пока не найдена своя команда включения потока.
    """
    return "ble" if platform == "darwin" else "sdk"


def headband_class(channel: str, platform: str = sys.platform):
    """Класс прибора под канал и систему. Импорт ленивый: у каждого свои
    системные библиотеки, и грузить чужие на этой системе нельзя."""
    if channel == "sdk":
        from bridge.device import BrainBitDevice
        return BrainBitDevice
    if platform == "darwin":
        from bridge.ble_device import BleHeadbandDevice
        return BleHeadbandDevice
    from bridge.bleak_device import BleakHeadbandDevice
    return BleakHeadbandDevice


def build(fake: bool, channel: str | None = None, mirror_only: bool = False,
          app_db: bool = True):
    """Источник сигнала: генератор, прямой Bluetooth или библиотека производителя."""
    channel = channel or default_channel()
    if fake or mirror_only:
        # в режиме зеркала сигнал нам не нужен: показания берём из приложения,
        # а генератор держит контракт устройства, чтобы мост не менялся
        from bridge.fake_device import FakeDevice
        device = FakeDevice()
    else:
        # мост живёт весь день и поднимается вместе с системой, а ободок то
        # включён, то заряжается. Поэтому прибор не требуется в момент старта:
        # обёртка ищет его сама и подхватывает, как только он появится
        from bridge.waiting_device import WaitingDevice
        device = WaitingDevice(headband_class(channel))
    clock = SessionClock()
    mirror = None
    # зеркало окна снимает экран средствами macOS, на других системах его нет.
    # Профиль без него считается, зеркало только контрольный слой
    if MACOS and (not fake or mirror_only):
        from bridge.app_mirror import AppMirror
        mirror = AppMirror(clock)
    # оценки штатного приложения из его же базы: точные числа и все шесть
    # полей, в отличие от зеркала окна, которому видно только три
    reader = None
    if app_db:
        from bridge.mind_db import MindDbMirror, find_db
        if find_db():
            reader = MindDbMirror(clock)
    return create_app(Recorder(fs=device.fs), clock, device,
                      RealtimeMetrics(fs=device.fs), mirror, reader)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fake", action="store_true", help="работать без прибора")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--channel", choices=("ble", "sdk"), default=None,
                        help="ble это прямой Bluetooth, sdk это библиотека "
                             f"производителя. На этой системе по умолчанию "
                             f"{default_channel()}")
    parser.add_argument("--mirror", action="store_true",
                        help="показания брать из штатного приложения, к прибору не лезть")
    parser.add_argument("--no-app-db", action="store_true",
                        help="не читать базу штатного приложения")
    args = parser.parse_args()
    uvicorn.run(build(args.fake, args.channel, args.mirror, not args.no_app_db),
                host="127.0.0.1", port=args.port)
