# -*- coding: utf-8 -*-
"""Точка входа единственного Windows EXE."""
from __future__ import annotations

import argparse
import logging
import multiprocessing
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from logging.handlers import RotatingFileHandler

import uvicorn

from bridge.main import build
from bridge.paths import LOGS_DIR, ensure_runtime_dirs


def _configure_logging() -> None:
    ensure_runtime_dirs()
    handler = RotatingFileHandler(LOGS_DIR / "bridge.log", maxBytes=2_000_000,
                                  backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status",
                                    timeout=1.5) as response:
            return response.status == 200
    except Exception:
        return False


def _open_when_ready(port: int, url: str) -> None:
    for _ in range(60):
        if _alive(port):
            webbrowser.open(url)
            return
        time.sleep(0.25)


def _autostart(enable: bool) -> None:
    if sys.platform != "win32":
        raise RuntimeError("автозапуск доступен только в Windows")
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                        winreg.KEY_SET_VALUE) as key:
        if enable:
            command = f'"{os.path.abspath(sys.executable)}" --no-browser'
            winreg.SetValueEx(key, "BHS Neuro", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "BHS Neuro")
            except FileNotFoundError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Нейропрофориентация BHS")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--fake", action="store_true",
                        help="демонстрация без ободка")
    parser.add_argument("--no-browser", action="store_true",
                        help="не открывать страницу после запуска")
    parser.add_argument("--install-autostart", action="store_true")
    parser.add_argument("--remove-autostart", action="store_true")
    args = parser.parse_args(argv)

    if args.install_autostart or args.remove_autostart:
        _autostart(args.install_autostart)
        print("Автозапуск включён." if args.install_autostart
              else "Автозапуск выключен.")
        return 0

    _configure_logging()
    local_url = f"http://127.0.0.1:{args.port}/app"
    if _alive(args.port):
        if not args.no_browser:
            webbrowser.open(local_url)
        return 0

    if not args.no_browser:
        threading.Thread(target=_open_when_ready, args=(args.port, local_url),
                         daemon=True).start()
    try:
        app = build(fake=args.fake, channel=None, mirror_only=False, app_db=True)
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False,
                    log_config=None)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        logging.exception("не удалось запустить приложение")
        raise


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
