# -*- coding: utf-8 -*-
"""Собирает «Профориентация BHS.app» и DMG для Mac на Apple Silicon.

Запускать на Mac: ``.venv/bin/python tools/build_mac.py``.
Ободок на Mac — только через Mind Tracker (SDK на macOS падает), поэтому
neurosdk в сборку не кладём. Подписи нет (ad-hoc): при первом запуске
macOS попросит открыть через правый клик → «Открыть».
"""
from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_windows import DIST, ROOT, _settings  # noqa: E402

sys.path.insert(0, str(ROOT))

from app import __version__  # noqa: E402

APP = "Профориентация BHS"
BUNDLE_ID = "school.bhs.profor"


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit("DMG собирается только на Mac")
    settings = _settings()
    defaults = ROOT / "build" / "bhs-defaults.env"
    defaults.parent.mkdir(parents=True, exist_ok=True)
    defaults.write_text("".join(f"{k}={v}\n" for k, v in settings.items() if v), encoding="utf-8")
    print("облако в сборке:", "настроено" if settings["SUPABASE_URL"] and settings["SUPABASE_ANON_KEY"] else "НЕ настроено")

    out = DIST / "mac"
    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", APP,
        "--osx-bundle-identifier", BUNDLE_ID,
        "--target-arch", "arm64",
        "--distpath", str(out),
        "--workpath", str(ROOT / "build" / "pyinstaller-mac"),
        "--specpath", str(ROOT / "build"),
        "--paths", str(ROOT),
        "--add-data", f"{ROOT / 'app' / 'ui'}:app/ui",
        "--add-data", f"{ROOT / 'app' / 'content'}:app/content",
        "--add-data", f"{ROOT / 'app' / 'report' / 'fonts'}:app/report/fonts",
        "--add-data", f"{defaults}:.",
        "--collect-all", "webview",
        "--hidden-import", "app.device.mac_ble",
        "--hidden-import", "app.device.sim",
        "--hidden-import", "bridge.ble_device",
        "--exclude-module", "neurosdk",
        str(ROOT / "app" / "main.py"),
    ], cwd=ROOT, check=True)

    app = out / f"{APP}.app"
    plist_path = app / "Contents" / "Info.plist"
    plist = plistlib.loads(plist_path.read_bytes())
    plist.update({
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        # без этой строки macOS убивает процесс при первом обращении к Bluetooth
        "NSBluetoothAlwaysUsageDescription": "Приложение читает сигнал ободка по Bluetooth.",
        "LSMinimumSystemVersion": "12.0",
    })
    plist_path.write_bytes(plistlib.dumps(plist))
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)

    dmg = DIST / f"BHS-Profor-{__version__}-mac-arm64.dmg"
    dmg.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / APP
        stage.mkdir()
        shutil.copytree(app, stage / app.name, symlinks=True)
        (stage / "Applications").symlink_to("/Applications")
        subprocess.run(["hdiutil", "create", "-volname", APP, "-srcfolder", str(stage),
                        "-format", "UDZO", "-ov", str(dmg)], check=True)
    print(f"Готово: {dmg} ({dmg.stat().st_size / 1024 / 1024:.1f} МБ)")


if __name__ == "__main__":
    main()
