# -*- coding: utf-8 -*-
"""Собирает «Профориентация BHS.app» и DMG для Mac.

Apple Silicon: ``.venv/bin/python tools/build_mac.py``.
Universal (Apple Silicon + Intel): ``.venv-universal/bin/python tools/build_mac.py --universal``.
M1 на macOS 12 Monterey: ``.venv-universal/bin/python tools/build_mac.py --monterey`` — только
Apple Silicon, но из окружения на OpenBLAS: numpy и scipy из обычного .venv собраны
под Apple Accelerate и требуют macOS 14.
Окружению Universal нужны universal2-колёса numpy, scipy и Pillow: их нет
на PyPI, они склеиваются из arm64 и x86_64 через ``delocate-merge``
(docs/v2/README.md, «Сборка и CI»).
Ободок на Mac — только через Mind Tracker (SDK на macOS падает), поэтому
neurosdk в сборку не кладём. Подписи нет (ad-hoc): при первом запуске
macOS попросит открыть через правый клик → «Открыть».
"""
from __future__ import annotations

import os
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
MONTEREY = (12, 6)
BUNDLE_ID = "school.bhs.profor"


def _min_macos(app: Path, arch: str) -> tuple[int, ...]:
    """Самая новая macOS, которую требует хоть одна библиотека внутри приложения."""
    newest = (10, 13)
    for f in app.rglob("*"):
        if not f.is_file() or not (f.suffix in (".so", ".dylib") or os.access(f, os.X_OK)):
            continue
        out = subprocess.run(["vtool", "-arch", arch, "-show-build", str(f)],
                             capture_output=True, text=True).stdout
        for line in out.splitlines():
            if line.strip().startswith("minos"):
                newest = max(newest, tuple(int(x) for x in line.split()[1].split(".")))
    return newest


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit("DMG собирается только на Mac")
    settings = _settings()
    defaults = ROOT / "build" / "bhs-defaults.env"
    defaults.parent.mkdir(parents=True, exist_ok=True)
    defaults.write_text("".join(f"{k}={v}\n" for k, v in settings.items() if v), encoding="utf-8")
    print("облако в сборке:", "настроено" if settings["SUPABASE_URL"] and settings["SUPABASE_ANON_KEY"] else "НЕ настроено")

    universal = "--universal" in sys.argv[1:]
    monterey = "--monterey" in sys.argv[1:]
    arch = "universal2" if universal else "arm64"
    suffix = "universal" if universal else "m1-monterey" if monterey else "arm64"
    out = DIST / "mac"
    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", APP,
        "--osx-bundle-identifier", BUNDLE_ID,
        "--target-arch", arch,
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
    })
    # минимальная macOS — по библиотекам внутри: иначе на старой системе приложение
    # молча падает после «Всё равно открыть», а не говорит, что macOS слишком старая
    minimum = max(_min_macos(app, a) for a in (("arm64", "x86_64") if universal else ("arm64",)))
    if monterey and minimum > MONTEREY:
        raise SystemExit(f"сборка требует macOS {'.'.join(map(str, minimum))}: для Monterey "
                         "собирайте из .venv-universal (numpy и scipy на OpenBLAS)")
    plist["LSMinimumSystemVersion"] = ".".join(map(str, minimum))
    print("минимальная macOS:", plist["LSMinimumSystemVersion"])
    plist_path.write_bytes(plistlib.dumps(plist))
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)

    dmg = DIST / f"BHS-Profor-{__version__}-mac-{suffix}.dmg"
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
