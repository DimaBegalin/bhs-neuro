# -*- coding: utf-8 -*-
"""Сборка облачной страницы теста: один файл для выкладки на сайт.

Страница собирается из тех же исходников, что и локальная (web/index.html
и web/assets), поэтому логика теста не может разъехаться между локальным
и облачным вариантом: меняешь исходник, пересобираешь, выкладываешь.

Скрипты и стили вшиваются внутрь, снаружи страница зовёт только мост
на 127.0.0.1:8765. То есть открываться она может откуда угодно, но нейро-слой
пишется только на ноутбуке, где работает мост и подключён ободок.

Запуск: ./.venv/bin/python tools/build_cloud_test.py
Результат: public/test.html
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
# public потому, что этот каталог выкладывается на сайт как есть,
# а Vercel и git с кириллицей в путях обращаются по-разному
OUT_DIR = os.path.join(ROOT, "public")
OUT = os.path.join(OUT_DIR, "test.html")
# порядок тот же, что в index.html: движок зависит от словарей и клиента моста
SCRIPTS = ("i18n.js", "blocks.js", "bridge-client.js", "engine.js")


def main() -> None:
    html = open(os.path.join(WEB, "index.html"), encoding="utf-8").read()

    css = open(os.path.join(WEB, "assets", "theme.css"), encoding="utf-8").read()
    html = html.replace('<link rel="stylesheet" href="assets/theme.css">',
                        "<style>\n" + css + "\n</style>")

    joined = []
    for name in SCRIPTS:
        code = open(os.path.join(WEB, "assets", name), encoding="utf-8").read()
        joined.append(f"/* --- {name} --- */\n" + code)
    tags = re.findall(r'<script src="assets/[^"]+"></script>', html)
    if len(tags) != len(SCRIPTS):
        sys.exit(f"в index.html {len(tags)} скриптов, собираю {len(SCRIPTS)}: "
                 "поправь список SCRIPTS")
    html = html.replace("\n".join(tags),
                        "<script>\n" + "\n\n".join(joined) + "\n</script>")
    # одиночные вхождения, если вёрстка когда-то разнесёт теги по файлу
    html = re.sub(r'<script src="assets/[^"]+"></script>\n?', "", html)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    size = os.path.getsize(OUT)
    assert "assets/" not in html, "остались внешние ссылки"
    print(f"собрано: {OUT} ({size/1024:.0f} КБ)")


if __name__ == "__main__":
    main()
