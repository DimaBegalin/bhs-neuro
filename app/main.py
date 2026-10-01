# -*- coding: utf-8 -*-
"""Запуск приложения: окно, ядро, источник сигнала.

На Windows по умолчанию работает ободок через SDK. На Mac — проигрыватель
записанной сессии, потому что ободок там через SDK не подключается.

    python -m app.main                      # Mac: проигрыватель последней записи
    python -m app.main --device sim         # имитатор
    python -m app.main --replay путь.npz --speed 2
"""
from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app import __version__
from app.api import Api
from app.device.link import DeviceLink
from app.session.session import SessionStore
from app.storage import BUNDLE_ROOT, PROJECT_ROOT, logs_dir, sessions_dir

UI_INDEX = BUNDLE_ROOT / "app" / "ui" / "index.html"
RECORDINGS = (PROJECT_ROOT / "сборка" / "Нейропрофориентация BHS" / "data", PROJECT_ROOT / "data")

log = logging.getLogger("app")


def _configure_logging(debug: bool) -> None:
    handler = RotatingFileHandler(logs_dir() / "app.log", maxBytes=2_000_000,
                                  backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    root.addHandler(handler)


def latest_recording() -> Path | None:
    files = [p for folder in RECORDINGS if folder.exists() for p in folder.glob("*.npz")]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def device_setup(kind: str, replay: Path | None, speed: float):
    """Фабрика источника сигнала и действия разработки для него."""
    if kind == "sdk":
        from app.device.sdk import SdkDevice
        return SdkDevice, {}
    if kind == "sim":
        from app.device.sim import SimDevice
        sim = SimDevice(speed=speed)
        return (lambda: sim), {
            "on:background_closed_start": lambda _p: setattr(sim, "eyes_closed", True),
            "on:background_closed_end": lambda _p: setattr(sim, "eyes_closed", False),
        }
    from app.device.replay import ReplayDevice
    path = replay or latest_recording()
    if path is None:
        raise SystemExit("нет записей для проигрывателя: укажите --replay путь.npz или --device sim")
    return (lambda: ReplayDevice(path, speed=speed)), {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Профориентация BHS с нейромониторингом")
    parser.add_argument("--device", choices=("sdk", "replay", "sim"),
                        default="sdk" if sys.platform == "win32" else "replay")
    parser.add_argument("--replay", type=Path, default=None, help="запись .npz для проигрывателя")
    parser.add_argument("--speed", type=float, default=1.0, help="ускорение проигрывателя и имитатора")
    parser.add_argument("--manager", default="", help="имя менеджера до появления входа (этап 4)")
    parser.add_argument("--debug", action="store_true", help="инструменты разработчика в окне")
    parser.add_argument("--fast", action="store_true", help="укороченные модули (разработка)")
    args = parser.parse_args(argv)

    _configure_logging(args.debug)
    log.info("запуск %s, источник %s", __version__, args.device)
    store = SessionStore(sessions_dir())
    recovered = store.recover_interrupted()
    if recovered:
        log.warning("собраны оборванные сессии: %s", ", ".join(recovered))

    factory, dev_controls = device_setup(args.device, args.replay, args.speed)
    link = DeviceLink(factory)
    api = Api(link, store, manager=args.manager, dev_controls=dev_controls, fast=args.fast)

    import webview
    webview.create_window("Профориентация BHS", url=str(UI_INDEX), js_api=api,
                          width=1240, height=820, min_size=(1000, 700))
    try:
        webview.start(debug=args.debug, http_server=True)
    finally:
        api.session_abort("окно приложения закрыто во время сессии")
        link.disconnect()
        log.info("выход")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
