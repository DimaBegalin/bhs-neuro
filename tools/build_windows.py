# -*- coding: utf-8 -*-
"""Собирает один Windows EXE со всеми Python-зависимостями и сайтом.

Запускать на Windows x64: ``py -3.12 tools\build_windows.py``.
PyInstaller не кросс-компилирует, поэтому macOS не может выпустить настоящий
PE-файл Windows; для этого в репозитории также есть GitHub Actions workflow.
"""
from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
NAME = "BHS-Neuro"
SDK_CHECK_NAME = "BHS-SDK-Check"
APP_NAME = "BHS-Profor"
ENV_KEYS = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "TEST_URL")

# GitHub Windows runner иногда оставляет stdout в CP1252, которая не умеет
# печатать русские диагностические сообщения сборщика.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def _settings() -> dict[str, str]:
    values = {key: os.environ.get(key, "") for key in ENV_KEYS}
    path = ROOT / ".env"
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                if key.strip() in ENV_KEYS and not values[key.strip()]:
                    values[key.strip()] = value.strip()
    return values


WINRT = [  # канал через Mind Tracker: пакеты WinRT лежат в пространстве имён winrt
    "--collect-all", "winrt",
    "--hidden-import", "winrt.windows.devices.bluetooth",
    "--hidden-import", "winrt.windows.devices.bluetooth.genericattributeprofile",
    "--hidden-import", "winrt.windows.devices.enumeration",
    "--hidden-import", "winrt.windows.foundation",
    "--hidden-import", "winrt.windows.foundation.collections",
    "--hidden-import", "winrt.windows.storage.streams",
    "--hidden-import", "bridge.win_ble_device",
]


def build_app() -> None:
    """Приложение версии 2.0: одно окно (pywebview + WebView2), без консоли.

    Настройки облака (адрес и публичный ключ Supabase) вшиваются в сборку
    файлом bhs-defaults.env, как в версии 1. Без них приложение работает
    полностью офлайн, а визиты копятся в очереди.
    """
    separator = ";"
    settings = {key: os.environ.get(key, "") for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SITE_URL")}
    for key, value in _settings().items():
        settings[key] = settings.get(key) or value
    defaults = ROOT / "build" / "bhs-defaults.env"
    defaults.parent.mkdir(parents=True, exist_ok=True)
    defaults.write_text("".join(f"{k}={v}\n" for k, v in settings.items() if v), encoding="utf-8")
    print("облако в сборке:", "настроено" if settings["SUPABASE_URL"] and settings["SUPABASE_ANON_KEY"] else "НЕ настроено")
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", APP_NAME,
        "--distpath", str(DIST),
        "--workpath", str(ROOT / "build" / "pyinstaller-app"),
        "--specpath", str(ROOT / "build"),
        "--paths", str(ROOT),
        "--add-data", f"{ROOT / 'app' / 'ui'}{separator}app/ui",
        "--add-data", f"{ROOT / 'app' / 'content'}{separator}app/content",
        "--add-data", f"{ROOT / 'app' / 'report' / 'fonts'}{separator}app/report/fonts",
        "--add-data", f"{defaults}{separator}.",
        "--collect-all", "webview",
        "--collect-all", "clr_loader",
        "--collect-all", "pythonnet",
        "--hidden-import", "clr",
        "--collect-all", "neurosdk",
        "--hidden-import", "app.device.sdk",
        "--hidden-import", "app.device.sim",
        "--hidden-import", "app.device.replay",
        "--hidden-import", "bridge.device",
        "--hidden-import", "app.device.win_ble",
        *WINRT,
        "--exclude-module", "objc",
        "--exclude-module", "Foundation",
        "--exclude-module", "Quartz",
        "--exclude-module", "CoreBluetooth",
        str(ROOT / "app" / "main.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    target = DIST / f"{APP_NAME}.exe"
    if not target.exists():
        raise SystemExit("сборка не создала EXE приложения")
    print(f"Готово: {target} ({target.stat().st_size / 1024 / 1024:.1f} МБ)")


def build_sdk_check() -> None:
    """Отдельный маленький EXE проверки ободка (этап 0 версии 2.0).

    Настройки облака ему не нужны: он только читает ободок и пишет отчёт.
    """
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--console",
        "--name", SDK_CHECK_NAME,
        "--distpath", str(DIST),
        "--workpath", str(ROOT / "build" / "pyinstaller-sdk-check"),
        "--specpath", str(ROOT / "build"),
        "--paths", str(ROOT),
        "--collect-all", "neurosdk",
        "--hidden-import", "bridge.device",
        "--hidden-import", "bridge.fake_device",
        *WINRT,
        str(ROOT / "tools" / "sdk_check.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    target = DIST / f"{SDK_CHECK_NAME}.exe"
    if not target.exists():
        raise SystemExit("сборка не создала EXE проверки ободка")
    print(f"Готово: {target} ({target.stat().st_size / 1024 / 1024:.1f} МБ)")


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Windows EXE надо собирать на Windows. "
                         "Запустите workflow build-windows или этот файл на Windows x64.")
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("для воспроизводимой сборки нужен Python 3.12 x64")
    if not (ROOT / "public" / "test.html").exists():
        raise SystemExit("нет собранного сайта public/test.html")

    settings = _settings()
    missing = [key for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY")
               if not settings.get(key)]
    if missing:
        raise SystemExit("не заданы настройки: " + ", ".join(missing))

    with tempfile.TemporaryDirectory(prefix="bhs-build-") as temporary:
        temporary_path = Path(temporary)
        defaults = temporary_path / "bhs-defaults.env"
        defaults.write_text("".join(f"{key}={settings[key]}\n" for key in ENV_KEYS
                                    if settings.get(key)), encoding="utf-8")
        public = temporary_path / "public"
        shutil.copytree(ROOT / "public", public)
        config = {"supabaseUrl": settings["SUPABASE_URL"],
                  "supabaseKey": settings["SUPABASE_ANON_KEY"]}
        (public / "config.js").write_text(
            "window.BHS_CONFIG = " + json.dumps(config, ensure_ascii=False) + ";\n",
            encoding="utf-8")
        separator = ";"  # разделитель --add-data в Windows
        command = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean", "--onefile", "--console",
            "--name", NAME,
            "--distpath", str(DIST),
            "--workpath", str(ROOT / "build" / "pyinstaller"),
            "--specpath", str(ROOT / "build"),
            "--add-data", f"{public}{separator}public",
            "--add-data", f"{defaults}{separator}.",
            "--collect-all", "neurosdk",
            "--collect-all", "reportlab",
            "--exclude-module", "bridge.ble_device",
            "--exclude-module", "bridge.app_mirror",
            "--exclude-module", "objc",
            "--exclude-module", "CoreBluetooth",
            "--exclude-module", "Foundation",
            "--exclude-module", "Quartz",
            "--exclude-module", "libdispatch",
            "--hidden-import", "analyzer.report_data",
            "--hidden-import", "report.build_html",
            "--hidden-import", "report.build_pdf",
            "--hidden-import", "report.to_pdf",
            "--hidden-import", "tools.side_decode",
            str(ROOT / "windows_entry.py"),
        ]
        subprocess.run(command, cwd=ROOT, check=True)

    target = DIST / f"{NAME}.exe"
    if not target.exists() or target.stat().st_size < 10_000_000:
        raise SystemExit("сборка не создала полноценный EXE")
    print(f"Готово: {target} ({target.stat().st_size / 1024 / 1024:.1f} МБ)")


if __name__ == "__main__":
    if "--sdk-check" in sys.argv[1:]:
        build_sdk_check()
    elif "--app" in sys.argv[1:]:
        build_app()
    else:
        main()
