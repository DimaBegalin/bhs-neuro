"""Дашборд замера: мониторинг мозга и профориентация.

Правила страницы: ни одного термина без перевода, все числа в шкале 0-100
от покоя самого ребёнка, у каждого блока подпись «как читать». Профориентация
опирается на измеренное и объясняет каждое «почему» конкретными числами.
"""
import json
import sys

from analyzer.career_map import build_career
from analyzer.insights import build_insights
from analyzer.human_scale import DOMAIN_HUMAN, METRICS, RHYTHMS, tempo_words, to_scale
from report.blocks import donut_ring
from report.viz import (DOMAIN_COLORS, effort_map, hbar, order_bars,
                        score_ring, session_tracks)
from bridge.storage import atomic_write_text

BAND_KEYS = ["delta", "theta", "alpha", "beta", "gamma"]
BAND_COLORS = {"delta": "#3E4585", "theta": "#535BA4", "alpha": "#22B57C",
               "beta": "#F16B14", "gamma": "#F4C15A"}
DOMAINS = ("numeric", "spatial", "verbal", "working_memory")


def sect(title, what, how, body, note=""):
    return ('<section class="card"><div class="card-head"><h3>%s</h3>'
            '<p class="what">%s</p><p class="how">Как читать: %s</p></div>%s%s</section>'
            % (title, what, how, body,
               '<p class="note">%s</p>' % note if note else ""))


def hero_tile(title, what, score, color, verdict_text, label=None):
    return ('<div class="tile"><div class="tile-ring">%s</div>'
            '<div class="tile-name">%s</div><div class="tile-what">%s</div>'
            '<div class="tile-verdict" style="color:%s">%s</div></div>'
            % (score_ring(score, color, label=label), title, what, color, verdict_text))


def build(report, out_path, child=""):
    profile = report["profile"]
    blocks = report["blocks"]
    rest = report["rest"]["state"]
    tl = report["timeline"]
    cards = sorted(profile["domains"],
                   key=lambda c: -(c["efficiency"] if c["efficiency"] is not None else -99))

    scores = {d: {m: to_scale(blocks[d]["state"][m], rest[m]) for m in METRICS}
              for d in DOMAINS}
    career = build_career(cards, scores, DOMAIN_HUMAN)
    neuro = build_insights(cards, scores, tl, report.get("iaf"),
                           report.get("pulse"), DOMAIN_HUMAN)
    tempo_word, tempo_hint = tempo_words(report["iaf"])

    means = tl["means"]
    hold, flow = tl["hold_pct"], tl["flow_pct"]
    fatigue = tl.get("fatigue") or {"score": 50, "verdict": "данных мало", "delta_pct": 0}

    def words(score, high, low, mid="в обычных пределах"):
        return high if score >= 63 else (low if score <= 37 else mid)

    hero = "".join([
        hero_tile("Концентрация", "сила включённости в задачу", means["engage"],
                  "#F16B14", words(means["engage"], "работал собранно",
                                   "включался слабо")),
        hero_tile("Удержание внимания", "доля времени выше покоя", hold, "#5B8DEF",
                  words(hold, "держал внимание почти всё время",
                        "внимание часто уплывало", "держал с провалами"),
                  label="%d%%" % hold),
        hero_tile("Напряжение", "цена, которой давались задачи", means["stress"],
                  "#F0666B", words(means["stress"], "работал на пределе",
                                   "давления почти не было")),
        hero_tile("Спокойствие", "работа без внутренней тревоги", means["calm"],
                  "#22B57C", words(means["calm"], "работал спокойно",
                                   "спокойствие уходило")),
        hero_tile("Поток", "включён и без перегрузки", flow, "#F4C15A",
                  words(flow, "часто входил в поток", "в поток почти не входил",
                        "поток случался"), label="%d%%" % flow),
        hero_tile("Усталость", "рост усилия к концу теста", fatigue["score"],
                  "#96A0B5", fatigue["verdict"],
                  label="%+d%%" % fatigue["delta_pct"]),
    ])

    _ = None  # легенда старой дорожки удалена вместе с ней
    pulse = report.get("pulse")
    pulse_row = ""
    if pulse and pulse.get("ok"):
        points = pulse.get("series", [])
        spark = ""
        if len(points) > 2:
            values = [pt["bpm"] for pt in points]
            low, high = min(values), max(values)
            span = (high - low) or 1
            step = 560 / (len(values) - 1)
            coords = " ".join("%.1f,%.1f" % (i * step, 46 - (v - low) / span * 36 - 5)
                              for i, v in enumerate(values))
            spark = ('<svg viewBox="0 0 560 46" class="pulse-spark">'
                     '<polyline points="%s" fill="none" stroke="#F0666B" '
                     'stroke-width="2.5" stroke-linejoin="round"/></svg>' % coords)
        pulse_row = ('<div class="pulse-row"><div class="pulse-num">'
                     '<b>%d</b><span>уд/мин<br>медиана</span></div>%s'
                     '<div class="pulse-range">от %d до %d<br>'
                     '<span>оптический датчик прибора</span></div></div>'
                     % (pulse["bpm_median"], spark,
                        pulse["bpm_min"], pulse["bpm_max"]))

    chart = session_tracks(tl, DOMAIN_HUMAN, pulse=report.get("pulse"))

    work = tl["workability"]
    if len(work) >= 2:
        delta_work = work[-1]["score"] - work[0]["score"]
        if delta_work >= 8:
            work_verdict = "разгоняется по ходу: первые задания идут дороже, дальше легче"
            work_advice = ("Занятия начинать с короткой разминки на пять минут: "
                           "мозгу нужен разбег, и это нормально.")
        elif delta_work <= -8:
            work_verdict = "к концу теста выдыхается"
            work_advice = ("Длинные подходы дробить: самое важное ставить в начало "
                           "занятия, после сорока минут делать настоящий перерыв.")
        else:
            work_verdict = "держит темп ровно всю сессию"
            work_advice = ("Выдерживает полный урок без провалов: объём нагрузки "
                           "можно наращивать смело.")
    else:
        work_verdict, work_advice = "блоков мало для вывода", ""
    work_bars = "".join(
        hbar("%d-й · %s" % (w["order"], DOMAIN_HUMAN.get(w["domain"], ("", ""))[0]),
             w["score"], DOMAIN_COLORS.get(w["domain"], "#888"),
             right_text="%d из 100" % w["score"])
        for w in work)

    recovery = tl["recovery"]
    if recovery["ratio"] is None:
        rec_big, rec_advice = "мало пауз", ""
    else:
        rec_big = "×%.2f" % recovery["ratio"]
        if recovery["ratio"] >= 1.15:
            rec_advice = ("Короткого перерыва хватает, чтобы вернуться в ресурс: "
                          "обычный режим занятий подходит.")
        elif recovery["ratio"] >= 1.0:
            rec_advice = ("Перерыв стоит удлинить: пять минут вместо двух, и без "
                          "телефона. Помогают два спокойных вдоха-выдоха перед "
                          "возвращением к задаче.")
        else:
            rec_advice = ("Короткая пауза не успевает снять напряжение. Между "
                          "занятиями нужен настоящий отдых десять минут и простая "
                          "практика расслабления: дыхание, вода, окно.")

    if tl.get("peak"):
        peak_big = "%d:%02d" % (int(tl["peak"]["t"] // 60), int(tl["peak"]["t"] % 60))
        peak_domain = DOMAIN_HUMAN.get(tl["peak"]["domain"], ("", ""))[0]
        peak_line = "блок «%s», напряжение %d из 100" % (peak_domain, tl["peak"]["score"])
        peak_advice = ("Именно этот тип задач дозировать первым: короткие подходы, "
                       "разбор ошибки сразу, похвала за ход решения, а не только "
                       "за ответ.")
    else:
        peak_big, peak_line, peak_advice = "нет", "", ""

    def pattern_block(title, what, body, verdict, advice):
        advice_html = ('<div class="pat-advice"><b>Что с этим делать.</b> %s</div>'
                       % advice) if advice else ""
        verdict_html = ('<div class="pat-verdict">%s</div>' % verdict) if verdict else ""
        return ('<div class="pat"><div class="pat-title">%s</div>'
                '<div class="pat-what">%s</div>%s%s%s</div>'
                % (title, what, body, verdict_html, advice_html))

    reaction = tl.get("error_reaction")
    if reaction:
        if reaction["delta"] >= 8:
            reaction_verdict = "ошибка выбивает: после неверного ответа напряжение подскакивает"
            reaction_advice = ("Учить проходить ошибку: короткая пауза, вдох, дальше. "
                               "На занятиях хвалить за ход решения, а не только за "
                               "ответ, иначе страх ошибки съест экзамен.")
        elif reaction["delta"] <= 2:
            reaction_verdict = "ошибку проходит спокойно, ровно идёт дальше"
            reaction_advice = ("Отношение к неудаче здоровое: можно смело давать "
                               "задачи на вырост, без страха сломать мотивацию.")
        else:
            reaction_verdict = "ошибка слегка цепляет, но из колеи выбивает редко"
            reaction_advice = ("Достаточно проговаривать после занятий одну мысль: "
                               "ошибка это часть решения, а не приговор.")
        reaction_body = ('<div class="pat-big">%+d</div>'
                         '<div class="pat-verdict">напряжение после ошибки %d, '
                         'после верного ответа %d, ошибок в замере %d</div>'
                         % (round(reaction["delta"]), reaction["after_error"],
                            reaction["after_ok"], reaction["errors"]))
        reaction_pattern = pattern_block(
            "Реакция на ошибку",
            "Сравниваем напряжение в четыре секунды после неверного ответа и "
            "после верного. Разница показывает, как ребёнок переживает неудачу.",
            reaction_body, reaction_verdict, reaction_advice)
    else:
        reaction_pattern = pattern_block(
            "Реакция на ошибку",
            "Сравниваем напряжение после неверного и верного ответа.",
            '<div class="pat-big">мало ошибок</div>',
            "ошибок было слишком мало для честного вывода, и это само по себе "
            "хороший знак", "")

    warmup = tl.get("warmup")
    if warmup:
        if warmup["mean_s"] <= 6:
            warm_verdict = "включается почти мгновенно"
            warm_advice = ("Разбег не нужен: можно начинать занятие сразу с "
                           "главного, пока внимание свежее.")
        elif warmup["mean_s"] <= 15:
            warm_verdict = "нужен короткий разбег"
            warm_advice = ("Первые минуты занятия отдавать простым заданиям: "
                           "они выводят мозг на рабочий ход без перегрузки.")
        else:
            warm_verdict = "разгоняется долго"
            warm_advice = ("Начинать с пятиминутной разминки из лёгких примеров "
                           "и не судить по первым заданиям: настоящий уровень "
                           "виден после разгона.")
        warm_body = ('<div class="pat-big">%.0f с</div>'
                     '<div class="pat-verdict">по блокам: %s</div>'
                     % (warmup["mean_s"],
                        ", ".join("%.0f с" % w for w in warmup["per_block"])))
        warmup_pattern = pattern_block(
            "Скорость включения",
            "Сколько секунд после начала нового типа задач мозгу нужно, чтобы "
            "выйти на рабочую включённость.",
            warm_body, warm_verdict, warm_advice)
    else:
        warmup_pattern = ""

    patterns = "".join([
        reaction_pattern,
        warmup_pattern,
        pattern_block("Работоспособность по ходу теста",
                      "Сила включённости в каждом блоке по порядку прохождения, "
                      "по шкале от 0 до 100, где 50 это покой.",
                      work_bars, work_verdict, work_advice),
        pattern_block("Восстановление в паузах",
                      "Насколько спокойствие в коротких паузах поднималось по "
                      "сравнению с работой. Единица значит без изменений, выше "
                      "единицы значит пауза работает.",
                      '<div class="pat-big">%s</div>' % rec_big,
                      recovery["verdict"], rec_advice),
        pattern_block("Самый напряжённый момент",
                      "Точка сессии, где мозг работал дороже всего.",
                      '<div class="pat-big" style="color:#F0666B">%s</div>' % peak_big,
                      peak_line, peak_advice),
    ])

    rhythm_rows = []
    for key in BAND_KEYS:
        name, explain = RHYTHMS[key]
        share = sum(blocks[d]["bands"][key] for d in DOMAINS) / len(DOMAINS)
        rhythm_rows.append(
            '<div class="rhythm"><div class="rhythm-top">'
            '<span class="rhythm-chip" style="background:%s"></span><b>%s</b>'
            '<span class="rhythm-pct">%.0f%%</span></div>'
            '<div class="hb-track"><i class="hb-fill" data-w="%d" '
            'style="background:%s"></i></div>'
            '<div class="rhythm-what">%s</div></div>'
            % (BAND_COLORS[key], name, share, min(int(share * 1.6), 100),
               BAND_COLORS[key], explain))
    rhythm_donut = donut_ring(
        [(RHYTHMS[k][0], sum(blocks[d]["bands"][k] for d in DOMAINS) / len(DOMAINS),
          BAND_COLORS[k]) for k in BAND_KEYS],
        tempo_word, "темп мозга")

    task_cards = []
    for card in cards:
        d = card["domain"]
        name, what = DOMAIN_HUMAN[d]
        level = ("сильная сторона" if card["efficiency"] and card["efficiency"] > 0.7
                 else "далось тяжело" if card["efficiency"] and card["efficiency"] < -0.7
                 else "обычный уровень")
        chip = ("strong" if level == "сильная сторона"
                else "costly" if level == "далось тяжело" else "")
        rows = "".join(hbar(METRICS[m]["title"], scores[d][m], DOMAIN_COLORS[d])
                       for m in ("focus", "stress", "load"))
        task_cards.append(
            '<div class="task"><div class="task-head">'
            '<span class="dot" style="background:%s"></span>'
            '<div><div class="task-name">%s</div><div class="task-what">%s</div></div>'
            '<span class="chip %s">%s</span></div>'
            '<div class="task-nums"><div><b>%.0f%%</b><span>решено верно</span></div>'
            '<div><b>%.1f с</b><span>средний ответ</span></div></div>%s</div>'
            % (DOMAIN_COLORS[d], name, what, chip, level, card["accuracy"] * 100,
               report["reaction_s"][d], rows))

    # профориентация
    arch = career["archetype"]
    from_names = " + ".join(DOMAIN_HUMAN[d][0].lower() for d in arch["from"])
    arch_hero = ('<div class="arch"><div class="arch-cap">рабочий профиль по замеру</div>'
                 '<div class="arch-name">%s</div><div class="arch-tag">%s</div>'
                 '<div class="arch-from">собран из двух самых ресурсных направлений: %s</div>'
                 '</div>' % (arch["name"], arch["tagline"], from_names))

    fit_cards = []
    for f in career["fits"]:
        profs = "".join('<span class="prof">%s</span>' % p for p in f["profs"])
        fit_cards.append(
            '<div class="fit"><div class="fit-head"><div>'
            '<div class="fit-cluster">%s</div><div class="fit-domain">%s</div></div>'
            '<div class="fit-ring">%s</div></div>'
            '<div class="hb-track"><i class="hb-fill" data-w="%d" '
            'style="background:%s"></i></div>'
            '<p class="fit-why">%s</p><div class="profs">%s</div></div>'
            % (f["cluster"], DOMAIN_HUMAN[f["domain"]][0],
               score_ring(f["fit"], DOMAIN_COLORS[f["domain"]], size=86, stroke=8),
               f["fit"], DOMAIN_COLORS[f["domain"]], f["why"], profs))

    reserve = 50
    if fatigue and isinstance(fatigue.get("delta_pct"), (int, float)):
        reserve = int(max(0, min(100, 100 - max(fatigue["delta_pct"], 0))))
    finals = [
        ("Вовлечённость", means["engage"], "насколько мозг был включён в работу",
         "#F16B14"),
        ("Когнитивная нагрузка", means["load"], "сколько ресурса тратил на задачи",
         "#5B8DEF"),
        ("Релаксация", means["calm"], "доля спокойствия внутри работы", "#22B57C"),
        ("Запас сил", reserve, "сколько выносливости осталось к концу", "#F4C15A"),
    ]
    if report.get("sync_pct"):
        finals.append(("Синхронность", report["sync_pct"],
                       "насколько слаженно работали полушария", "#C77DF0"))
    final_tiles = "".join(
        '<div class="fin"><div class="fin-num" style="color:%s">%d<small>%%</small></div>'
        '<div class="fin-name">%s</div><div class="fin-what">%s</div></div>'
        % (color, value, name, what) for name, value, what, color in finals)

    pane1 = "".join([
        sect("Итог замера в пяти числах",
             "Главные индексы, усреднённые за всё тестирование.",
             "шкала от 0 до 100. Для первых трёх 50 это уровень личного покоя: "
             "выше значит больше обычного. Запас сил и синхронность читаются "
             "напрямую: чем выше, тем лучше.",
             '<div class="finals">%s</div>' % final_tiles),
        sect("Состояние за сессию",
             "Шесть состояний, посчитанных с датчиков за время теста.",
             "шкала от 0 до 100, где 50 это спокойное состояние самого ребёнка. "
             "Выше 63 заметно больше обычного, ниже 37 заметно меньше.",
             '<div class="hero">%s</div>%s' % (hero, pulse_row),
             "Сравниваем ребёнка только с ним самим: чужой нормы по прибору нет, "
             "и придумывать её нечестно."),
        sect("Как шла сессия, минута за минутой",
             "Сверху шкала этапов теста. Под ней три ленты, у каждой один "
             "вопрос и один цвет.",
             "у всех лент общее время, пунктир поперёк это уровень покоя. "
             "Линия выше пунктира значит больше обычного, ниже значит меньше. "
             "Смотрите, что делает красная лента над цветным этапом: это и "
             "есть цена каждого типа задач.",
             chart,
             "Крестики на красной ленте это ошибки: если крестик совпал с "
             "горбом линии, ошибка пришла вместе с перегрузкой."),
        sect("Поведенческие паттерны",
             "Как ребёнок распределяет силы: разгон, выносливость, восстановление.",
             "три наблюдения из динамики всей сессии.",
             '<div class="pats">%s</div>' % patterns),
        sect("Из чего складывалась работа мозга",
             "Мозг работает на нескольких волнах сразу. Здесь их доли за сессию.",
             "чем длиннее полоса, тем больше этого состояния было. В центре "
             "кольца темп мозга: скорость обработки информации.",
             '<div class="cols"><div>%s</div><div>%s</div></div>'
             % ("".join(rhythm_rows), rhythm_donut),
             "Темп: %s. %s" % (tempo_word, tempo_hint)),
        sect("Каждый тип задач отдельно",
             "Четыре блока проверяли четыре разных способа мышления.",
             "процент это верные ответы, полосы это состояние в блоке, "
             "белая чёрточка посередине это уровень покоя.",
             "".join(task_cards)),
    ])

    insight_cards = "".join(
        '<div class="ins" style="border-color:%s33">'
        '<div class="ins-word" style="color:%s">%s</div>'
        '<div class="ins-title">%s</div>'
        '<div class="ins-fact">%s</div>'
        '<div class="ins-study">%s</div></div>'
        % (i["color"], i["color"], i["word"], i["title"], i["fact"], i["study"])
        for i in neuro["insights"])

    steps_traj = "".join(
        '<div class="traj-step"><div class="traj-when">%s</div>'
        '<div class="traj-what">%s</div></div>' % (when, what)
        for when, what in neuro["trajectory"])

    pane_insights = "".join([
        sect("Карта когнитивной эффективности",
             "Главный график замера: результат против энергозатрат. Каждая "
             "точка это тип задач.",
             "чем правее точка, тем выше точность; чем ниже, тем дешевле она "
             "далась мозгу. Сильные стороны живут в правом нижнем углу.",
             effort_map(profile["domains"],
                        {d: DOMAIN_HUMAN[d][0] for d in DOMAINS})),
        sect("Нейроинсайты",
             "Короткие выводы из замера. Каждый держится на измеренном числе.",
             "слово крупно, под ним факт из данных и что это значит для учёбы.",
             '<div class="ins-grid">%s</div>' % insight_cards),
        sect("Вывод специалиста",
             "Черновик заключения, собранный алгоритмом по данным.",
             "специалист зачитывает и уточняет на разборе, это его опора.",
             '<p class="para">%s</p>' % neuro["specialist"]),
        sect("Траектория ребёнка",
             "Три шага от кружка до профессии, выстроенные от сильного "
             "направления «%s»." % neuro["trajectory_title"],
             "это план-подсказка для семьи, а не приговор: траекторию "
             "уточняет специалист вместе с родителем.",
             '<div class="traj">%s</div>' % steps_traj),
    ])

    pane2 = "".join([
        sect("Профиль ребёнка",
             "Короткое имя тому, что показал замер.",
             "это рабочее название для разговора, его дал алгоритм по двум "
             "самым ресурсным направлениям.",
             arch_hero),
        sect("Куда мозгу дорога дешевле",
             "Четыре направления, отсортированные по индексу опоры: насколько "
             "профессии этого куста лягут на сильные стороны.",
             "индекс собран из точности (45%), низкого напряжения (30%) и "
             "концентрации (25%) в задачах этого типа. Это подсказка для "
             "разговора, выбирает всегда семья.",
             '<div class="fits">%s</div>' % "".join(fit_cards)),
        sect("Где будет дороже",
             "Честная часть профориентации: не запрет, а цена.",
             "прочитайте вслух на разборе, это снимает страх «у ребёнка не получится».",
             '<p class="para">%s</p>' % career["caution"]),
        sect("Что делать дальше",
             "Три шага для семьи.",
             "начните с первого, он самый простой.",
             '<div class="step"><b>Нагружать сильное</b>Секции, олимпиады и кружки '
             'из верхнего направления: там результат приходит без перегрузки, '
             'и планку можно поднимать смело.</div>'
             '<div class="step"><b>Менять способ в дорогом</b>Короткие отрезки по '
             '15 минут, разбор ошибки сразу, больше наглядных опор. Дорогой канал '
             'тянется, когда его не давят объёмом.</div>'
             '<div class="step"><b>Повторить замер через полгода</b>Станет видно, '
             'что сдвинулось от занятий, а что осталось устойчивой чертой.</div>'),
        sect("Для специалиста",
             "Технические данные замера.",
             "родителю читать необязательно.",
             '<details class="tech"><summary>Показать технические данные</summary>'
             '<p style="margin-top:12px">Частота альфа-пика: %s Гц, выраженность %.2f. '
             'Каналы: %s, 250 Гц. Полосы индивидуальные по Климешу, вовлечённость '
             'по Pope (1995). Напряжение: отношение быстрых ритмов к альфа. '
             'Качество сигнала по блокам: %s. Пульс прибор умеет снимать оптическим '
             'датчиком, этот канал ещё не расшифрован: появится в следующей версии, '
             'выдумывать его вместо данных мы не стали.</p></details>'
             % (report["iaf"] or "не выделен", report["iaf_prominence"],
                ", ".join(report["channels"]),
                ", ".join("%s %.0f%%" % (DOMAIN_HUMAN[d][0], blocks[d]["quality"])
                          for d in DOMAINS))),
    ])

    html = TEMPLATE.replace("__WHO__", child or ("сессия " + report["session_id"]))
    html = html.replace("__PANE1__", pane1).replace("__PANEINS__", pane_insights)
    html = html.replace("__PANE2__", pane2)
    atomic_write_text(out_path, html)
    return out_path


TEMPLATE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Нейропрофориентация · Beta High School</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
@font-face{font-family:'Halvar';src:url('../fonts/HalvarBreit-Bd.woff2') format('woff2');font-weight:700}
@font-face{font-family:'Halvar';src:url('../fonts/HalvarBreit-Md.woff2') format('woff2');font-weight:500}
:root{--orange:#F16B14;--blue:#5B8DEF;--green:#22B57C;--amber:#F4C15A;--alert:#F0666B;
--bg:#090D15;--card:#111726;--card2:#182031;--line:rgba(255,255,255,.08);
--text:#F6F8FB;--muted:#94A0B8;
--display:'Halvar','Archivo',sans-serif;--body:'Inter',-apple-system,sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:var(--body);font-size:16px;
line-height:1.6;padding-bottom:80px}
body::before{content:'';position:fixed;inset:0;pointer-events:none;
background:radial-gradient(600px 320px at 12% -4%,rgba(241,107,20,.14),transparent 60%),
radial-gradient(640px 340px at 88% -6%,rgba(91,141,239,.10),transparent 60%)}
.wrap{max-width:1120px;margin:0 auto;padding:34px 20px 0;position:relative}
h1{font-family:var(--display);font-size:34px;font-weight:700;letter-spacing:-.5px;line-height:1.15}
.sub{color:var(--muted);font-size:16px;margin-top:8px}
.tabs{position:sticky;top:0;z-index:20;display:flex;gap:6px;background:rgba(9,13,21,.82);
backdrop-filter:blur(14px);padding:14px 0;margin:22px 0 20px}
.tabs button{border:1px solid var(--line);background:var(--card);color:var(--muted);
font-family:var(--body);font-size:16px;font-weight:500;padding:12px 26px;
border-radius:999px;cursor:pointer;transition:all .2s ease}
.tabs button.on{background:var(--orange);border-color:var(--orange);color:#fff}
.pane{display:none}.pane.on{display:block}
.pdf-btn{border:1px solid var(--line);background:var(--card);color:var(--text);
font-family:var(--body);font-size:15px;font-weight:500;padding:12px 22px;
border-radius:999px;cursor:pointer;margin-left:auto}
.pdf-btn:hover{border-color:var(--orange);color:var(--orange)}
/* Печать. Три вещи обязательны, иначе документ уходит семье испорченным:
   виден весь отчёт, а не открытая вкладка; фон сохраняется, иначе светлый
   текст ложится на белое и читать нечего; карточки не рвутся по страницам */
@media print{
  @page{size:A4;margin:12mm}
  html,body{background:#090D15 !important;
    -webkit-print-color-adjust:exact;print-color-adjust:exact}
  body{padding-bottom:0}
  body::before{display:none}
  .tabs,.pdf-btn{display:none !important}
  .pane{display:block !important;break-before:page}
  .pane:first-of-type{break-before:auto}
  .wrap{max-width:none;padding:0}
  .card,.tile,.hb,.donut{break-inside:avoid}
  h1{font-size:28px}
}
.card{background:var(--card);border:1px solid var(--line);border-radius:24px;
padding:26px 28px;margin-bottom:18px}
.card-head{margin-bottom:20px}
.card-head h3{font-family:var(--display);font-size:22px;font-weight:500;margin-bottom:8px}
.what{font-size:16px;color:#C9D1E0;line-height:1.55}
.how{font-size:15px;color:var(--muted);margin-top:6px;line-height:1.55}
.note{font-size:14px;color:var(--muted);margin-top:16px;padding-top:14px;
border-top:1px solid var(--line);line-height:1.6}
.finals{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}
.fin{background:var(--card2);border-radius:18px;padding:18px 16px;text-align:center}
.fin-num{font-family:var(--display);font-size:40px;font-weight:700;line-height:1}
.fin-num small{font-size:17px;font-weight:500}
.fin-name{font-size:15.5px;font-weight:600;margin-top:8px}
.fin-what{font-size:12.5px;color:var(--muted);margin-top:4px;line-height:1.45}
@media(max-width:900px){.finals{grid-template-columns:repeat(2,1fr)}}
.hero{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.tile{background:var(--card2);border-radius:20px;padding:20px 16px;text-align:center}
.ring{width:112px;height:112px}
.ring-num{fill:var(--text);font-size:26px;font-weight:600;font-family:var(--body)}
.tile-name{font-size:18px;font-weight:600;margin-top:10px}
.tile-what{font-size:13.5px;color:var(--muted);margin-top:4px;line-height:1.45}
.tile-verdict{font-size:15px;margin-top:9px;font-weight:500}
.pulse-row{display:flex;align-items:center;gap:22px;margin-top:14px;
background:var(--card2);border-radius:20px;padding:16px 20px}
.pulse-num b{font-family:var(--display);font-size:38px;font-weight:700;color:#F0666B}
.pulse-num span{display:block;font-size:12px;color:var(--muted);line-height:1.3}
.pulse-spark{flex:1;height:46px;min-width:120px}
.pulse-range{font-size:15px;text-align:right;line-height:1.5}
.pulse-range span{font-size:12px;color:var(--muted)}
.tracks-head{width:100%;height:34px;display:block}
.seg-label{font-size:12px;font-weight:600;fill:#fff}
.seg-label.mut{fill:#B9C2D4;font-weight:400}
.lane-row{margin-top:14px}
.lane-head{display:flex;align-items:baseline;gap:10px;margin-bottom:4px}
.lane-head b{font-size:15.5px;font-weight:600}
.lane-head span{font-size:13px;color:var(--muted)}
.track-lane{width:100%;height:92px;display:block;background:rgba(255,255,255,.025);
border-radius:12px}
.tracks-axis{position:relative;height:20px;margin-top:6px}
.tracks-axis span{position:absolute;font-size:11px;color:var(--muted);
transform:translateX(-50%)}
.phase-label{font-size:12px;font-weight:600}
.axis-label{font-size:11px;fill:var(--muted)}
.peak-label{font-size:12px;fill:#FFB4B7;font-weight:600}
.chart-legend{display:flex;gap:20px;flex-wrap:wrap;margin-top:12px;font-size:14px;
color:var(--muted)}
.chart-legend i{display:inline-block;width:16px;height:3px;border-radius:2px;
vertical-align:middle;margin-right:7px}
.chart-legend b{color:var(--alert);font-weight:700;margin-right:5px}
.lg-mut b{color:var(--muted)}
.pats{display:flex;flex-direction:column;gap:14px}
.pat{background:var(--card2);border-radius:20px;padding:22px 24px}
.pat-title{font-size:18px;font-weight:600;margin-bottom:6px}
.pat-what{font-size:14.5px;color:var(--muted);line-height:1.55;margin-bottom:16px}
.pat-big{font-family:var(--display);font-size:40px;font-weight:700}
.pat-verdict{font-size:16px;color:#E4E9F2;margin-top:8px;font-weight:500}
.pat-advice{font-size:15px;color:#C9D1E0;line-height:1.6;margin-top:12px;
padding-top:12px;border-top:1px solid var(--line)}
.pat-advice b{color:var(--text)}
.hb{display:flex;align-items:center;gap:12px;margin-bottom:10px}
.hb-name{font-size:14px;color:var(--muted);width:158px;flex:none;line-height:1.3}
.hb-track{flex:1;height:10px;background:rgba(255,255,255,.07);border-radius:6px;
position:relative;overflow:hidden}
.hb-fill{display:block;height:10px;border-radius:6px;width:0;
transition:width .9s cubic-bezier(.16,1,.3,1)}
.hb-mid{position:absolute;left:50%;top:-2px;width:2px;height:14px;
background:rgba(255,255,255,.35);z-index:2}
.hb-val{font-size:14px;font-weight:600;width:70px;text-align:right;white-space:nowrap}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:26px}
.rhythm{margin-bottom:16px}
.rhythm-top{display:flex;align-items:center;gap:9px;font-size:16px;margin-bottom:6px}
.rhythm-chip{width:11px;height:11px;border-radius:3px}
.rhythm-pct{margin-left:auto;color:var(--muted);font-size:15px}
.rhythm-what{font-size:13.5px;color:var(--muted);margin-top:5px;line-height:1.5}
.task{background:var(--card2);border-radius:20px;padding:20px 22px;margin-bottom:14px}
.task-head{display:flex;align-items:flex-start;gap:11px;margin-bottom:14px}
.dot{width:11px;height:11px;border-radius:50%;flex:none;margin-top:6px}
.task-name{font-size:18px;font-weight:600}
.task-what{font-size:14px;color:var(--muted);margin-top:2px}
.chip{margin-left:auto;font-size:14px;padding:6px 14px;border-radius:999px;
background:rgba(255,255,255,.07);color:var(--muted);white-space:nowrap}
.chip.strong{background:rgba(34,181,124,.2);color:#5BD8A4}
.chip.costly{background:rgba(240,102,107,.18);color:var(--alert)}
.task-nums{display:flex;gap:30px;margin-bottom:16px}
.task-nums b{font-size:26px;font-weight:600;display:block;font-family:var(--display)}
.task-nums span{font-size:14px;color:var(--muted)}
.em-wrap{position:relative}
.effort-map{width:100%;height:440px}
.zone-label{font-size:12.5px;font-weight:600}
.axis-title{font-size:12px;fill:#94A0B8;text-anchor:end}
.em-pt{cursor:pointer}
.em-pt circle{transition:opacity .2s ease, r .2s ease}
.em-wrap.dim .em-pt{opacity:.25}
.em-wrap.dim .em-pt.hot{opacity:1}
.em-tip{position:absolute;pointer-events:none;background:#0E1422;
border:1px solid rgba(255,255,255,.14);border-radius:14px;padding:12px 16px;
box-shadow:0 12px 32px rgba(0,0,0,.5);min-width:190px;z-index:5;
transform:translate(-50%,-112%);transition:opacity .15s ease}
.em-tip b{font-size:15.5px;display:block;margin-bottom:6px}
.em-tip div{font-size:13.5px;color:#C9D1E0;line-height:1.55}
.em-tip .tip-eff{font-weight:600}
.em-legend{display:flex;gap:18px;flex-wrap:wrap;margin-top:10px}
.em-leg{font-size:14px;color:#C9D1E0;display:inline-flex;align-items:center;gap:8px}
.em-leg i{width:11px;height:11px;border-radius:50%;display:inline-block}
.ins-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.ins{background:var(--card2);border:1px solid var(--line);border-radius:20px;
padding:20px 22px}
.ins-word{font-family:var(--display);font-size:24px;font-weight:700;letter-spacing:-.3px}
.ins-title{font-size:13px;color:var(--muted);text-transform:uppercase;
letter-spacing:.07em;margin-top:4px}
.ins-fact{font-size:14.5px;color:#C9D1E0;margin-top:10px;line-height:1.5}
.ins-study{font-size:14.5px;margin-top:8px;line-height:1.55;padding-top:10px;
border-top:1px solid var(--line)}
.traj{display:flex;flex-direction:column;gap:0}
.traj-step{display:flex;gap:18px;padding:16px 0;border-top:1px solid var(--line);
align-items:baseline}
.traj-step:first-child{border-top:0}
.traj-when{width:190px;flex:none;font-weight:600;font-size:15.5px;color:var(--orange)}
.traj-what{font-size:15.5px;line-height:1.6;color:#D5DBE6}
.arch{text-align:center;padding:26px 20px;background:
radial-gradient(420px 200px at 50% 0%,rgba(241,107,20,.16),transparent 70%);
border-radius:20px}
.arch-cap{font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em}
.arch-name{font-family:var(--display);font-size:44px;font-weight:700;margin-top:10px;
background:linear-gradient(90deg,#F16B14,#F4C15A);-webkit-background-clip:text;
background-clip:text;color:transparent}
.arch-tag{font-size:19px;color:#E4E9F2;margin-top:8px}
.arch-from{font-size:14.5px;color:var(--muted);margin-top:12px}
.fits{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.fit{background:var(--card2);border-radius:20px;padding:20px 22px}
.fit-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.fit-cluster{font-family:var(--display);font-size:19px;font-weight:500}
.fit-domain{font-size:14px;color:var(--muted);margin-top:3px}
.fit-ring .ring{width:84px;height:84px}
.fit-ring .ring-num{font-size:21px}
.fit-why{font-size:14.5px;color:#C9D1E0;line-height:1.55;margin:12px 0}
.profs{display:flex;flex-wrap:wrap;gap:7px}
.prof{font-size:13.5px;padding:7px 13px;border-radius:999px;
background:rgba(255,255,255,.06);border:1px solid var(--line);color:#DAE0EC}
.para{font-size:16.5px;line-height:1.65;color:#D5DBE6}
.step{border-top:1px solid var(--line);padding:17px 0;font-size:16px;line-height:1.6}
.step b{display:block;font-size:17px;margin-bottom:5px}
.tech{font-size:14px;color:var(--muted);line-height:1.7}
.tech summary{cursor:pointer;color:#C9D1E0;font-size:15px;padding:6px 0}
.donut{display:flex;align-items:center;gap:26px;flex-wrap:wrap}
.donut-figure{position:relative;width:150px;height:150px;flex:none}
.donut-svg{transform:rotate(-90deg);width:150px;height:150px}
.ring-arc{transition:opacity .22s ease}
.donut.dim .ring-arc{opacity:.2}.donut.dim .ring-arc.hot{opacity:1}
.donut-center{position:absolute;inset:0;display:flex;flex-direction:column;
align-items:center;justify-content:center;pointer-events:none}
.donut-title{font-family:var(--display);font-size:19px;font-weight:500}
.donut-caption{font-size:12.5px;color:var(--muted);margin-top:2px}
.donut-legend{display:flex;flex-direction:column;gap:3px}
.ring-row{display:flex;align-items:center;gap:11px;background:transparent;border:0;
padding:7px 9px;margin:0 -9px;border-radius:10px;font-family:var(--body);
transition:opacity .2s ease;cursor:default}
.donut.dim .ring-row{opacity:.35}
.donut.dim .ring-row.hot{opacity:1;background:rgba(255,255,255,.05)}
.ring-chip{width:10px;height:10px;border-radius:3px;flex:none}
.ring-name{font-size:14.5px;color:#C9D1E0;width:180px;text-align:left}
.ring-pct{font-size:14.5px;font-weight:600;color:var(--text)}
@media(max-width:900px){.hero{grid-template-columns:repeat(2,1fr)}
.pats,.cols,.fits{grid-template-columns:1fr}.ring-name{width:140px}}
@media(max-width:540px){.hero{grid-template-columns:1fr}}
</style></head><body><div class="wrap">

<h1>Как работает мозг ребёнка</h1>
<p class="sub">__WHO__ · замер 5 минут, четыре типа задач</p>

<div class="tabs">
  <button class="on" data-tab="0">Мониторинг мозга</button>
  <button data-tab="1">Нейроинсайты</button>
  <button data-tab="2">Профориентация</button>
  <button class="pdf-btn" id="pdf" data-tab="pdf">Скачать PDF</button>
</div>

<div class="pane on">__PANE1__</div>
<div class="pane">__PANEINS__</div>
<div class="pane">__PANE2__</div>

</div><script>
var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
function animate(){
  document.querySelectorAll('.ring-fill').forEach(function(c){
    var t = c.getAttribute('data-target');
    if (reduced) { c.setAttribute('stroke-dasharray', t); return; }
    c.style.transition = 'stroke-dasharray 1s cubic-bezier(.16,1,.3,1)';
    requestAnimationFrame(function(){ c.setAttribute('stroke-dasharray', t); });
  });
  document.querySelectorAll('.hb-fill').forEach(function(b){
    var w = b.getAttribute('data-w') + '%';
    if (reduced) { b.style.transition = 'none'; }
    requestAnimationFrame(function(){ b.style.width = w; });
  });
}
// кнопку PDF из переключателя вкладок исключаем: её data-tab не число,
// и общий обработчик спрятал бы разом все панели
document.querySelectorAll('.tabs button:not(.pdf-btn)').forEach(function(btn){
  btn.addEventListener('click', function(){
    var index = Number(btn.getAttribute('data-tab'));
    document.querySelectorAll('.pane').forEach(function(p,i){p.classList.toggle('on', i===index)});
    document.querySelectorAll('.tabs button:not(.pdf-btn)').forEach(function(b){b.classList.remove('on')});
    btn.classList.add('on');
    animate();
  });
});

/* Скачивание PDF. Основной путь: программа на ноутбуке печатает эту же
   страницу браузером и отдаёт готовый файл, поэтому документ выходит один
   в один с экраном. Если программы нет, отдаём страницу в печать браузера:
   печатные стили раскрывают все три вкладки и держат тёмный фон. */
var pdfButton = document.getElementById('pdf');
if (pdfButton) {
  pdfButton.addEventListener('click', function(){
    var name = (location.pathname.split('/').pop() || '').replace(/[.]html$/, '');
    var label = pdfButton.textContent;
    if (!name) { window.print(); return; }
    pdfButton.disabled = true;
    pdfButton.textContent = 'Готовлю PDF...';
    fetch('http://127.0.0.1:8765/report/' + encodeURIComponent(name) + '.pdf')
      .then(function(response){
        if (!response.ok) { throw new Error('нет'); }
        return response.blob();
      })
      .then(function(blob){
        var url = URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = url;
        link.download = name + '.pdf';
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(function(){ URL.revokeObjectURL(url); }, 10000);
      })
      .catch(function(){ window.print(); })
      .then(function(){
        pdfButton.disabled = false;
        pdfButton.textContent = label;
      });
  });
}
if (location.hash === '#career') { document.querySelectorAll('.tabs button')[2].click(); }
if (location.hash === '#insights') { document.querySelectorAll('.tabs button')[1].click(); }
document.querySelectorAll('.donut').forEach(function(donut){
  var arcs = donut.querySelectorAll('.ring-arc');
  var rows = donut.querySelectorAll('.ring-row');
  function highlight(index){
    donut.classList.toggle('dim', index !== null);
    arcs.forEach(function(a,i){ a.classList.toggle('hot', i === index) });
    rows.forEach(function(r,i){ r.classList.toggle('hot', i === index) });
  }
  arcs.forEach(function(a,i){
    a.addEventListener('mouseenter', function(){ highlight(i) });
    a.addEventListener('mouseleave', function(){ highlight(null) });
  });
  rows.forEach(function(r,i){
    r.addEventListener('mouseenter', function(){ highlight(i) });
    r.addEventListener('mouseleave', function(){ highlight(null) });
  });
});
document.querySelectorAll('.em-wrap').forEach(function(wrap){
  var tip = wrap.querySelector('.em-tip');
  var points = wrap.querySelectorAll('.em-pt');
  function show(point){
    var d = point.dataset;
    var eff = parseFloat(d.eff);
    var line = eff > 0.7 ? 'сильная сторона' :
      (eff < -0.7 ? 'далось тяжело' : 'обычный уровень');
    tip.innerHTML = '<b style="color:' + d.color + '">' + d.name + '</b>'
      + '<div>Результат: ' + d.acc + '% верных</div>'
      + '<div>Цена усилия: ' + d.cost + '</div>'
      + '<div class="tip-eff" style="color:' + d.color + '">' + line + '</div>';
    var circle = point.querySelectorAll('circle')[1];
    var box = wrap.getBoundingClientRect();
    var dot = circle.getBoundingClientRect();
    tip.style.left = (dot.left - box.left + dot.width / 2) + 'px';
    tip.style.top = (dot.top - box.top) + 'px';
    tip.hidden = false;
    wrap.classList.add('dim');
    points.forEach(function(p){ p.classList.toggle('hot', p === point); });
  }
  function hide(){
    tip.hidden = true;
    wrap.classList.remove('dim');
    points.forEach(function(p){ p.classList.remove('hot'); });
  }
  points.forEach(function(point){
    point.addEventListener('mouseenter', function(){ show(point); });
    point.addEventListener('mouseleave', hide);
    point.addEventListener('click', function(e){
      e.stopPropagation();
      if (tip.hidden || !point.classList.contains('hot')) { show(point); }
      else { hide(); }
    });
  });
  document.addEventListener('click', hide);
});
window.addEventListener('load', animate);
</script></body></html>"""


if __name__ == "__main__":
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    print(build(data, sys.argv[2] if len(sys.argv) > 2 else "web/result.html",
                sys.argv[3] if len(sys.argv) > 3 else ""))
