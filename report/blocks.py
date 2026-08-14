"""Кирпичи отчёта: каждая функция рисует один блок и ничего не знает о странице."""
import math

TITLES = {"numeric": "Числа и логика", "spatial": "Пространство и формы",
          "verbal": "Слова и смыслы", "working_memory": "Память и внимание"}
SHORT = {"numeric": "Числа", "spatial": "Пространство",
         "verbal": "Слова", "working_memory": "Память"}
COLORS = {"numeric": "#535BA4", "spatial": "#F16B14",
          "verbal": "#17875F", "working_memory": "#F4C15A"}
BANDS = [("delta", "дельта"), ("theta", "тета"), ("alpha", "альфа"),
         ("beta", "бета"), ("gamma", "гамма")]
BAND_COLORS = {"delta": "#3E4585", "theta": "#535BA4", "alpha": "#17875F",
               "beta": "#F16B14", "gamma": "#F4C15A"}


def rings(values, colors, labels, size=200):
    circles, legend = [], []
    for index, (value, color, label) in enumerate(zip(values, colors, labels)):
        radius = size / 2 - 15 - index * 27
        circumference = 2 * math.pi * radius
        filled = max(0.03, min(1.0, value)) * circumference
        circles.append(
            '<circle cx="%s" cy="%s" r="%.1f" fill="none" stroke="%s" '
            'stroke-opacity=".16" stroke-width="21"/>'
            '<circle cx="%s" cy="%s" r="%.1f" fill="none" stroke="%s" stroke-width="21" '
            'stroke-linecap="round" stroke-dasharray="%.1f %.1f" '
            'transform="rotate(-90 %s %s)"/>'
            % (size/2, size/2, radius, color, size/2, size/2, radius, color,
               filled, circumference, size/2, size/2))
        legend.append('<span class="ring-leg"><i style="background:%s"></i>%s'
                      '<b>%d%%</b></span>' % (color, label, round(value * 100)))
    return ('<div class="rings-wrap"><svg viewBox="0 0 %s %s" class="rings">%s</svg>'
            '<div class="ring-legend">%s</div></div>'
            % (size, size, "".join(circles), "".join(legend)))


def tiles(items):
    cells = []
    for title, value, unit, trend, color, points in items:
        spark = ""
        if points and len(points) > 1:
            low, high = min(points), max(points)
            span = (high - low) or 1
            step = 110 / (len(points) - 1)
            coords = " ".join("%.1f,%.1f" % (i * step, 30 - (v - low) / span * 24 - 3)
                              for i, v in enumerate(points))
            spark = ('<svg viewBox="0 0 110 30" class="tile-spark"><polyline points="%s" '
                     'fill="none" stroke="%s" stroke-width="2" stroke-linecap="round"/></svg>'
                     % (coords, color))
        cells.append('<div class="tile"><div class="tile-title" style="color:%s">%s</div>'
                     '<div class="tile-value">%s<small>%s</small></div>'
                     '<div class="tile-trend">%s</div>%s</div>'
                     % (color, title, value, unit, trend, spark))
    return '<div class="tiles">%s</div>' % "".join(cells)


def test_track(domain, block, color, width=920, height=120):
    """Дорожка блока: состояние линией, ответы точками под ней.

    Это ответ на главный вопрос разбора: что происходило с мозгом на конкретном
    задании и где ребёнок ошибался.
    """
    line = block["timeline"]
    duration = block["duration_s"] or 1
    body = []
    if len(line) > 1:
        low, high = min(line), max(line)
        span = (high - low) or 1
        step = width / (len(line) - 1)
        points = " ".join("%.1f,%.1f" % (i * step, 76 - (v - low) / span * 60)
                          for i, v in enumerate(line))
        body.append('<polygon points="0,86 %s %s,86" fill="%s22"/>' % (points, width, color))
        body.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2.5"/>'
                    % (points, color))
    for trial in block["trials"]:
        x = trial["at"] / duration * width
        if trial["correct"]:
            body.append('<circle cx="%.1f" cy="102" r="3.5" fill="%s" opacity=".55"/>'
                        % (x, color))
        else:
            body.append('<path d="M%.1f 97 l6 10 M%.1f 107 l6 -10" stroke="#F0666B" '
                        'stroke-width="2" stroke-linecap="round"/>' % (x - 3, x - 3))
    return ('<svg viewBox="0 0 %s %s" class="track">%s</svg>' % (width, height, "".join(body)))


def spectrum_log(freqs, series, width=880, height=210):
    if not freqs:
        return ""
    paths, ticks = [], []
    for domain, values in series.items():
        logs = [math.log10(max(v, 1e-7)) for v in values]
        low, high = min(logs), max(logs)
        span = (high - low) or 1
        step = width / (len(logs) - 1)
        points = " ".join("%.1f,%.1f" % (i * step, height - 24 - (v - low) / span * (height - 44))
                          for i, v in enumerate(logs))
        paths.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2.2"/>'
                     % (points, COLORS[domain]))
    for hz in (4, 8, 13, 20, 30, 40):
        if hz < freqs[0] or hz > freqs[-1]:
            continue
        x = (hz - freqs[0]) / (freqs[-1] - freqs[0]) * width
        ticks.append('<line x1="%.0f" y1="0" x2="%.0f" y2="%s" stroke="rgba(255,255,255,.07)" '
                     'stroke-dasharray="4 7"/><text x="%.0f" y="%s" fill="#8C93A6" '
                     'font-size="11">%s Гц</text>' % (x, x, height - 26, x + 5, height - 8, hz))
    return ('<svg viewBox="0 0 %s %s" class="spectrum">%s%s</svg>'
            % (width, height, "".join(ticks), "".join(paths)))


def heat_table(row_titles, col_titles, values, unit=""):
    peak = max(max(row) for row in values) or 1
    rows = []
    for index, row in enumerate(values):
        cells = "".join('<td><span class="heat" style="opacity:%.2f">%.0f%s</span></td>'
                        % (0.16 + 0.84 * v / peak, v, unit) for v in row)
        rows.append("<tr><th>%s</th>%s</tr>" % (row_titles[index], cells))
    header = "".join("<th>%s</th>" % c for c in col_titles)
    return ('<table class="heat-table"><thead><tr><th></th>%s</tr></thead><tbody>%s</tbody></table>'
            % (header, "".join(rows)))


def band_stack(block, width=380):
    parts = [(key, block["bands"][key]) for key, _ in BANDS]
    total = sum(v for _, v in parts) or 1
    offset, segments, marks = 0.0, [], []
    for name, value in parts:
        share = value / total * width
        segments.append('<rect x="%.1f" y="0" width="%.1f" height="26" fill="%s"/>'
                        % (offset, share, BAND_COLORS[name]))
        if share > 34:
            marks.append('<text x="%.1f" y="17" fill="#fff" font-size="10" '
                         'text-anchor="middle">%.0f%%</text>' % (offset + share / 2, value))
        offset += share
    return ('<svg viewBox="0 0 %s 26" class="stack">%s%s</svg>'
            % (width, "".join(segments), "".join(marks)))


def candles(series, width=380, height=140):
    body = []
    values = [v for item in series for v in item["values"]]
    low, high = min(values), max(values)
    span = (high - low) or 1
    step = width / len(series)
    for index, item in enumerate(series):
        block = item["values"]
        lo, hi, mid = min(block), max(block), sum(block) / len(block)
        x = step * (index + 0.5)
        y_top = height - 26 - (hi - low) / span * (height - 46)
        y_bottom = height - 26 - (lo - low) / span * (height - 46)
        y_mid = height - 26 - (mid - low) / span * (height - 46)
        body.append('<line x1="%.0f" y1="%.1f" x2="%.0f" y2="%.1f" stroke="%s" '
                    'stroke-width="2.5" stroke-linecap="round"/>'
                    '<rect x="%.0f" y="%.1f" width="26" height="5" rx="2.5" fill="%s"/>'
                    '<text x="%.0f" y="%s" text-anchor="middle" fill="#8C93A6" '
                    'font-size="10">%s</text>'
                    % (x, y_top, x, y_bottom, item["color"], x - 13, y_mid - 2.5,
                       item["color"], x, height - 8, item["label"]))
    return '<svg viewBox="0 0 %s %s" class="candles">%s</svg>' % (width, height, "".join(body))


def radar(values, labels, color="#F16B14", size=300):
    count = len(values)
    center, radius = size / 2, size / 2 - 52
    rings_svg = "".join('<circle cx="%s" cy="%s" r="%.1f" fill="none" '
                        'stroke="rgba(255,255,255,.08)"/>' % (center, center, radius * k)
                        for k in (0.33, 0.66, 1.0))
    points, marks = [], []
    peak = max(values) or 1
    for index, (value, label) in enumerate(zip(values, labels)):
        angle = -math.pi / 2 + index * 2 * math.pi / count
        r = radius * (value / peak)
        points.append("%.1f,%.1f" % (center + r * math.cos(angle), center + r * math.sin(angle)))
        lx = center + (radius + 26) * math.cos(angle)
        ly = center + (radius + 26) * math.sin(angle)
        anchor = "middle" if abs(math.cos(angle)) < 0.3 else ("start" if math.cos(angle) > 0 else "end")
        marks.append('<text x="%.0f" y="%.0f" text-anchor="%s" class="radar-label">%s</text>'
                     % (lx, ly + 4, anchor, label))
    return ('<svg viewBox="0 0 %s %s" class="radar">%s<polygon points="%s" fill="%s33" '
            'stroke="%s" stroke-width="2.5"/>%s</svg>'
            % (size, size, rings_svg, " ".join(points), color, color, "".join(marks)))


def scatter(cards, width=420, height=280):
    dots = []
    for card in cards:
        if card["efficiency"] is None:
            continue
        x = 40 + card["accuracy"] * (width - 70)
        y = height - 36 - ((card["cost"] + 1.6) / 3.2) * (height - 66)
        dots.append('<circle cx="%.0f" cy="%.0f" r="11" fill="%s"/>'
                    '<text x="%.0f" y="%.0f" text-anchor="middle" class="dot-label">%s</text>'
                    % (x, y, COLORS[card["domain"]], x, y - 18, SHORT[card["domain"]]))
    return ('<svg viewBox="0 0 %s %s" class="scatter">'
            '<line x1="40" y1="%s" x2="%s" y2="%s" stroke="rgba(255,255,255,.15)"/>'
            '<line x1="40" y1="14" x2="40" y2="%s" stroke="rgba(255,255,255,.15)"/>'
            '<text x="%s" y="%s" text-anchor="end" class="axis">точность выше →</text>'
            '<text x="34" y="18" text-anchor="end" class="axis" '
            'transform="rotate(-90 34 18)">цена усилия выше →</text>%s</svg>'
            % (width, height, height - 36, width - 14, height - 36, height - 36,
               width - 14, height - 14, "".join(dots)))


def gauge(value, maximum, color, caption, width=210, height=124):
    angle = math.pi * min(1.0, value / maximum if maximum else 0)
    cx, cy, r = width / 2, height - 26, width / 2 - 22
    x2, y2 = cx - r * math.cos(angle), cy - r * math.sin(angle)
    return ('<svg viewBox="0 0 %s %s" class="gauge">'
            '<path d="M %s %s A %s %s 0 0 1 %s %s" fill="none" stroke="rgba(255,255,255,.10)" '
            'stroke-width="13" stroke-linecap="round"/>'
            '<path d="M %s %s A %s %s 0 0 1 %.1f %.1f" fill="none" stroke="%s" '
            'stroke-width="13" stroke-linecap="round"/>'
            '<text x="%s" y="%s" text-anchor="middle" class="gauge-value">%.2f</text>'
            '<text x="%s" y="%s" text-anchor="middle" class="gauge-cap">%s</text></svg>'
            % (width, height, cx - r, cy, r, r, cx + r, cy,
               cx - r, cy, r, r, x2, y2, color,
               cx, cy - 16, value, cx, height - 6, caption))


def bullet_row(label, value, target, maximum, color, width=300):
    v = min(1.0, value / maximum) * width
    t = min(1.0, target / maximum) * width
    return ('<div class="mini-row"><span class="mini-name">%s</span>'
            '<svg viewBox="0 0 %s 22" class="bullet">'
            '<rect x="0" y="7" width="%s" height="9" rx="4.5" fill="rgba(255,255,255,.08)"/>'
            '<rect x="0" y="7" width="%.1f" height="9" rx="4.5" fill="%s"/>'
            '<rect x="%.1f" y="3" width="3" height="17" rx="1.5" fill="#fff"/></svg>'
            '<span class="mini-val">%.2f</span></div>'
            % (label, width, width, v, color, t, value))


def pyramid(levels):
    rows = []
    for index, (title, value, color) in enumerate(levels):
        rows.append('<div class="pyr-row"><span class="pyr-bar" style="width:%s%%;'
                    'background:%s"></span><span class="pyr-label">%s<b>%s</b></span></div>'
                    % (44 + index * 19, color, title, value))
    return '<div class="pyramid">%s</div>' % "".join(reversed(rows))


def donut_ring(items, center_title, center_caption, size=150, stroke=15):
    """Кольцо долей с легендой и подсветкой по наведению.

    Сегменты рисуются штриховкой окружности: длина штриха это доля, смещение
    это накопленный угол. При наведении на сегмент или строку легенды остальные
    приглушаются, чтобы читалась одна доля за раз.
    """
    radius = size / 2 - stroke
    circumference = 2 * math.pi * radius
    arcs, rows, offset = [], [], 0.0
    total = sum(value for _, value, _ in items) or 1
    for index, (label, value, color) in enumerate(items):
        share = value / total
        arcs.append(
            '<circle class="ring-arc" data-arc="%d" cx="%s" cy="%s" r="%.1f" fill="none" '
            'stroke="%s" stroke-width="%s" stroke-dasharray="%.2f %.2f" '
            'stroke-dashoffset="%.2f"/>'
            % (index, size / 2, size / 2, radius, color, stroke,
               max(share * circumference - 2, 0.5), circumference,
               -offset * circumference))
        rows.append(
            '<button type="button" class="ring-row" data-row="%d">'
            '<span class="ring-chip" style="background:%s"></span>'
            '<span class="ring-name">%s</span>'
            '<span class="ring-pct">%.1f%%</span></button>'
            % (index, color, label, share * 100))
        offset += share
    # длинное слово в центре уменьшаем, чтобы оно не задевало кольцо
    title_size = 19 if len(str(center_title)) <= 6 else (15 if len(str(center_title)) <= 9 else 12)
    return ('<div class="donut">'
            '<div class="donut-figure"><svg viewBox="0 0 %s %s" class="donut-svg">%s</svg>'
            '<div class="donut-center"><span class="donut-title" style="font-size:%dpx">%s</span>'
            '<span class="donut-caption">%s</span></div></div>'
            '<div class="donut-legend">%s</div></div>'
            % (size, size, "".join(arcs), title_size, center_title,
               center_caption, "".join(rows)))
