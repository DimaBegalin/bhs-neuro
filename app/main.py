# -*- coding: utf-8 -*-
"""Запуск приложения: окно, ядро, источник сигнала.

На Windows по умолчанию работает ободок через SDK. На Mac — проигрыватель
записанной сессии, потому что ободок там через SDK не подключается.

    python -m app.main                      # Mac: проигрыватель последней записи
    python -m app.main --device sim         # имитатор
    python -m app.main --device ble         # живой ободок на Mac через Mind Tracker
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
    if kind == "ble":
        from app.device.mac_ble import MacBleDevice
        return MacBleDevice, {}
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


def selftest(out: Path, window: bool, sessions_root: Path | None = None) -> int:
    """Проверка собранного приложения без человека: содержимое, расчёт, окно.

    Прогоняет сессию с имитатором и ускоренными модулями через тот же Api,
    что и окно, считает итог и пишет отчёт в out (JSON). С window=True ещё
    открывает настоящее окно и проверяет, что страница и мост JS поднялись.
    """
    import json
    import tempfile
    import time

    from app.device.sim import SimDevice
    from app.session.session import SessionStore as Store

    report: dict = {"version": __version__, "ok": False}
    try:
        sim = SimDevice(speed=20.0)
        link = DeviceLink(lambda: sim)
        root = sessions_root or Path(tempfile.mkdtemp()) / "sessions"
        api = Api(link, Store(root), manager="selftest", fast=True)
        api.device_connect()
        for _ in range(100):
            if api.device_state()["state"] == "streaming":
                break
            time.sleep(0.05)
        started = api.session_start({"name": "Самопроверка", "grade": 9, "lang": "ru", "with_headband": True})
        data = api.session_content()
        api.session_mark("background_closed_start", {})
        time.sleep(0.5)
        api.session_mark("background_closed_end", {})
        from app import content
        kinds = {i["id"]: i["type"] for i in content.load("interests")["items"]}
        for item in data["interests"]["items"]:
            value = {"R": 5, "I": 4, "C": 3}.get(kinds[item["id"]], 1)  # выраженный профиль R-I
            api.session_mark("interest_answer", {"item": item["id"], "value": value, "rt_ms": 1500})
        for card in data["cards"]:
            api.session_mark("card_rating", {"card": card["id"], "liked": True, "rt_ms": 900})
        summary = api.session_finish()
        link.disconnect()
        result = summary.get("result") or {}
        report.update(plan=[m["id"] for m in started["plan"]],
                      top=(result.get("recommendation") or {}).get("top"),
                      result_error=summary.get("result_error"))
        from app.settings import cloud_configured
        report["cloud_configured"] = cloud_configured()
        from app.report import MANAGER_PDF, PARENT_PDF
        folder = Path(api._store.root) / started["id"]
        report["reports"] = all((folder / name).exists() for name in (PARENT_PDF, MANAGER_PDF))
        try:
            import neurosdk  # noqa: F401  SDK ободка должен быть внутри сборки
            report["neurosdk"] = True
        except Exception as error:
            report["neurosdk"] = f"нет: {error}"
        if window:
            import webview
            seen: dict = {}

            def probe(win):
                for _ in range(40):
                    time.sleep(0.5)
                    try:
                        if win.evaluate_js("typeof window.pywebview === 'object' && !!window.pywebview.api"):
                            seen["bridge"] = True
                            seen["text"] = win.evaluate_js("document.querySelector('main').innerText.slice(0, 60)")
                            break
                    except Exception as error:
                        seen["error"] = str(error)
                win.destroy()

            win = webview.create_window("selftest", url=str(UI_INDEX), js_api=api, width=900, height=600)
            webview.start(probe, win, http_server=True)
            report["window"] = seen
        report["ok"] = bool(report.get("top")) and not report.get("result_error") and report["reports"] and (
            not window or report.get("window", {}).get("bridge") is True)
    except Exception as error:
        import traceback
        report["error"] = traceback.format_exc()
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


def _hard_exit(code: int) -> None:
    """Выход без ожидания чужих потоков.

    Встроенный HTTP-сервер pywebview и нативные потоки SDK не всегда
    завершаются сами: без этого после закрытия окна процесс оставался
    висеть в фоне и мешал следующему запуску.
    """
    import os
    logging.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Профориентация BHS с нейромониторингом")
    parser.add_argument("--device", choices=("sdk", "ble", "replay", "sim"),
                        default="sdk" if sys.platform == "win32" else "replay")
    parser.add_argument("--replay", type=Path, default=None, help="запись .npz для проигрывателя")
    parser.add_argument("--speed", type=float, default=1.0, help="ускорение проигрывателя и имитатора")
    parser.add_argument("--manager", default="", help="имя менеджера до появления входа (этап 4)")
    parser.add_argument("--debug", action="store_true", help="инструменты разработчика в окне")
    parser.add_argument("--fast", action="store_true", help="укороченные модули (разработка)")
    parser.add_argument("--selftest", type=Path, default=None,
                        help="проверить сборку без человека и записать отчёт в этот файл")
    parser.add_argument("--selftest-window", action="store_true",
                        help="в самопроверке также открыть окно")
    args = parser.parse_args(argv)
    if args.selftest is not None:
        _hard_exit(selftest(args.selftest, args.selftest_window))

    _configure_logging(args.debug)
    log.info("запуск %s, источник %s", __version__, args.device)
    store = SessionStore(sessions_dir())
    recovered = store.recover_interrupted()
    if recovered:
        log.warning("собраны оборванные сессии: %s", ", ".join(recovered))

    factory, dev_controls = device_setup(args.device, args.replay, args.speed)
    link = DeviceLink(factory)
    from app.cloud.auth import ManagerAuth
    from app.cloud.sync import Syncer
    auth = ManagerAuth()
    syncer = Syncer(auth, store.root)
    for meta in store.list():  # досылаем сессии, не ушедшие в прошлых запусках
        if meta.get("status") == "finished" and not meta.get("synced_at"):
            syncer.enqueue(store.root / meta["id"])
    syncer.start()
    api = Api(link, store, manager=args.manager, dev_controls=dev_controls, fast=args.fast,
              on_finished=syncer.enqueue, auth=auth, syncer=syncer)

    import webview
    webview.create_window("Профориентация BHS", url=str(UI_INDEX), js_api=api,
                          width=1240, height=820, min_size=(1000, 700))
    try:
        webview.start(debug=args.debug, http_server=True)
    finally:
        api.session_abort("окно приложения закрыто во время сессии")
        link.disconnect()
        log.info("выход")
    _hard_exit(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
