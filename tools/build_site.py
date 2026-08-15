# -*- coding: utf-8 -*-
"""Сборка сайта: вход, панель менеджера, отчёт и тест.

Страницы собираются из web/, руками в public/ лезть не надо: следующая
сборка всё затрёт. Общие стили и логика вшиваются внутрь каждой страницы,
чтобы не плодить запросы и не ловить рассинхрон версий.

Тест собирается отдельно: у него свои словари, блоки задач и движок,
и он единственная страница, которая обязана работать без интернета.

Настройки облака кладутся отдельным файлом config.js. Ключ anon публичный
по замыслу: записи защищает не он, а правила доступа базы.

Запуск: ./.venv/bin/python tools/build_site.py
"""
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
SITE = os.path.join(WEB, "site")
OUT_DIR = os.path.join(ROOT, "public")
# страницы сайта: имя файла становится адресом, cleanUrls срезает .html
PAGES = ("index.html", "login.html", "admin.html", "report.html")
# порядок как в web/index.html: движок зависит от словарей и клиента моста
TEST_SCRIPTS = ("i18n.js", "blocks.js", "bridge-client.js", "engine.js")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def build_pages() -> None:
    theme = _read(os.path.join(SITE, "theme.css"))
    shared = _read(os.path.join(SITE, "shared.js"))
    for name in PAGES:
        html = _read(os.path.join(SITE, name))
        html = html.replace("__THEME__", theme).replace("__SHARED__", shared)
        out = os.path.join(OUT_DIR, name)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"собрано: {name} ({os.path.getsize(out)/1024:.0f} КБ)")


def build_test() -> None:
    """Страница теста: всё внутрь, ни одной внешней ссылки."""
    html = _read(os.path.join(WEB, "index.html"))
    css = _read(os.path.join(WEB, "assets", "theme.css"))
    html = html.replace('<link rel="stylesheet" href="assets/theme.css">',
                        "<style>\n" + css + "\n</style>")

    joined = []
    for name in TEST_SCRIPTS:
        joined.append(f"/* --- {name} --- */\n"
                      + _read(os.path.join(WEB, "assets", name)))
    tags = re.findall(r'<script src="assets/[^"]+"></script>', html)
    if len(tags) != len(TEST_SCRIPTS):
        sys.exit(f"в web/index.html {len(tags)} скриптов, собираю "
                 f"{len(TEST_SCRIPTS)}: поправь список TEST_SCRIPTS")
    html = html.replace("\n".join(tags),
                        "<script>\n" + "\n\n".join(joined) + "\n</script>")
    html = re.sub(r'<script src="assets/[^"]+"></script>\n?', "", html)
    assert "assets/" not in html, "в тесте остались внешние ссылки"

    out = os.path.join(OUT_DIR, "test.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"собрано: test.html ({os.path.getsize(out)/1024:.0f} КБ)")


def build_config() -> None:
    """Адрес и публичный ключ облака для страниц."""
    values = {}
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    config = {"supabaseUrl": values.get("SUPABASE_URL", ""),
              "supabaseKey": values.get("SUPABASE_ANON_KEY", "")}
    out = os.path.join(OUT_DIR, "config.js")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("/* Настройки облака. Собирается из .env, править здесь незачем.\n"
                 "   Ключ anon публичный по замыслу: записи защищают правила\n"
                 "   доступа базы, а не секретность ключа. */\n")
        fh.write("window.BHS_CONFIG = " + json.dumps(config, ensure_ascii=False,
                                                     indent=2) + ";\n")
    if not config["supabaseUrl"]:
        print("ВНИМАНИЕ: облако не настроено, вход работать не будет")
    print("собрано: config.js")


def build_vercel() -> None:
    """Настройки сайта. Лежат в корне: оттуда их читает сборка из репозитория,
    а внутри public они оказались бы просто ещё одним выложенным файлом."""
    settings = {
        "outputDirectory": "public",
        "cleanUrls": True,
        "headers": [{
            "source": "/(.*)",
            "headers": [
                {"key": "X-Content-Type-Options", "value": "nosniff"},
                {"key": "Referrer-Policy", "value": "no-referrer"},
            ],
        }],
    }
    with open(os.path.join(ROOT, "vercel.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(settings, ensure_ascii=False, indent=2))


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    build_pages()
    build_test()
    build_config()
    build_vercel()
    print(f"\nготово: {OUT_DIR}")


if __name__ == "__main__":
    main()
