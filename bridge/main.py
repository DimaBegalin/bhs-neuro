"""Запуск моста. По умолчанию идёт к реальному прибору, с --fake к генератору."""
import argparse

import uvicorn

from bridge.clock import SessionClock
from bridge.realtime import RealtimeMetrics
from bridge.recorder import Recorder
from bridge.server import create_app


def build(fake: bool, channel: str = "ble", mirror_only: bool = False,
          app_db: bool = True):
    """Источник сигнала: генератор, прямой Bluetooth или библиотека производителя.

    По умолчанию берём прямой Bluetooth: библиотека производителя на macOS
    падает при доставке данных, а прямой канал проверен на живом приборе.
    """
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
        if channel == "sdk":
            from bridge.device import BrainBitDevice as Headband
        else:
            from bridge.ble_device import BleHeadbandDevice as Headband
        device = WaitingDevice(Headband)
    clock = SessionClock()
    mirror = None
    if not fake or mirror_only:
        from bridge.app_mirror import AppMirror
        mirror = AppMirror(clock)
    # оценки штатного приложения из его же базы: точные числа и все шесть
    # полей, в отличие от зеркала окна, которому видно только три
    reader = None
    if app_db:
        from bridge.mind_db import MindDbMirror, DB_PATH
        import os
        if os.path.exists(DB_PATH):
            reader = MindDbMirror(clock)
    return create_app(Recorder(fs=device.fs), clock, device,
                      RealtimeMetrics(fs=device.fs), mirror, reader)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fake", action="store_true", help="работать без прибора")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--channel", choices=("ble", "sdk"), default="ble",
                        help="ble это прямой Bluetooth, sdk это библиотека производителя")
    parser.add_argument("--mirror", action="store_true",
                        help="показания брать из штатного приложения, к прибору не лезть")
    parser.add_argument("--no-app-db", action="store_true",
                        help="не читать базу штатного приложения")
    args = parser.parse_args()
    uvicorn.run(build(args.fake, args.channel, args.mirror, not args.no_app_db),
                host="127.0.0.1", port=args.port)
