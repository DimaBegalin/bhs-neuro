"""Запуск моста. По умолчанию идёт к реальному прибору, с --fake к генератору."""
import argparse
import sys

import uvicorn

from bridge.clock import SessionClock
from bridge.realtime import RealtimeMetrics
from bridge.recorder import Recorder
from bridge.server import create_app


def default_channel(platform: str = sys.platform) -> str:
    """Надёжный канал по умолчанию для текущей системы."""
    return "ble" if platform == "darwin" else "sdk"


def headband_class(channel: str, platform: str = sys.platform):
    """Ленивый импорт не загружает чужие системные библиотеки."""
    if channel == "sdk":
        from bridge.device import BrainBitDevice
        return BrainBitDevice
    if platform == "darwin":
        from bridge.ble_device import BleHeadbandDevice
        return BleHeadbandDevice
    raise RuntimeError("прямой BLE-канал доступен только на macOS; "
                       "на Windows используйте --channel sdk")


def build(fake: bool, channel: str | None = None, mirror_only: bool = False,
          app_db: bool = True):
    """Источник сигнала: генератор, прямой Bluetooth или библиотека производителя.

    По умолчанию берём прямой Bluetooth: библиотека производителя на macOS
    падает при доставке данных, а прямой канал проверен на живом приборе.
    """
    channel = channel or default_channel()
    if mirror_only and sys.platform != "darwin":
        raise RuntimeError("зеркало Mind Tracker доступно только на macOS")
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
    if sys.platform == "darwin" and (not fake or mirror_only):
        from bridge.app_mirror import AppMirror
        mirror = AppMirror(clock)
    # оценки штатного приложения из его же базы: точные числа и все шесть
    # полей, в отличие от зеркала окна, которому видно только три
    reader = None
    if app_db:
        from bridge.mind_db import MindDbMirror, find_db
        db_path = find_db()
        if db_path:
            reader = MindDbMirror(clock, db_path)
    return create_app(Recorder(fs=device.fs), clock, device,
                      RealtimeMetrics(fs=device.fs), mirror, reader)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fake", action="store_true", help="работать без прибора")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--channel", choices=("ble", "sdk"), default=None,
                        help="канал прибора; по умолчанию ble на macOS, sdk на Windows")
    parser.add_argument("--mirror", action="store_true",
                        help="показания брать из штатного приложения, к прибору не лезть")
    parser.add_argument("--no-app-db", action="store_true",
                        help="не читать базу штатного приложения")
    args = parser.parse_args()
    uvicorn.run(build(args.fake, args.channel, args.mirror, not args.no_app_db),
                host="127.0.0.1", port=args.port)
