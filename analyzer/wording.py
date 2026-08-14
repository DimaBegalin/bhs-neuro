"""Готовые формулировки для разбора. Диагност читает отсюда и ничего не сочиняет."""

FORBIDDEN = ["диагноз", "обследование", "сканирование мозга", "МРТ", "IQ",
             "уровень интеллекта", "определил профессию"]

TITLES = {
    "ru": {"numeric": "Числа и логика", "spatial": "Пространство и формы",
           "verbal": "Слова и смыслы", "working_memory": "Память и внимание"},
    "kk": {"numeric": "Сандар мен логика", "spatial": "Кеңістік пен пішіндер",
           "verbal": "Сөздер мен мағыналар", "working_memory": "Жады мен зейін"},
}

VERDICTS = {
    "ru": {
        "strong": "сильный канал: результат высокий, работа даётся легко",
        "solid": "рабочий канал: результат ровный при обычных затратах",
        "costly": "дорогой канал: результат даётся большим усилием",
    },
    "kk": {
        "strong": "күшті арна: нәтиже жоғары, оңай беріледі",
        "solid": "тұрақты арна: нәтиже де, күш те қалыпты",
        "costly": "қымбат арна: нәтиже үлкен күшпен келеді",
    },
}

DIRECTIONS = {
    "numeric": "аналитика, финансы, инженерия, данные",
    "spatial": "архитектура, дизайн, инженерия, медицина",
    "verbal": "право, коммуникации, международные отношения, преподавание",
    "working_memory": "исследования, программирование, управление проектами",
}


def _level(card: dict) -> str:
    efficiency = card.get("efficiency")
    if efficiency is None:
        return "solid"
    if efficiency > 0.7:
        return "strong"
    if efficiency < -0.7:
        return "costly"
    return "solid"


def describe_domain(card: dict, lang: str = "ru") -> dict:
    lang = lang if lang in TITLES else "ru"
    level = _level(card)
    accuracy = int(round(card["accuracy"] * 100))
    seconds = card["median_rt_ms"] / 1000.0
    if lang == "ru":
        detail = f"точность {accuracy} процентов, обычный ответ за {seconds:.1f} секунды"
    else:
        detail = f"дәлдігі {accuracy} пайыз, әдеттегі жауап {seconds:.1f} секунд"
    return {"title": TITLES[lang][card["domain"]],
            "verdict": VERDICTS[lang][level],
            "detail": detail,
            "level": level}


def _attention_line(cards: list, lang: str) -> str:
    slopes = [c for c in cards if c.get("attention_slope") is not None]
    if not slopes:
        return ""
    worst = min(slopes, key=lambda c: c["attention_slope"])
    if worst["attention_slope"] > -0.01:
        return ("Внимание держалось ровно на всех блоках" if lang == "ru"
                else "Зейін барлық блокта тұрақты болды")
    title = TITLES[lang][worst["domain"]]
    return (f"Внимание заметнее всего проседало на блоке «{title}»" if lang == "ru"
            else f"Зейін «{title}» блогында ең көп төмендеді")


def describe_profile(profile: dict, lang: str = "ru") -> dict:
    cards = profile["domains"]
    ranked = sorted(cards, key=lambda c: (c.get("efficiency") is None,
                                          -(c.get("efficiency") or 0)))
    strong, costly = ranked[0], ranked[-1]
    if profile["has_eeg"]:
        headline = (f"Личная частота ритма {profile['iaf']:.1f} герца, "
                    "все показатели посчитаны от неё")
        disclaimer = ("Прибор показывает, как работает мозг на разных типах задач. "
                      "Направление подбирает специалист вместе с интересами ребёнка")
    else:
        headline = "Разбор идёт по результатам задач"
        disclaimer = ("Сигнал в этот раз был неустойчивым, поэтому показываем только "
                      "результаты задач. При желании замер можно повторить")
    return {
        "headline": headline,
        "strong": describe_domain(strong, lang),
        "costly": describe_domain(costly, lang),
        "attention": _attention_line(cards, lang),
        "directions": DIRECTIONS[strong["domain"]],
        "disclaimer": disclaimer,
    }
