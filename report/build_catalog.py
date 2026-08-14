"""Каталог визуалов для отчёта: показываем варианты на настоящих данных.

Задача каталога это выбор. Каждый блок нарисован данными реальной сессии,
подписан по смыслу и снабжён пометкой, для чего он годится в разборе.
"""
import json
import math
import sys
from pathlib import Path

from report.watch_blocks import watch_rings, watch_tiles

TITLES = {"numeric": "Числа и логика", "spatial": "Пространство и формы",
          "verbal": "Слова и смыслы", "working_memory": "Память и внимание"}
COLORS = {"numeric": "#535BA4", "spatial": "#F16B14",
          "verbal": "#17875F", "working_memory": "#F4C15A"}
BANDS = [("delta", "дельта"), ("theta", "тета"), ("alpha", "альфа"),
         ("beta", "бета"), ("gamma", "гамма")]
BAND_COLORS = {"delta": "#3E4585", "theta": "#535BA4", "alpha": "#17875F",
               "beta": "#F16B14", "gamma": "#F4C15A"}


def donut(value, maximum, color, size=110, label="", sub=""):
    radius = size / 2 - 9
    circumference = 2 * math.pi * radius
    filled = max(0.0, min(1.0, value / maximum if maximum else 0)) * circumference
    return f'''<svg viewBox="0 0 {size} {size}" class="donut">
      <circle cx="{size/2}" cy="{size/2}" r="{radius}" fill="none"
        stroke="rgba(255,255,255,.10)" stroke-width="9"/>
      <circle cx="{size/2}" cy="{size/2}" r="{radius}" fill="none" stroke="{color}"
        stroke-width="9" stroke-linecap="round"
        stroke-dasharray="{filled:.1f} {circumference:.1f}"
        transform="rotate(-90 {size/2} {size/2})"/>
      <text x="{size/2}" y="{size/2+2}" text-anchor="middle" class="donut-value">{label}</text>
      <text x="{size/2}" y="{size/2+18}" text-anchor="middle" class="donut-sub">{sub}</text>
    </svg>'''


def radar(values, labels, color="#F16B14", size=220):
    count = len(values)
    center = size / 2
    radius = center - 34
    rings = "".join(
        f'<circle cx="{center}" cy="{center}" r="{radius*k:.1f}" fill="none" '
        f'stroke="rgba(255,255,255,.08)"/>' for k in (0.33, 0.66, 1.0))
    points, marks = [], []
    peak = max(values) or 1
    for i, (value, label) in enumerate(zip(values, labels)):
        angle = -math.pi / 2 + i * 2 * math.pi / count
        r = radius * (value / peak)
        x, y = center + r * math.cos(angle), center + r * math.sin(angle)
        points.append(f"{x:.1f},{y:.1f}")
        lx, ly = center + (radius + 20) * math.cos(angle), center + (radius + 20) * math.sin(angle)
        anchor = "middle" if abs(math.cos(angle)) < 0.3 else ("start" if math.cos(angle) > 0 else "end")
        marks.append(f'<text x="{lx:.0f}" y="{ly+4:.0f}" text-anchor="{anchor}" '
                     f'class="radar-label">{label}</text>')
    return f'''<svg viewBox="0 0 {size} {size}" class="radar">{rings}
      <polygon points="{" ".join(points)}" fill="{color}33" stroke="{color}" stroke-width="2"/>
      {"".join(marks)}</svg>'''


def bullet(value, target, maximum, color, width=250):
    v = min(1.0, value / maximum) * width
    t = min(1.0, target / maximum) * width
    return f'''<svg viewBox="0 0 {width} 26" class="bullet">
      <rect x="0" y="8" width="{width}" height="10" rx="5" fill="rgba(255,255,255,.08)"/>
      <rect x="0" y="8" width="{v:.1f}" height="10" rx="5" fill="{color}"/>
      <rect x="{t:.1f}" y="4" width="3" height="18" rx="1.5" fill="#fff"/>
    </svg>'''


def heatmap(rows, columns, values, low_color="#181D2B", high_color="#F16B14"):
    peak = max(max(row) for row in values) or 1
    cells = []
    for r, row in enumerate(values):
        line = "".join(
            f'<td><span class="heat" style="opacity:{0.15 + 0.85*v/peak:.2f}">'
            f'{v:.0f}</span></td>' for v in row)
        cells.append(f'<tr><th>{rows[r]}</th>{line}</tr>')
    header = "".join(f"<th>{c}</th>" for c in columns)
    return (f'<table class="heat-table"><thead><tr><th></th>{header}</tr></thead>'
            f'<tbody>{"".join(cells)}</tbody></table>')


def candles(series, width=280, height=120):
    """Свечи: диапазон и середина показателя внутри каждого блока."""
    step = width / (len(series) * 2)
    body = []
    all_values = [v for item in series for v in item["values"]]
    low, high = min(all_values), max(all_values)
    span = (high - low) or 1
    for i, item in enumerate(series):
        values = item["values"]
        lo, hi = min(values), max(values)
        mid = sum(values) / len(values)
        x = step * (i * 2 + 1)
        y1 = height - (hi - low) / span * (height - 20) - 10
        y2 = height - (lo - low) / span * (height - 20) - 10
        ym = height - (mid - low) / span * (height - 20) - 10
        body.append(f'<line x1="{x:.0f}" y1="{y1:.1f}" x2="{x:.0f}" y2="{y2:.1f}" '
                    f'stroke="{item["color"]}" stroke-width="2"/>'
                    f'<rect x="{x-9:.0f}" y="{min(ym, ym):.1f}" width="18" height="4" '
                    f'rx="2" fill="{item["color"]}"/>')
    return f'<svg viewBox="0 0 {width} {height}" class="candles">{"".join(body)}</svg>'


def area_log(freqs, values, color="#F16B14", width=320, height=130):
    """Спектр в логарифме мощности: иначе виден только горб медленных волн."""
    logs = [math.log10(max(v, 1e-6)) for v in values]
    low, high = min(logs), max(logs)
    span = (high - low) or 1
    step = width / (len(logs) - 1)
    points = [f"{i*step:.1f},{height - (v - low)/span*(height-16) - 8:.1f}"
              for i, v in enumerate(logs)]
    return (f'<svg viewBox="0 0 {width} {height}" class="area">'
            f'<polygon points="0,{height} {" ".join(points)} {width},{height}" '
            f'fill="{color}22"/>'
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" '
            f'stroke-width="2"/></svg>')


def stack(parts, width=280):
    total = sum(v for _, v in parts) or 1
    segments, offset = [], 0.0
    for name, value in parts:
        share = value / total * width
        segments.append(f'<rect x="{offset:.1f}" y="0" width="{share:.1f}" height="22" '
                        f'fill="{BAND_COLORS[name]}"/>')
        offset += share
    return f'<svg viewBox="0 0 {width} 22" class="stack">{"".join(segments)}</svg>'


def scatter(cards, width=290, height=200):
    dots = []
    for card in cards:
        if card["efficiency"] is None:
            continue
        x = 20 + (card["accuracy"]) * (width - 46)
        y = height - 24 - ((card["cost"] + 1.5) / 3.0) * (height - 44)
        dots.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="9" '
                    f'fill="{COLORS[card["domain"]]}"/>'
                    f'<text x="{x:.0f}" y="{y-14:.0f}" text-anchor="middle" '
                    f'class="dot-label">{TITLES[card["domain"]].split()[0]}</text>')
    return (f'<svg viewBox="0 0 {width} {height}" class="scatter">'
            f'<line x1="20" y1="{height-24}" x2="{width-10}" y2="{height-24}" '
            f'stroke="rgba(255,255,255,.15)"/>'
            f'<line x1="20" y1="10" x2="20" y2="{height-24}" '
            f'stroke="rgba(255,255,255,.15)"/>'
            f'<text x="{width-10}" y="{height-8}" text-anchor="end" class="axis">точность</text>'
            f'<text x="16" y="14" class="axis">цена усилия</text>'
            f'{"".join(dots)}</svg>')


def timeline_ribbon(points, color="#F16B14", width=300, height=54):
    if not points:
        return ""
    low, high = min(points), max(points)
    span = (high - low) or 1
    step = width / (len(points) - 1)
    bars = []
    for i, value in enumerate(points):
        norm = (value - low) / span
        bar_height = 8 + norm * (height - 16)
        bars.append(f'<rect x="{i*step:.1f}" y="{height - bar_height:.1f}" '
                    f'width="{max(2, step-1.5):.1f}" height="{bar_height:.1f}" '
                    f'rx="1.5" fill="{color}" opacity="{0.35 + 0.65*norm:.2f}"/>')
    return f'<svg viewBox="0 0 {width} {height}" class="ribbon">{"".join(bars)}</svg>'


def gauge(value, maximum, color, width=200, height=110):
    angle = math.pi * min(1.0, value / maximum if maximum else 0)
    cx, cy, r = width / 2, height - 12, width / 2 - 18
    x2, y2 = cx - r * math.cos(angle), cy - r * math.sin(angle)
    arc = (f'<path d="M {cx-r} {cy} A {r} {r} 0 0 1 {cx+r} {cy}" fill="none" '
           f'stroke="rgba(255,255,255,.10)" stroke-width="12" stroke-linecap="round"/>')
    value_arc = (f'<path d="M {cx-r} {cy} A {r} {r} 0 0 1 {x2:.1f} {y2:.1f}" fill="none" '
                 f'stroke="{color}" stroke-width="12" stroke-linecap="round"/>')
    return (f'<svg viewBox="0 0 {width} {height}" class="gauge">{arc}{value_arc}'
            f'<text x="{cx}" y="{cy-14}" text-anchor="middle" class="gauge-value">'
            f'{value:.2f}</text></svg>')


def pyramid(levels, width=260):
    rows = []
    for index, (title, value, color) in enumerate(levels):
        share = 40 + index * 18
        rows.append(f'<div class="pyr-row"><span class="pyr-bar" '
                    f'style="width:{share}%;background:{color}"></span>'
                    f'<span class="pyr-label">{title}<b>{value}</b></span></div>')
    return f'<div class="pyramid">{"".join(reversed(rows))}</div>'


def build(report: dict, out_path: str) -> str:
    blocks = report["blocks"]
    profile = report["profile"]
    domains = list(blocks)
    freqs = report["spectrum_freqs"]

    items = []

    def add(number, title, hint, use, body):
        items.append(f'''<div class="item">
          <div class="item-head"><span class="num">{number:02d}</span>
            <div><div class="item-title">{title}</div>
            <div class="item-hint">{hint}</div></div></div>
          <div class="item-body">{body}</div>
          <div class="item-use">{use}</div>
        </div>''')

    add(1, "Кольца состояния", "Одно число крупно, вокруг заполненное кольцо",
        "Шапка отчёта: фокус, стресс, вовлечение одним взглядом",
        "".join(donut(blocks[d]["state"]["focus"], 1.0, COLORS[d],
                      label=f'{blocks[d]["state"]["focus"]:.2f}',
                      sub=TITLES[d].split()[0]) for d in domains))

    add(2, "Радар по типам задач", "Четыре луча, площадь показывает профиль целиком",
        "Главная картинка разбора: видно форму, а не набор чисел",
        radar([blocks[d]["state"]["engagement"] for d in domains],
              [TITLES[d].split()[0] for d in domains]))

    add(3, "Спектр в логарифме", "Тот же спектр, но видна структура, а не только горб",
        "Замена нынешнего графика со спадом",
        "".join(f'<div class="mini">{area_log(freqs, blocks[d]["spectrum"], COLORS[d])}'
                f'<span>{TITLES[d]}</span></div>' for d in domains[:2]))

    add(4, "Лента напряжения по времени", "Столбики по ходу блока, выше значит напряжённее",
        "Отвечает на вопрос «на каком месте ребёнку стало тяжело»",
        "".join(f'<div class="mini">{timeline_ribbon(blocks[d]["timeline"], COLORS[d])}'
                f'<span>{TITLES[d]}</span></div>' for d in domains[:2]))

    add(5, "Тепловая карта ритмов", "Строки это ритмы, столбцы это блоки",
        "Плотная таблица для тех, кто любит цифры",
        heatmap([name for _, name in BANDS], [TITLES[d].split()[0] for d in domains],
                [[blocks[d]["bands"][key] for d in domains] for key, _ in BANDS]))

    add(6, "Стек ритмов", "Сто процентов мощности, поделённые между ритмами",
        "Показывает состав активности одной полосой",
        "".join(f'<div class="mini">{stack([(k, blocks[d]["bands"][k]) for k, _ in BANDS])}'
                f'<span>{TITLES[d]}</span></div>' for d in domains))

    add(7, "Карта результат и цена", "Точки в осях: точность против затраченного усилия",
        "Ядро методики: сильный канал сверху справа",
        scatter(profile["domains"]))

    add(8, "Свечи по блокам", "Диапазон колебаний состояния внутри блока",
        "Видно, ровно ли работал ребёнок или скакал",
        candles([{"values": blocks[d]["timeline"] or [0], "color": COLORS[d]}
                 for d in domains]))

    add(9, "Шкала с целью", "Полоса и белая метка ожидаемого уровня",
        "Сравнение с нормой, когда она появится после пилота",
        "".join(f'<div class="mini">{bullet(blocks[d]["state"]["relax"], 0.2, 0.35, COLORS[d])}'
                f'<span>{TITLES[d]}</span></div>' for d in domains))

    add(10, "Спидометр", "Один показатель на полукруглой шкале",
        "Крупный акцент на один вывод, например на напряжение",
        gauge(blocks[domains[0]]["state"]["stress"], 1.2, "#F16B14"))

    add(11, "Пирамида уровней", "Слои снизу вверх, каждый шире предыдущего",
        "Итоговая иерархия: от базового к сильному",
        pyramid([("Базовый уровень", "62%", "#3E4585"),
                 ("Рабочий уровень", "84%", "#535BA4"),
                 ("Сильная сторона", "97%", "#F16B14")]))

    rest_state = report["rest"]["state"]
    best = domains[0]
    add(12, "Кольца как на часах", "Три кольца: насколько заполнена личная норма",
        "Шапка отчёта и экран монитора: понятно без единого слова",
        watch_rings(
            [min(1.0, blocks[best]["state"]["focus"] / max(rest_state["focus"], .01) / 3),
             min(1.0, blocks[best]["state"]["load"] / max(rest_state["load"], .01) / 3),
             min(1.0, blocks[best]["state"]["relax"] / max(rest_state["relax"], .01) / 3)],
            ["#F16B14", "#535BA4", "#17875F"],
            ["Фокус", "Нагрузка", "Покой"]))

    add(13, "Плитки как в здоровье", "Показатель, число, тренд и микрографик",
        "Второй экран: много показателей мелкими блоками, ничего не теряется",
        watch_tiles([
            ("Фокус", f'{blocks[best]["state"]["focus"]:.2f}', "", "выше покоя",
             "#F16B14", blocks[best]["timeline"][:14]),
            ("Напряжение", f'{blocks[best]["state"]["stress"]:.2f}', "", "в коридоре",
             "#535BA4", blocks[domains[1]]["timeline"][:14]),
            ("Альфа-ритм", f'{report["iaf"] or 0:.1f}', " Гц", "личная частота",
             "#17875F", None),
            ("Качество", f'{blocks[best]["quality"]:.0f}', "%", "сигнал принят",
             "#F4C15A", None),
        ]))

    add(14, "Полосы по точкам съёма", "Четыре электрода отдельно",
        "Техническая честность: видно, откуда взялся сигнал",
        heatmap(report["channels"], [TITLES[d].split()[0] for d in domains],
                [[blocks[d]["per_channel_alpha"][i] for d in domains]
                 for i in range(len(report["channels"]))]))

    html = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Каталог визуалов · нейропрофориентация BHS</title>
<style>
@font-face {{ font-family:'Halvar Breitschrift'; src:url('fonts/HalvarBreit-Rg.woff2') format('woff2'); font-weight:400 }}
@font-face {{ font-family:'Halvar Breitschrift'; src:url('fonts/HalvarBreit-Md.woff2') format('woff2'); font-weight:500 }}
@font-face {{ font-family:'Halvar Breitschrift'; src:url('fonts/HalvarBreit-Bd.woff2') format('woff2'); font-weight:700 }}
:root {{ --orange:#F16B14; --indigo:#535BA4; --green:#17875F; --amber:#F4C15A;
  --dark:#111521; --dark2:#181D2B; --line:rgba(255,255,255,.08);
  --text:#F6F7F9; --muted:#8C93A6;
  --font:'Halvar Breitschrift','Archivo',-apple-system,sans-serif; }}
* {{ box-sizing:border-box; margin:0; padding:0 }}
body {{ background:var(--dark); color:var(--text); font-family:var(--font); padding:32px }}
.wrap {{ max-width:1240px; margin:0 auto }}
h1 {{ font-size:30px; font-weight:700; letter-spacing:-.5px; margin-bottom:8px }}
.lead {{ color:var(--muted); font-size:15px; line-height:1.6; max-width:720px; margin-bottom:28px }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(330px,1fr)); gap:16px }}
.item {{ background:var(--dark2); border-radius:28px; padding:20px; border:1px solid var(--line);
  display:flex; flex-direction:column }}
.item-head {{ display:flex; gap:12px; margin-bottom:14px }}
.num {{ font-size:12px; font-weight:700; color:var(--orange); padding-top:3px }}
.item-title {{ font-size:16px; font-weight:500 }}
.item-hint {{ font-size:12px; color:var(--muted); margin-top:3px; line-height:1.45 }}
.item-body {{ flex:1; display:flex; flex-wrap:wrap; gap:10px; align-items:center;
  justify-content:center; padding:10px 0 14px; min-height:130px }}
.item-use {{ font-size:12px; color:var(--muted); border-top:1px solid var(--line);
  padding-top:12px; line-height:1.5 }}
.mini {{ display:flex; flex-direction:column; gap:4px; align-items:center; width:100% }}
.mini span {{ font-size:11px; color:var(--muted) }}
.donut {{ width:100px; height:100px }}
.donut-value {{ fill:var(--text); font-size:19px; font-weight:500 }}
.donut-sub {{ fill:var(--muted); font-size:9px }}
.radar {{ width:210px; height:210px }}
.radar-label {{ fill:var(--muted); font-size:9px }}
.area,.ribbon,.stack,.bullet {{ width:100%; max-width:300px }}
.scatter {{ width:100%; max-width:290px }}
.axis,.dot-label {{ fill:var(--muted); font-size:9px }}
.dot-label {{ fill:var(--text) }}
.candles {{ width:100%; max-width:280px }}
.gauge {{ width:190px }}
.gauge-value {{ fill:var(--text); font-size:20px; font-weight:500 }}
.heat-table {{ width:100%; border-collapse:collapse; font-size:11px }}
.heat-table th {{ color:var(--muted); font-weight:400; text-align:left; padding:3px 5px }}
.heat-table td {{ padding:2px }}
.heat {{ display:block; background:var(--orange); border-radius:5px; padding:5px 2px;
  text-align:center; color:#fff; font-size:10px }}
.rings {{ width:180px; height:180px }}
.ring-legend {{ display:flex; flex-direction:column; gap:6px; justify-content:center }}
.ring-leg {{ font-size:11px; color:var(--muted); display:flex; align-items:center; gap:7px }}
.ring-leg i {{ width:9px; height:9px; border-radius:50% }}
.ring-leg b {{ color:var(--text); font-weight:500; margin-left:2px }}
.tiles {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; width:100% }}
.tile {{ background:rgba(255,255,255,.04); border-radius:16px; padding:11px 13px }}
.tile-title {{ font-size:10px; font-weight:500; text-transform:uppercase; letter-spacing:.06em }}
.tile-value {{ font-size:24px; font-weight:500; margin-top:3px }}
.tile-value small {{ font-size:11px; color:var(--muted); margin-left:2px }}
.tile-trend {{ font-size:10px; color:var(--muted) }}
.tile-spark {{ width:100%; height:26px; margin-top:4px }}
.pyramid {{ width:100%; display:flex; flex-direction:column; gap:6px; align-items:center }}
.pyr-row {{ width:100%; display:flex; align-items:center; gap:8px; justify-content:center }}
.pyr-bar {{ height:26px; border-radius:6px }}
.pyr-label {{ font-size:11px; color:var(--muted); display:flex; gap:6px }}
.pyr-label b {{ color:var(--text); font-weight:500 }}
.note {{ margin-top:26px; background:var(--dark2); border-radius:28px; padding:22px 24px;
  border:1px solid var(--line); font-size:14px; line-height:1.65; color:#c9cedb }}
.note b {{ color:var(--text) }}
</style></head><body><div class="wrap">
<h1>Каталог визуалов</h1>
<p class="lead">Двенадцать вариантов блоков, нарисованных данными реальной сессии
{report["session_id"]}. Выбери номера, которые берём в отчёт, и скажи, чего не хватает.
Цвета и шрифт уже фирменные: оранжевый ядро, индиго и зелёный акценты.</p>
<div class="grid">{"".join(items)}</div>
<div class="note"><b>Про спад на спектре.</b> Мощность мозговых ритмов всегда падает
с частотой, это закон, а не поломка прибора: медленные волны в десятки раз мощнее
быстрых. На линейной шкале видно только горб слева. Вариант 03 показывает тот же
спектр в логарифме, там читается вся структура, включая альфа-пик и бета-диапазон.</div>
</div></body></html>'''
    Path(out_path).write_text(html, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    report = json.load(open(sys.argv[1], encoding="utf-8"))
    print(build(report, sys.argv[2] if len(sys.argv) > 2 else "web/catalog.html"))
