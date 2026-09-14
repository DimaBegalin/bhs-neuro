# -*- coding: utf-8 -*-
"""Припасы для коробки: Python и все библиотеки одним набором.

Зачем. На ноутбуке менеджера установка не должна ничего скачивать и ничего
собирать из исходников. Скачивание упирается в интернет школы, а сборка из
исходников заставляет macOS предлагать инструменты разработчика: менеджер
видит предложение поставить Xcode и справедливо пугается.

Поэтому Python и все библиотеки кладутся в коробку готовыми. Один пакет,
pyneurosdk2, готовой сборки не имеет вовсе, только исходники: собираем его
здесь один раз, и в коробку он едет уже собранным.

Припасы зависят от системы и от вида процессора, поэтому коробка собирается
на такой же машине, на какой будет работать. Метка внутри это фиксирует,
и установщик по ней понимает, годятся ли припасы.

Запуск: ./.venv/bin/python tools/build_vendor.py
Результат: вендор/ рядом с проектом
"""
import glob
import json
import os
import platform
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "вендор")
PYTHON_DIR = os.path.join(VENDOR, "python")
WHEELS_DIR = os.path.join(VENDOR, "колёса")
MARK_PATH = os.path.join(VENDOR, "метка.json")
PYTHON_VERSION = "3.12"


def _uv() -> str:
    for candidate in (os.path.expanduser("~/.local/bin/uv"), shutil.which("uv")):
        if candidate and os.path.exists(candidate):
            return candidate
    sys.exit("нет uv: поставьте его (curl -LsSf https://astral.sh/uv/install.sh | sh)")


def copy_python() -> str:
    """Готовый Python рядом с программой, а не системный.

    Системный Python на ноутбуке менеджера может быть любым или отсутствовать,
    а на свежей macOS обращение к нему само по себе вызывает предложение
    поставить инструменты разработчика.
    """
    uv = _uv()
    subprocess.run([uv, "python", "install", PYTHON_VERSION],
                   capture_output=True, check=False)
    system = "macos" if sys.platform == "darwin" else sys.platform
    machine = {"arm64": "aarch64", "AMD64": "x86_64"}.get(platform.machine(),
                                                          platform.machine())
    pattern = os.path.join(os.path.expanduser("~/.local/share/uv/python"),
                           f"cpython-{PYTHON_VERSION}.*-{system}-{machine}-*")
    found = sorted(d for d in glob.glob(pattern) if os.path.isdir(d)
                   and os.listdir(d))
    if not found:
        sys.exit(f"не нашёл готовый Python {PYTHON_VERSION} для {system}-{machine}")
    source = found[-1]

    if os.path.exists(PYTHON_DIR):
        shutil.rmtree(PYTHON_DIR)
    shutil.copytree(source, PYTHON_DIR, symlinks=True)

    # пометка «этим Python управляет uv» запрещает ставить в него библиотеки.
    # В коробке это наш собственный экземпляр, управлять им больше некому
    for base, _, files in os.walk(PYTHON_DIR):
        if "EXTERNALLY-MANAGED" in files:
            os.remove(os.path.join(base, "EXTERNALLY-MANAGED"))
    return os.path.basename(source)


def collect_wheels() -> int:
    """Все библиотеки готовыми сборками, включая ту, у которой её нет."""
    if os.path.exists(WHEELS_DIR):
        shutil.rmtree(WHEELS_DIR)
    os.makedirs(WHEELS_DIR)
    python = os.path.join(PYTHON_DIR, "bin", "python3")
    if not os.path.exists(python):
        python = os.path.join(PYTHON_DIR, "python.exe")
    result = subprocess.run(
        [python, "-m", "pip", "wheel", "--wheel-dir", WHEELS_DIR,
         "-r", os.path.join(ROOT, "requirements.txt")],
        capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit("не собрались библиотеки:\n" + result.stderr[-800:])
    return len(os.listdir(WHEELS_DIR))


def main() -> None:
    os.makedirs(VENDOR, exist_ok=True)
    print("Кладу готовый Python...")
    build = copy_python()
    print(f"  {build}")
    print("Собираю библиотеки...")
    count = collect_wheels()
    print(f"  готовых сборок: {count}")

    with open(MARK_PATH, "w", encoding="utf-8") as fh:
        json.dump({"python": PYTHON_VERSION, "build": build,
                   "platform": sys.platform, "machine": platform.machine()},
                  fh, ensure_ascii=False, indent=2)

    size = sum(os.path.getsize(os.path.join(b, f))
               for b, _, files in os.walk(VENDOR) for f in files)
    print(f"\nприпасы готовы: {VENDOR} ({size/1024/1024:.0f} МБ)")
    print(f"под {sys.platform} {platform.machine()}")


if __name__ == "__main__":
    main()
