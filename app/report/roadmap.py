# -*- coding: utf-8 -*-
"""Career & University Roadmap BHS: PDF-дорожная карта ученика 8–10 класса по итогу теста.

Вёрстка — HTML в фирменном стиле BHS (Halvar, оранжевый), PDF печатает
браузер, который есть на компьютере: Edge на Windows, Chrome или Edge на Mac.
Без браузера дорожная карта не собирается, остальные отчёты — да. Для
11 класса шаблона нет. Тексты — по документам BHS
«Career & University Roadmap» 8–10 класс; только на русском.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
from html import escape as e
from pathlib import Path

from app.report.model import STYLE_STRONG, _style_scores
from app.report.texts import NEXT_STEPS, STYLE, STYLE_STRENGTH, T, TYPES
from app.storage import BUNDLE_ROOT

log = logging.getLogger(__name__)

ROADMAP_PDF = "дорожная-карта.pdf"
ROADMAP_HTML = "дорожная-карта.html"
FONTS = BUNDLE_ROOT / "app" / "ui" / "fonts"
_printing = threading.Lock()  # фоновая печать и кнопка не запускают браузер одновременно

PATHWAY = ["Career Guidance", "Academic Planning", "Portfolio", "University List", "Personal Statement", "Application"]
PRINCIPLES = [("Дать попробовать", "Проекты, конкурсы, дебаты, волонтёрство и реальные задачи."),
              ("Дать увидеть", "Профессии, университеты, встречи с экспертами и профессиональная среда."),
              ("Дать время", "Интересы подростка меняются. Важно не торопить окончательный выбор.")]

GRADES = {
    8: {
        "stage": "EXPLORE", "stage_ru": "Исследовать", "pathway_step": 0,
        "headline": "{name}: сильные стороны, с которых начинается путь в Гарвард",
        "lead": "Интересы превращаются в первые осознанные шаги.",
        "hero": "Гарвард? Почему бы и нет. У вашего ребёнка уже есть качества, интересы и сильные стороны, "
                "которые можно развивать для поступления в Гарвард и университеты топ-10 мира. "
                "8 класс — время исследовать себя, найти интересные направления и сдать первый SAT.",
        "comment": "В 8 классе важно не торопить ребёнка с окончательным выбором. Главная задача — расширить кругозор, "
                   "попробовать разные направления и заметить то, в чём хочется развиваться глубже.",
        "profile_note": "Направления, которые по итогам диагностики стоит исследовать подробнее.",
        "second": "Что хочется попробовать",
        "task_title": "Исследовать и пробовать",
        "task": "В 8 классе ученик начинает понимать свои интересы через реальные действия: проекты, кружки, "
                "конкурсы, волонтёрство, встречи с профессионалами и новые образовательные возможности.",
        "actions": [
                    ('Пройти профориентационную диагностику', 'сентябрь'),
                    ('Определить 2–3 направления, которые интересно исследовать', 'октябрь'),
                    ('Начать подготовку к SAT в BHS и сдать первый SAT, чтобы узнать стартовый балл', 'до мая'),
                    ('Системно заниматься английским, чтобы в 9 классе начать подготовку к IELTS', 'весь год'),
                    ('Попробовать новую внеклассную активность (extracurricular)', '1 полугодие'),
                    ('Принять участие минимум в одном проекте или конкурсе', 'до апреля'),
                    ('Посетить профориентационное мероприятие или встречу с университетом', 'весь год'),
                    ('Начать фиксировать достижения, проекты и сертификаты', 'с сентября'),
                    ],
        "result": "К концу 8 класса ученик лучше понимает свои интересы, у него есть несколько пробных активностей "
                  "и первые результаты, с которыми можно осознанно двигаться дальше в 9 классе.",
        "parents": "В 8 классе задача семьи — не выбрать профессию за ребёнка, а создать условия, в которых он сможет "
                   "безопасно исследовать свои интересы и увидеть свои сильные стороны.",
        "next": ("9 класс · BUILD", "Выбрать направления, пересдать SAT, начать подготовку к IELTS и запустить долгосрочный проект."),
    },
    9: {
        "stage": "BUILD", "stage_ru": "Строить", "pathway_step": 1,
        "headline": "{name} строит профиль, с которым поступают в Гарвард и топ-10 университетов мира",
        "lead": "Теперь интересы превращаются в первые реальные достижения.",
        "hero": "Гарвард? Это реально. Профиль сильного кандидата строится не за последний год, а шаг за шагом. "
                "9 класс — время выбрать, во что вкладываться, и начать создавать результаты, которые увидит приёмная комиссия.",
        "comment": "В 9 классе важно переходить от простого исследования к осознанному выбору. Ребёнку не обязательно знать "
                   "точную профессию, но стоит определить 1–2 направления, которые хочется развивать глубже, "
                   "и начать строить вокруг них собственный профиль.",
        "profile_note": "Наиболее перспективные направления по итогам диагностики.",
        "second": "Что стоит развивать",
        "task_title": "Формировать профиль",
        "task": "Выбрать 1–2 направления и выстроить вокруг них проекты, внеклассные активности и первые достижения. "
                "Лучше одно дело, которое развивается весь год, чем много разовых попыток.",
        "actions": [
                    ('Выбрать 1–2 основных направления интереса', 'сентябрь–октябрь'),
                    ('Пересдать SAT и поднять балл по сравнению с 8 классом', 'до мая'),
                    ('Начать подготовку к IELTS в BHS', 'с января'),
                    ('Запустить собственный долгосрочный проект', '1 полугодие'),
                    ('Выбрать одну внеклассную активность для системного развития', 'сентябрь'),
                    ('Участвовать в конкурсах, олимпиадах, конференциях или социальных инициативах', 'весь год'),
                    ('Попробовать себя в лидерской роли', 'весь год'),
                    ('Определить интересующие страны и образовательные системы', 'до мая'),
                    ('Вести единый список достижений и результатов', 'постоянно'),
                    ],
        "result": "К концу 9 класса у ученика есть понятное направление интересов, несколько подтверждающих "
                  "активностей и первые результаты, которыми можно гордиться.",
        "parents": "Помогайте ребёнку выбирать не количество активностей, а их качество и смысл. "
                   "Лучше один проект, который развивается год, чем десять разовых сертификатов.",
        "next": ("10 класс · STRENGTHEN", "SAT и IELTS на высокие баллы, рекомендательные письма, эссе с января."),
    },
    10: {
        "stage": "STRENGTHEN", "stage_ru": "Усиливать", "pathway_step": 2,
        "headline": "{name} готовит заявку уровня Гарварда и топ-10 университетов мира",
        "lead": "Начинается переход от интереса к стратегии поступления.",
        "hero": "Гарвард? Пора готовиться. 10 класс — решающий год: SAT и IELTS на высокие баллы, рекомендательные письма "
                "и эссе с января. Вся эта программа есть в BHS.",
        "comment": "В 10 классе профиль ученика должен становиться более целостным. Интересы, академические результаты, "
                   "внеклассные активности и лидерский опыт постепенно складываются в понятную историю кандидата.",
        "profile_note": "Наиболее перспективные направления по итогам диагностики.",
        "second": "Что стоит развивать",
        "task_title": "Усилить профиль",
        "task": "До конца учебного года сдать SAT и IELTS на высокие баллы, получить рекомендательные письма "
                "и с января начать работу над эссе. Всё это вместе с проектами и лидерским опытом складывается "
                "в понятную историю кандидата.",
        "actions": [
                    ('Определить академическое направление и составить предварительный список университетов', 'сентябрь–октябрь'),
                    ('Сдать SAT на высокий балл: ориентир для топ-10 университетов — 1500+', 'до конца года'),
                    ('Сдать IELTS на высокий балл: ориентир — 7.5+', 'до конца года'),
                    ('Получить рекомендательные письма от двух учителей и школьного консультанта', 'до мая'),
                    ('Начать работу над эссе: Personal Statement и дополнительные эссе университетов', 'с января'),
                    ('Взять лидерскую роль в проекте или организации', 'весь год'),
                    ('Усилить 1–2 ключевые внеклассные активности, участвовать в международных конкурсах', 'весь год'),
                    ('Собрать портфолио достижений', 'к маю'),
                    ],
        "result": "К концу 10 класса у ученика есть баллы SAT и IELTS, рекомендательные письма, черновик эссе "
                  "и предварительный список университетов. В 11 классе остаётся финальная подача.",
        "parents": "В 10 классе важно перейти от вопроса «куда поступать?» к вопросу "
                   "«какого кандидата университет должен увидеть в моём ребёнке?».",
        "next": ("11 класс · APPLY", "Финальный список университетов, доработка эссе, стипендии и подача заявок."),
    },
}



def _css(fonts: str) -> str:
    return f"""
@font-face {{ font-family: Halvar; src: url("{fonts}/HalvarBreit-Rg.woff2"); font-weight: 400; }}
@font-face {{ font-family: Halvar; src: url("{fonts}/HalvarBreit-Md.woff2"); font-weight: 500; }}
@font-face {{ font-family: Halvar; src: url("{fonts}/HalvarBreit-Bd.woff2"); font-weight: 700; }}
@font-face {{ font-family: Halvar; src: url("{fonts}/HalvarBreit-Blk.woff2"); font-weight: 900; }}
@page {{ size: A4; margin: 0; }}
:root {{ --ink: #101114; --muted: #6b6f78; --line: #ebe6e1; --soft: #fff3ea; --accent: #e8590c;
        --accent-2: #ff8a3d; --dark: #08090b; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font: 10.5pt/1.5 -apple-system, "Helvetica Neue", Arial, sans-serif; color: var(--ink);
       -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
.page {{ width: 210mm; height: 297mm; padding: 16mm 17mm 14mm; position: relative; page-break-after: always;
        overflow: hidden; display: flex; flex-direction: column; }}
.page:last-child {{ page-break-after: auto; }}
h1, h2, h3, .display {{ font-family: Halvar, sans-serif; }}
.top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8mm; }}
.logo {{ display: flex; align-items: center; gap: 3mm; }}
.mark {{ width: 11mm; height: 11mm; border-radius: 3mm; background: linear-gradient(135deg, var(--accent-2), var(--accent));
        color: #fff; font: 900 9.5pt Halvar; display: grid; place-items: center; letter-spacing: .3pt; }}
.wordmark b {{ display: block; font: 900 10.5pt/1.1 Halvar; letter-spacing: 1.2pt; }}
.wordmark span {{ font: 500 6.8pt Halvar; letter-spacing: 1.6pt; color: var(--muted); }}
.badge {{ font: 700 7.5pt Halvar; letter-spacing: 1.4pt; color: var(--accent); border: 1.2pt solid var(--accent);
         padding: 1.6mm 3mm; border-radius: 10mm; }}
.dark .wordmark span {{ color: #a9adb6; }} .dark .badge {{ color: var(--accent-2); border-color: var(--accent-2); }}
.cover {{ background: var(--dark); color: #fff; margin: -16mm -17mm 0; padding: 14mm 17mm 9mm; }}
.kicker {{ font: 700 8pt Halvar; letter-spacing: 2pt; color: var(--accent-2); }}
.cover h1 {{ font-size: 22pt; line-height: 1.18; font-weight: 900; margin: 3mm 0 4mm; }}
.blank {{ display: inline-block; min-width: 52mm; border-bottom: 1.5pt solid var(--accent-2); height: .95em;
         vertical-align: baseline; }}
.cover .lead {{ font-size: 11.5pt; color: #d6d8de; }}
.fields {{ display: grid; grid-template-columns: 1.4fr 1fr; gap: 6mm; margin-top: 6mm; }}
.field {{ font: 500 7.5pt Halvar; letter-spacing: 1.2pt; color: #a9adb6; border-bottom: 1pt solid #3a3c42; padding-bottom: 2mm; }}
.field .val {{ display: inline-block; margin-top: 1.5mm; font: 700 11pt Halvar; letter-spacing: .3pt; color: #fff; }}
.hero {{ display: flex; gap: 5mm; margin: 6mm 0 0; padding: 4mm 6mm; background: var(--soft); border-radius: 4mm;
        border-left: 1.6mm solid var(--accent); }}
.hero p {{ font-size: 10.5pt; }}
.hero b {{ font-family: Halvar; font-weight: 900; color: var(--accent); display: block; font-size: 12pt; margin-bottom: 1.5mm; }}
h2 {{ font-size: 15pt; font-weight: 900; margin: 6mm 0 1.5mm; display: flex; align-items: baseline; gap: 3mm; }}
h2 .n {{ color: var(--accent); font-size: 11pt; }}
.note {{ color: var(--muted); font-size: 9pt; margin-bottom: 3.5mm; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ font: 700 7.5pt Halvar; letter-spacing: 1.2pt; text-align: left; color: var(--muted);
     border-bottom: 1.2pt solid var(--ink); padding: 2mm 0; }}
td {{ border-bottom: .6pt solid var(--line); padding: 2mm 0; vertical-align: middle; }}
.score {{ text-align: right; white-space: nowrap; font-family: Halvar; font-weight: 500; }}
.score i {{ display: inline-block; width: 13mm; border-bottom: .8pt solid var(--ink); }}
.comment {{ margin-top: 4mm; padding: 4mm 5mm; border: .8pt solid var(--line); border-radius: 3mm; font-size: 9.5pt; }}
.comment b, .label {{ font: 700 7.5pt Halvar; letter-spacing: 1.2pt; color: var(--accent); display: block; margin-bottom: 1.5mm; }}
.chips {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2.5mm 6mm; margin: 2mm 0 1mm; }}
.chips span {{ display: flex; align-items: center; gap: 2.5mm; font-size: 10pt; }}
.box {{ width: 3.6mm; height: 3.6mm; border: 1pt solid var(--ink); border-radius: .8mm; flex: none; display: inline-block; }}
.lines {{ display: grid; gap: 5mm; margin-top: 3mm; }}
.lines div {{ border-bottom: .8pt solid #b9bcc4; height: 6mm; font-family: Halvar; font-weight: 700; color: var(--accent); font-size: 9pt; }}
.card {{ border: .8pt solid var(--line); border-radius: 4mm; padding: 4.5mm 6mm; margin-top: 3.5mm; }}
.task {{ background: var(--dark); color: #fff; border-radius: 4mm; padding: 6mm 7mm; margin-top: 4mm; }}
.task h3 {{ font-size: 13pt; font-weight: 900; color: var(--accent-2); margin-bottom: 2mm; }}
.task p {{ color: #d6d8de; }}
.plan td {{ padding: 2.8mm 0; font-size: 9.8pt; }}
.plan td:first-child {{ width: 7mm; }}
.when {{ white-space: nowrap; font: 700 7.6pt Halvar; color: var(--accent); padding-left: 3mm; padding-right: 2mm; }}
.status {{ white-space: nowrap; font-size: 8pt; color: var(--muted); text-align: right; }}
.status span {{ margin-left: 3mm; display: inline-flex; align-items: center; gap: 1.2mm; }}
.status .box {{ width: 3mm; height: 3mm; border-color: #8b8f98; }}
.result {{ margin-top: 6mm; padding: 5mm 6mm; background: var(--soft); border-radius: 4mm; }}
.result h3 {{ font-size: 11.5pt; font-weight: 900; margin-bottom: 1.5mm; }}
.quote {{ font: 700 12.5pt/1.4 Halvar; margin: 2mm 0 5mm; }}
.principles {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 4mm; }}
.principles div {{ border-radius: 4mm; padding: 5mm; background: var(--soft); }}
.principles b {{ font: 900 18pt Halvar; color: var(--accent); display: block; }}
.principles h3 {{ font-size: 9pt; letter-spacing: 1pt; margin: 1.5mm 0 1.5mm; }}
.principles p {{ font-size: 9pt; color: #3a3c42; }}
.path {{ display: flex; flex-wrap: wrap; gap: 2mm; margin: 2mm 0 4mm; }}
.path span {{ font: 700 7.4pt Halvar; letter-spacing: .8pt; padding: 2mm 3mm; border-radius: 10mm; border: .8pt solid var(--line); color: var(--muted); }}
.path span.on {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
.next {{ display: flex; gap: 4mm; align-items: baseline; padding: 4mm 5mm; border: 1pt dashed var(--accent); border-radius: 3mm; }}
.next b {{ font: 900 9pt Halvar; color: var(--accent); white-space: nowrap; letter-spacing: .8pt; }}
.all-in {{ margin-top: 4mm; padding: 4.5mm 6mm; border-radius: 4mm; background: var(--accent); color: #fff; font-size: 9.8pt; }}
.all-in b {{ font: 900 9pt Halvar; letter-spacing: 1.2pt; display: block; margin-bottom: 1.5mm; }}
.disclaimer {{ font-size: 7.6pt; color: var(--muted); margin-top: 5mm; }}
.bar {{ display: inline-block; width: 34mm; height: 2.4mm; background: var(--soft); border-radius: 2mm;
        vertical-align: middle; margin-right: 3mm; overflow: hidden; }}
.bar i {{ display: block; height: 100%; background: var(--accent); border-radius: 2mm; }}
.score b {{ display: inline-block; width: 8mm; text-align: right; }}
.top-type td {{ font-weight: 600; }}
.cluster {{ padding: 2.2mm 0; border-bottom: .6pt solid var(--line); }}
.cluster:last-child {{ border-bottom: none; }}
.cluster b {{ font: 700 10.5pt Halvar; display: block; margin-bottom: .8mm; }}
.cluster span {{ font-size: 9.4pt; color: #3a3c42; }}
.filled {{ list-style: none; display: grid; gap: 2.4mm; margin-top: 2mm; counter-reset: n; }}
.filled li {{ counter-increment: n; display: flex; gap: 3mm; font-size: 10pt; }}
.filled li::before {{ content: counter(n); font: 700 9pt Halvar; color: var(--accent); }}
.foot {{ margin-top: auto; display: flex; justify-content: space-between; border-top: .6pt solid var(--line);
        padding-top: 3mm; font: 500 7pt Halvar; letter-spacing: 1.2pt; color: var(--muted); }}
"""




def logo() -> str:
    return ('<div class="logo"><div class="mark">BHS</div><div class="wordmark"><b>BETA HIGH SCHOOL</b>'
            '<span>CAREER GUIDANCE</span></div></div>')


def foot(n: int, grade: int, stage: str) -> str:
    return f'<div class="foot"><span>BETA HIGH SCHOOL · CAREER & UNIVERSITY ROADMAP</span><span>{grade} КЛАСС · {stage} · {n} / 4</span></div>'


def top(grade: int, g: dict, dark=False) -> str:
    return f'<div class="top{" dark" if dark else ""}">{logo()}<div class="badge">{grade} КЛАСС · {g["stage"]}</div></div>'




def _browser() -> str | None:
    """Chromium-браузер для печати в PDF: на Windows Edge стоит всегда."""
    if sys.platform == "win32":
        roots = [os.environ.get(k, "") for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
        found = [Path(r) / sub for r in roots if r for sub in (
            r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe")]
    else:
        found = [Path(p) for p in (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium")]
    for path in found:
        if path.exists():
            return str(path)
    return shutil.which("chrome") or shutil.which("chromium") or shutil.which("google-chrome")


def _data(model: dict) -> dict:
    """Из модели отчёта — то, что печатается в дорожной карте."""
    result = model["result"]
    rec = result["recommendation"]
    types = sorted(model["interests"]["types"], key=lambda t: -t["score"])
    flat = result["interests"]["level"] == "flat" or not rec["top"]
    strengths = [] if flat else [f"{t['name']} интерес — {t['desc']}" for t in types[:2]]
    style = _style_scores(result.get("work_style"))
    if style:
        best = max(style, key=style.get)
        if style[best] >= STYLE_STRONG:
            strengths.append(f"{STYLE[best]['ru']} — {STYLE_STRENGTH[best]['ru']}")
    steps = (list(T["flat_steps"]["ru"]) if flat else
             [NEXT_STEPS[c]["ru"][0] for c in rec["top"]][:3])
    return {"name": model["student"]["name"], "grade": model["student"]["grade"], "date": model["date"],
            "types": types, "clusters": [] if flat else model["clusters"], "flat": flat,
            "strengths": strengths or [T["no_strength"]["ru"]], "steps": steps,
            "comment": (model.get("comment") or {}).get("text")}


def render_roadmap_html(model: dict) -> str:
    d = _data(model)
    grade = d["grade"]
    g = GRADES[grade]
    headline = e(g["headline"].replace("{name}", d["name"]))
    top2 = {t["type"] for t in d["types"][:2]} if not d["flat"] else set()
    profile_rows = "".join(
        f'<tr class="{"top-type" if t["type"] in top2 else ""}"><td>{e(t["name"])}</td><td class="score">'
        f'<span class="bar"><i style="width:{max(0, min(100, t["score"])):.0f}%"></i></span><b>{t["score"]:.0f}</b> / 100</td></tr>'
        for t in d["types"])
    clusters = ("".join(f'<div class="cluster"><b>{i}. {e(c["title"])}</b><span>{e(", ".join(c["professions"]) or "—")}</span></div>'
                        for i, c in enumerate(d["clusters"], 1))
                or f'<p>{e(T["interests_flat"]["ru"])}</p>')
    strengths = "".join(f"<li>{e(s)}</li>" for s in d["strengths"])
    steps = "".join(f"<li>{e(s)}</li>" for s in d["steps"])
    actions = "".join(
        f'<tr><td><i class="box"></i></td><td>{e(a)}</td><td class="when">{e(w)}</td><td class="status">'
        '<span><i class="box"></i>Начал(а)</span><span><i class="box"></i>В процессе</span><span><i class="box"></i>Готово</span></td></tr>'
        for a, w in g["actions"])
    principles = "".join(f'<div><b>0{i}</b><h3>{t.upper()}</h3><p>{e(x)}</p></div>' for i, (t, x) in enumerate(PRINCIPLES, 1))
    path = "".join(f'<span class="{"on" if i == g["pathway_step"] else ""}">{p.upper()}</span>' for i, p in enumerate(PATHWAY))
    hero_title, hero_rest = g["hero"].split(". ", 1)
    st = g["stage"]
    body = f"""
<section class="page">
  <div class="cover">
    {top(grade, g, dark=True)}
    <div class="kicker">CAREER & UNIVERSITY ROADMAP · {g["stage_ru"].upper()}</div>
    <h1>{headline}</h1>
    <p class="lead">{e(g["lead"])}</p>
    <div class="fields"><div class="field">УЧЕНИК<br><span class="val">{e(d["name"])}, {grade} класс</span></div>
      <div class="field">ДАТА ДИАГНОСТИКИ<br><span class="val">{e(d["date"])}</span></div></div>
  </div>
  <div class="hero"><p><b>{e(hero_title)}.</b>{e(hero_rest)}</p></div>
  <h2><span class="n">01</span>Что показала диагностика</h2>
  <p class="note">Результаты помогают увидеть актуальные интересы, сильные стороны и возможные направления развития.
  Они не определяют профессию и не являются прогнозом гарантированного поступления.</p>
  <table><tr><th>МОЙ ПРОФИЛЬ ИНТЕРЕСОВ</th><th class="score">РЕЗУЛЬТАТ</th></tr>{profile_rows}</table>
  <div class="comment"><b>КОММЕНТАРИЙ ПРОФОРИЕНТАТОРА BHS</b>{e(d["comment"] or g["comment"])}</div>
  {foot(1, grade, st)}
</section>
<section class="page">
  {top(grade, g)}
  <h2><span class="n">02</span>Мой Career Profile</h2>
  <p class="note">{e(g["profile_note"])}</p>
  <div class="card"><span class="label">ПОДХОДЯЩИЕ НАПРАВЛЕНИЯ И ПРОФЕССИИ</span>{clusters}</div>
  <div class="card"><span class="label">СИЛЬНЫЕ СТОРОНЫ</span><ol class="filled">{strengths}</ol></div>
  <div class="card"><span class="label">{e(g["second"]).upper()}</span><ol class="filled">{steps}</ol></div>
  <h2><span class="n">03</span>Моя главная задача на этот год</h2>
  <div class="task"><h3>{e(g["task_title"])}</h3><p>{e(g["task"])}</p></div>
  {foot(2, grade, st)}
</section>
<section class="page">
  {top(grade, g)}
  <h2><span class="n">04</span>Action Plan</h2>
  <p class="note">Отмечайте статус по мере движения и сверяйтесь с профориентатором BHS раз в четверть.</p>
  <table class="plan"><tr><th></th><th>ДЕЙСТВИЕ</th><th>СРОК</th><th class="status">МОЙ СТАТУС</th></tr>{actions}</table>
  <div class="result"><h3>Мой главный результат к концу учебного года</h3><p>{e(g["result"])}</p></div>
  {foot(3, grade, st)}
</section>
<section class="page">
  {top(grade, g)}
  <h2><span class="n">05</span>Рекомендации родителям</h2>
  <p class="quote">{e(g["parents"])}</p>
  <span class="label">ТРИ ПРИНЦИПА BHS</span>
  <div class="principles">{principles}</div>
  <h2><span class="n">06</span>BHS Pathway</h2>
  <div class="path">{path}</div>
  <div class="next"><b>{e(g["next"][0])}</b><span>{e(g["next"][1])}</span></div>
  <div class="all-in"><b>ВСЯ ПРОГРАММА — В BHS</b>Подготовка к SAT и IELTS, работа над эссе, рекомендательные письма,
  проекты, конкурсы и список университетов — весь Career & University Roadmap ученик проходит внутри
  Beta High School, вместе с профориентатором и учителями. Отдельные курсы искать не нужно.</div>
  <div class="comment"><b>ФИНАЛЬНЫЙ КОММЕНТАРИЙ ПРОФОРИЕНТАТОРА</b>Ваш следующий шаг — обсудить результаты диагностики
  с профориентатором BHS и определить 3–5 конкретных действий на ближайшие 90 дней. Именно последовательные
  маленькие шаги со временем формируют сильную образовательную траекторию.</div>
  <p class="disclaimer">Важно: диагностика отражает актуальные интересы и особенности профиля ученика. Она не является
  медицинским или психологическим заключением и не гарантирует поступление в конкретный университет.
  Итоговые решения принимаются учеником и семьёй совместно со специалистами.</p>
  {foot(4, grade, st)}
</section>"""
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{e(d["name"])} — BHS Roadmap</title>'
            f"<style>{_css(FONTS.as_uri())}</style></head><body>{body}</body></html>")


def make_roadmap(folder: Path, model: dict) -> Path | None:
    """Дорожная карта в папку сессии. None — класс без шаблона или нет браузера."""
    if model["student"].get("grade") not in GRADES:
        return None
    with _printing:
        return _print(Path(folder), model)


def _print(folder: Path, model: dict) -> Path | None:
    html = folder / ROADMAP_HTML
    html.write_text(render_roadmap_html(model), encoding="utf-8")
    browser = _browser()
    if browser is None:
        log.warning("дорожная карта: нет Chrome или Edge, PDF не собран, есть %s", html.name)
        return None
    pdf = folder / ROADMAP_PDF
    tmp = folder / ".дорожная-карта.tmp.pdf"
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run",
                    "--use-mock-keychain", "--password-store=basic", "--disable-extensions",
                    "--allow-file-access-from-files", f"--user-data-dir={folder / '.browser'}",
                    f"--print-to-pdf={tmp}", html.as_uri()],
                   check=True, capture_output=True, timeout=90,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    shutil.rmtree(folder / ".browser", ignore_errors=True)
    os.replace(tmp, pdf)
    return pdf
