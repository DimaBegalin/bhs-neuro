# -*- coding: utf-8 -*-
"""Сборка коробки для менеджера: один архив, который ставится в два клика.

Внутри всё, что нужно на ноутбуке: мост, расчёт, установщик с автозапуском
и ключи облака. Питон в архив не кладём, установщик ставит его сам.

Ключи облака попадают в архив, поэтому раздавать его надо адресно:
почтой, мессенджером, общим диском школы. Выкладывать в открытый доступ
нельзя, иначе анонимный ключ станет достоянием улицы.

Запуск: ./.venv/bin/python tools/make_package.py
Результат: сборка/Нейропрофориентация-BHS.zip
"""
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "сборка")
NAME = "Нейропрофориентация BHS"
ZIP_PATH = os.path.join(OUT_DIR, "Нейропрофориентация-BHS.zip")

# что кладём: код моста и расчёта, установщик, инструкция, ключи облака
INCLUDE_DIRS = ("analyzer", "bridge", "report", "upload", "web", "tools")
INCLUDE_FILES = ("requirements.txt", "pyproject.toml",
                 "Установить.command", "Удалить.command", "START.command",
                 "МЕНЕДЖЕРУ.md", "УСТАНОВКА.md")
# из .env в коробку едут только настройки облака и адрес сайта. Имя
# менеджера и его вход остаются на этой машине: иначе каждый установивший
# коробку оказался бы в панели под чужой учётной записью
ENV_KEYS = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "TEST_URL")
# что не кладём никогда: чужие визиты, отчёты с именами, служебный мусор
SKIP_DIRS = {"__pycache__", "reports", ".venv", "data", "logs"}


def _add_dir(zf: zipfile.ZipFile, name: str) -> int:
    count = 0
    for base, dirs, files in os.walk(os.path.join(ROOT, name)):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for file in files:
            if file.endswith((".pyc", ".DS_Store")):
                continue
            full = os.path.join(base, file)
            rel = os.path.relpath(full, ROOT)
            zf.write(full, os.path.join(NAME, rel))
            count += 1
    return count


def main() -> None:
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        sys.exit("нет файла .env: без ключей облака визиты не будут выгружаться")
    settings = {}
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            if key.strip() in ENV_KEYS:
                settings[key.strip()] = value.strip()
    missing = [k for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY") if not settings.get(k)]
    if missing:
        sys.exit(f"в .env нет {', '.join(missing)}: визиты не будут выгружаться")

    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(ZIP_PATH):
        os.remove(ZIP_PATH)

    total = 0
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in INCLUDE_DIRS:
            total += _add_dir(zf, name)
        for name in INCLUDE_FILES:
            path = os.path.join(ROOT, name)
            if not os.path.exists(path):
                sys.exit(f"нет файла {name}, коробка была бы неполной")
            zf.write(path, os.path.join(NAME, name))
            total += 1
        zf.writestr(os.path.join(NAME, ".env"),
                    "".join(f"{k}={settings[k]}\n" for k in ENV_KEYS if settings.get(k)))
        total += 1

    # проверка: чужих визитов и отчётов внутри быть не должно
    with zipfile.ZipFile(ZIP_PATH) as zf:
        names = zf.namelist()
    leaked = [n for n in names if "/data/" in n or "/reports/" in n
              or n.endswith(".manager_session.json")]
    if leaked:
        sys.exit(f"в архив попали чужие данные: {leaked[:3]}")
    with zipfile.ZipFile(ZIP_PATH) as zf:
        packed_env = zf.read(os.path.join(NAME, ".env")).decode("utf-8")
    for forbidden in ("OPERATOR", "access_token"):
        if forbidden in packed_env:
            sys.exit(f"в архив уехало лишнее из .env: {forbidden}")

    size = os.path.getsize(ZIP_PATH) / 1024 / 1024
    print(f"собрано: {ZIP_PATH}")
    print(f"файлов: {total}, размер: {size:.1f} МБ")
    print("\nВНИМАНИЕ: внутри ключи облака. Раздавать адресно,")
    print("в открытый доступ не выкладывать.")


if __name__ == "__main__":
    main()
