# -*- coding: utf-8 -*-
"""Кто и на какой машине проводит визит.

Приборов и ноутбуков много, облако у всех одно. Идентификатор визита раньше
состоял из одного времени суток, и два менеджера, начавшие тест в одну
секунду, получали одинаковый идентификатор: в облаке второй визит затирал
первый. Поэтому в идентификатор входит код рабочего места и дата.

Код берётся в таком порядке:
1. строка OPERATOR в файле .env рядом с мостом, если менеджер её задал;
2. имя компьютера, приведённое к латинице и цифрам;
3. запасное bhs, чтобы система поднялась в любом случае.

Живое имя менеджера, если оно задано строкой OPERATOR_NAME, попадает
в карточку визита: на разборе видно, кто проводил.
"""
import os
import re
import subprocess
import time

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        ".env")
FALLBACK = "bhs"
CODE_MAX = 12


def _env(key: str) -> str:
    if not os.path.exists(ENV_PATH):
        return ""
    try:
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() == key:
                return value.strip()
    except OSError:
        return ""
    return ""


# кириллица в коде недопустима: он идёт в имя файла визита и в облако.
# Русское имя переводим в латиницу, иначе код выпадал в бессмысленный хеш
# вида 7fe77581, и в панели рабочее место было не опознать
TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ә": "a", "ғ": "g", "қ": "q", "ң": "n", "ө": "o", "ұ": "u",
    "ү": "u", "һ": "h", "і": "i",
}


def _slug(raw: str) -> str:
    """Приводит любое имя к безопасному коду: латиница, цифры, длина до 12."""
    lowered = (raw or "").lower()
    latin = "".join(TRANSLIT.get(ch, ch) for ch in lowered)
    cleaned = re.sub(r"[^a-z0-9]+", "", latin)
    return cleaned[:CODE_MAX]


def _computer_name() -> str:
    try:
        out = subprocess.run(["scutil", "--get", "ComputerName"],
                             capture_output=True, text=True, timeout=3)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    import socket
    return socket.gethostname()


def operator_code() -> str:
    """Короткий код рабочего места, входит в имя каждого файла визита."""
    return _slug(_env("OPERATOR")) or _slug(_computer_name()) or FALLBACK


def operator_name() -> str:
    """Живое имя менеджера для карточки. Пусто, если не задано."""
    return _env("OPERATOR_NAME").strip()[:80]


def new_session_id(now=None) -> str:
    """Идентификатор визита, неповторимый среди всех менеджеров и дней.

    Вид: код-ГГММДД-ЧЧММСС, например anna-260814-143015.
    """
    stamp = time.strftime("%y%m%d-%H%M%S", now or time.localtime())
    return f"{operator_code()}-{stamp}"
