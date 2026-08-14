"""Графика дашборда: большая дорожка сессии, кольца, полосы."""
import math

DOMAIN_COLORS = {"numeric": "#5B8DEF", "spatial": "#F16B14",
                 "verbal": "#22B57C", "working_memory": "#F4C15A"}
LINE_COLORS = {"stress": "#F0666B", "engage": "#F16B14", "calm": "#22B57C"}


def _fmt_t(t):
    return "%d:%02d" % (int(t // 60), int(t % 60))


def score_ring(score, color, size=120, stroke=10, label=None):
    radius = size / 2 - stroke
    circumference = 2 * math.pi * radius
    target = max(0.02, min(1.0, score / 100)) * circumference
    return ('<svg viewBox="0 0 %s %s" class="ring"><circle cx="%s" cy="%s" r="%.1f" '
            'fill="none" stroke="rgba(255,255,255,.08)" stroke-width="%s"/>'
            '<circle class="ring-fill" cx="%s" cy="%s" r="%.1f" fill="none" stroke="%s" '
            'stroke-width="%s" stroke-linecap="round" stroke-dasharray="0 %.1f" '
            'data-target="%.1f %.1f" transform="rotate(-90 %s %s)"/>'
            '<text x="%s" y="%s" text-anchor="middle" class="ring-num">%s</text></svg>'
            % (size, size, size / 2, size / 2, radius, stroke,
               size / 2, size / 2, radius, color, stroke, circumference,
               target, circumference, size / 2, size / 2,
               size / 2, size / 2 + 9, label if label is not None else score))


def session_chart(tl, human_domains, width=1080, height=300):
    """Дорожка всей сессии: фазы фоном, три линии состояния, ответы снизу."""
    duration = tl["duration_s"] or 1
    left, right, top, bottom = 10, 10, 34, 56
    plot_w, plot_h = width - left - right, height - top - bottom

    def x(t):
        return left + t / duration * plot_w

    def y(v):
        return top + (100 - v) / 100 * plot_h

    parts = []
    # фазы фоном
    for ph in tl["phases"]:
        px, pw = x(ph["start"]), max(x(ph["end"]) - x(ph["start"]), 2)
        if ph["kind"] == "block":
            color = DOMAIN_COLORS.get(ph["domain"], "#666")
            parts.append('<rect x="%.1f" y="%s" width="%.1f" height="%s" fill="%s" '
                         'opacity="0.10"/>' % (px, top, pw, plot_h, color))
            name = human_domains.get(ph["domain"], ("", ""))[0]
            parts.append('<text x="%.1f" y="%s" class="phase-label" fill="%s">%s</text>'
                         % (px + 6, top - 8, color, name))
        elif ph["kind"] == "calib":
            parts.append('<rect x="%.1f" y="%s" width="%.1f" height="%s" '
                         'fill="rgba(255,255,255,.045)"/>' % (px, top, pw, plot_h))
            parts.append('<text x="%.1f" y="%s" class="phase-label" '
                         'fill="#96A0B5">%s</text>' % (px + 6, top - 8, ph["label"]))
    # сетка уровней
    for level in (25, 50, 75):
        parts.append('<line x1="%s" y1="%.1f" x2="%s" y2="%.1f" '
                     'stroke="rgba(255,255,255,.06)"%s/>'
                     % (left, y(level), left + plot_w, y(level),
                        ' stroke-dasharray="3 6"' if level != 50 else ""))
    parts.append('<text x="%s" y="%.1f" class="axis-label">покой</text>'
                 % (left + plot_w - 44, y(50) - 6))
    # линии
    for key in ("calm", "engage", "stress"):
        values = tl["series"][key]
        segment = []
        for t, v in zip(tl["times"], values):
            if v is None:
                if len(segment) > 1:
                    parts.append('<polyline points="%s" fill="none" stroke="%s" '
                                 'stroke-width="2.4" stroke-linejoin="round"/>'
                                 % (" ".join(segment), LINE_COLORS[key]))
                segment = []
                continue
            segment.append("%.1f,%.1f" % (x(t), y(v)))
        if len(segment) > 1:
            parts.append('<polyline points="%s" fill="none" stroke="%s" '
                         'stroke-width="2.4" stroke-linejoin="round"/>'
                         % (" ".join(segment), LINE_COLORS[key]))
    # пик напряжения
    peak = tl.get("peak")
    if peak:
        px = x(peak["t"])
        parts.append('<line x1="%.1f" y1="%s" x2="%.1f" y2="%s" stroke="#F0666B" '
                     'stroke-width="1.5" stroke-dasharray="5 5" opacity=".8"/>'
                     % (px, top, px, top + plot_h))
        chip_w = 176
        cx = min(max(px - chip_w / 2, left), left + plot_w - chip_w)
        parts.append('<rect x="%.1f" y="%s" width="%s" height="24" rx="12" '
                     'fill="#2A1519" stroke="#F0666B" stroke-opacity=".5"/>'
                     '<text x="%.1f" y="%s" text-anchor="middle" class="peak-label">'
                     'пик напряжения · %s</text>'
                     % (cx, top + 6, chip_w, cx + chip_w / 2, top + 22, _fmt_t(peak["t"])))
    # ответы по низу
    tick_y = top + plot_h + 16
    for tick in tl["ticks"]:
        tx = x(tick["t"])
        if tick["ok"]:
            parts.append('<circle cx="%.1f" cy="%s" r="2.4" fill="#96A0B5" '
                         'opacity=".5"/>' % (tx, tick_y))
        else:
            parts.append('<path d="M%.1f %s l7 7 M%.1f %s l7 -7" stroke="#F0666B" '
                         'stroke-width="2.2" stroke-linecap="round"/>'
                         % (tx - 3.5, tick_y - 3.5, tx - 3.5, tick_y + 3.5))
    # ось времени
    step = 60 if duration > 150 else 30
    t = 0
    while t <= duration:
        parts.append('<text x="%.1f" y="%s" class="axis-label">%s</text>'
                     % (x(t) + 2, height - 6, _fmt_t(t)))
        t += step
    return ('<svg viewBox="0 0 %s %s" class="session-chart" '
            'preserveAspectRatio="none">%s</svg>' % (width, height, "".join(parts)))


def hbar(label, value, color, right_text=None, mid=True):
    return ('<div class="hb"><span class="hb-name">%s</span>'
            '<div class="hb-track">%s<i class="hb-fill" data-w="%d" '
            'style="background:%s"></i></div><span class="hb-val">%s</span></div>'
            % (label, '<b class="hb-mid"></b>' if mid else "", max(2, min(100, value)),
               color, right_text if right_text is not None else value))


def order_bars(workability, human_domains):
    rows = []
    for w in workability:
        name = human_domains.get(w["domain"], ("", ""))[0]
        rows.append(hbar("%d-й · %s" % (w["order"], name), w["score"],
                         DOMAIN_COLORS.get(w["domain"], "#888")))
    return "".join(rows)


def _phase_x(t, duration, width):
    return t / duration * width


def session_tracks(tl, human_domains, width=1060, pulse=None):
    """Сессия раздельными лентами: шкала этапов сверху, ниже по одной метрике.

    Замена перегруженной дорожке: три линии в одном поле читались кашей.
    Здесь каждая лента отвечает на один вопрос, а время у всех общее.
    """
    duration = tl["duration_s"] or 1
    header_h, track_h, label_w = 34, 92, 0

    def x(t):
        return _phase_x(t, duration, width)

    # шкала этапов: цветные сегменты блоков, серые для подготовки и пауз
    head = []
    for ph in tl["phases"]:
        px, pw = x(ph["start"]), max(x(ph["end"]) - x(ph["start"]), 2)
        if ph["kind"] == "block":
            color = DOMAIN_COLORS.get(ph["domain"], "#666")
            name = human_domains.get(ph["domain"], ("", ""))[0]
            head.append('<rect x="%.1f" y="4" width="%.1f" height="26" rx="7" '
                        'fill="%s" opacity=".92"/>' % (px, pw, color))
            if pw > 90:
                head.append('<text x="%.1f" y="21" text-anchor="middle" '
                            'class="seg-label">%s</text>' % (px + pw / 2, name))
        else:
            label = "подготовка" if ph["kind"] == "calib" else ""
            head.append('<rect x="%.1f" y="4" width="%.1f" height="26" rx="7" '
                        'fill="rgba(255,255,255,.10)"/>' % (px, pw))
            if label and pw > 80:
                head.append('<text x="%.1f" y="21" text-anchor="middle" '
                            'class="seg-label mut">%s</text>' % (px + pw / 2, label))
    header = ('<svg viewBox="0 0 %s %s" class="tracks-head" '
              'preserveAspectRatio="none">%s</svg>' % (width, header_h, "".join(head)))

    def lane(key, color, with_marks):
        parts = []
        # фоновые полосы блоков без подписей, только цветовая связь со шкалой
        for ph in tl["phases"]:
            if ph["kind"] != "block":
                continue
            px, pw = x(ph["start"]), max(x(ph["end"]) - x(ph["start"]), 2)
            parts.append('<rect x="%.1f" y="0" width="%.1f" height="%s" fill="%s" '
                         'opacity=".07"/>' % (px, pw, track_h,
                                              DOMAIN_COLORS.get(ph["domain"], "#666")))
        # уровень покоя
        mid_y = track_h - 14 - (50 / 100) * (track_h - 30)
        parts.append('<line x1="0" y1="%.1f" x2="%s" y2="%.1f" '
                     'stroke="rgba(255,255,255,.22)" stroke-dasharray="4 6"/>'
                     % (mid_y, width, mid_y))
        parts.append('<text x="%s" y="%.1f" text-anchor="end" class="axis-label">'
                     'покой</text>' % (width - 4, mid_y - 4))
        # линия метрики: короткие разрывы сшиваем, длинные показываем
        # пунктирным мостиком, чтобы линия читалась непрерывной, а шумные
        # места оставались честно помеченными
        points = [(t, v) for t, v in zip(tl["times"], tl["series"][key])
                  if v is not None]
        segments, current = [], []
        for t, v in points:
            if current and t - current[-1][0] > 3.5:
                segments.append(current)
                current = []
            current.append((t, v))
        if current:
            segments.append(current)

        def xy(pair):
            return "%.1f,%.1f" % (x(pair[0]),
                                  track_h - 14 - (pair[1] / 100) * (track_h - 30))

        for index, segment in enumerate(segments):
            if index > 0:
                prev_last = segments[index - 1][-1]
                parts.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" '
                             'stroke-width="1.6" stroke-dasharray="2 6" '
                             'opacity=".55"/>'
                             % (*xy(prev_last).split(","), *xy(segment[0]).split(","),
                                color))
            if len(segment) > 1:
                parts.append('<polyline points="%s" fill="none" stroke="%s" '
                             'stroke-width="2.6" stroke-linejoin="round" '
                             'stroke-linecap="round"/>'
                             % (" ".join(xy(pt) for pt in segment), color))
        if with_marks:
            peak = tl.get("peak")
            if peak:
                px = x(peak["t"])
                parts.append('<line x1="%.1f" y1="0" x2="%.1f" y2="%s" stroke="%s" '
                             'stroke-width="1.5" stroke-dasharray="5 5"/>'
                             % (px, px, track_h - 12, color))
            for tick in tl["ticks"]:
                if tick["ok"]:
                    continue
                tx = x(tick["t"])
                parts.append('<path d="M%.1f %s l7 7 M%.1f %s l7 -7" stroke="%s" '
                             'stroke-width="2.2" stroke-linecap="round"/>'
                             % (tx - 3.5, track_h - 10, tx - 3.5, track_h - 3, color))
        return ('<svg viewBox="0 0 %s %s" class="track-lane" '
                'preserveAspectRatio="none">%s</svg>' % (width, track_h, "".join(parts)))

    lanes = [
        ("Напряжение", "насколько дорого давались задачи; крестики это ошибки, "
         "пунктирная черта это самый тяжёлый момент", "#F0666B", "stress", True),
        ("Включённость", "насколько мозг был в работе", "#F16B14", "engage", False),
        ("Спокойствие", "работа без внутренней тревоги", "#22B57C", "calm", False),
    ]
    body = "".join(
        '<div class="lane-row"><div class="lane-head">'
        '<b style="color:%s">%s</b><span>%s</span></div>%s</div>'
        % (color, title, hint, lane(key, color, marks))
        for title, hint, color, key, marks in lanes)

    # пульсовая лента: сердце под мозгом, из оптического канала прибора
    points = [(p["t"], p["bpm"]) for p in (pulse or {}).get("series", [])
              if 0 <= p["t"] <= duration]
    if len(points) >= 4:
        low = min(v for _, v in points)
        high = max(v for _, v in points)
        span = (high - low) or 1
        h = 72
        segs = []
        for ph in tl["phases"]:
            if ph["kind"] != "block":
                continue
            segs.append('<rect x="%.1f" y="0" width="%.1f" height="%s" fill="%s" '
                        'opacity=".07"/>' % (x(ph["start"]),
                                             max(x(ph["end"]) - x(ph["start"]), 2), h,
                                             DOMAIN_COLORS.get(ph["domain"], "#666")))
        line = " ".join("%.1f,%.1f" % (x(t), h - 12 - (v - low) / span * (h - 26))
                        for t, v in points)
        segs.append('<polyline points="%s" fill="none" stroke="#FF7AA2" '
                    'stroke-width="2.6" stroke-linejoin="round" '
                    'stroke-linecap="round"/>' % line)
        segs.append('<text x="%s" y="14" text-anchor="end" class="axis-label">'
                    'до %d</text>' % (width - 6, high))
        segs.append('<text x="%s" y="%s" text-anchor="end" class="axis-label">'
                    'от %d</text>' % (width - 6, h - 4, low))
        body += ('<div class="lane-row"><div class="lane-head">'
                 '<b style="color:#FF7AA2">Пульс</b>'
                 '<span>удары в минуту, оптический датчик прибора</span></div>'
                 '<svg viewBox="0 0 %s %s" class="track-lane" '
                 'preserveAspectRatio="none">%s</svg></div>'
                 % (width, h, "".join(segs)))

    # ось времени одна на всех
    ticks = []
    step = 60 if duration > 150 else 30
    t = 0
    while t <= duration:
        ticks.append('<span style="left:%.2f%%">%s</span>'
                     % (t / duration * 100, _fmt_t(t)))
        t += step
    axis = '<div class="tracks-axis">%s</div>' % "".join(ticks)

    return '<div class="tracks">%s%s%s</div>' % (header, body, axis)


def effort_map(cards, human_short, width=980, height=440):
    """Карта когнитивной эффективности: результат против энергозатрат.

    Оси подстраиваются под данные: у сильного ребёнка все точности живут
    в верхней четверти, и без зума точки слипаются в углу. Подписи ушли
    в легенду, детали всплывают при наведении и по касанию.
    """
    plotted = [c for c in cards if c.get("cost") is not None]
    if not plotted:
        return ""
    left, right, top, bottom = 74, 34, 26, 60
    plot_w, plot_h = width - left - right, height - top - bottom

    acc_min = min(c["accuracy"] for c in plotted)
    x_lo = max(0.0, min(acc_min - 0.12, 0.7))
    x_lo = int(x_lo * 20) / 20.0            # к шагу пять процентов
    x_hi = 1.02
    cost_values = [c["cost"] for c in plotted]
    y_pad = 0.5
    y_lo = min(cost_values) - y_pad
    y_hi = max(cost_values) + y_pad
    if y_hi - y_lo < 1.6:
        middle = (y_hi + y_lo) / 2
        y_lo, y_hi = middle - 0.8, middle + 0.8

    def px(accuracy):
        return left + (accuracy - x_lo) / (x_hi - x_lo) * plot_w

    def py(cost):
        return top + (cost - y_lo) / (y_hi - y_lo) * plot_h

    mid_x, mid_y = (x_lo + x_hi) / 2, (y_lo + y_hi) / 2
    parts = [
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#22B57C" '
        'opacity=".08" rx="14"/>' % (px(mid_x), py(mid_y),
                                     px(x_hi) - px(mid_x), py(y_hi) - py(mid_y)),
        '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#F0666B" '
        'opacity=".07" rx="14"/>' % (px(x_lo), py(y_lo),
                                     px(mid_x) - px(x_lo), py(mid_y) - py(y_lo)),
        '<text x="%.1f" y="%.1f" class="zone-label" fill="#5BD8A4" '
        'text-anchor="end">зона силы: высокий результат малой ценой</text>'
        % (px(x_hi) - 12, py(y_hi) - 12),
        '<text x="%.1f" y="%.1f" class="zone-label" fill="#FFA6AA">'
        'дорогая зона: результат через усилие</text>'
        % (px(x_lo) + 12, py(y_lo) + 20),
        '<line x1="%s" y1="%.1f" x2="%s" y2="%.1f" '
        'stroke="rgba(255,255,255,.18)"/>' % (left, py(y_hi), left + plot_w, py(y_hi)),
        '<line x1="%s" y1="%s" x2="%s" y2="%.1f" '
        'stroke="rgba(255,255,255,.18)"/>' % (left, top, left, py(y_hi)),
        '<text x="%s" y="%s" class="axis-title">результат: доля верных ответов →'
        '</text>' % (left + plot_w - 4, height - 20),
        '<text x="26" y="%.1f" class="axis-title" transform="rotate(-90 26 %.1f)">'
        '← энергозатраты: цена усилия</text>'
        % (top + plot_h / 2, top + plot_h / 2),
    ]
    share = x_lo
    while share <= 1.001:
        parts.append('<line x1="%.1f" y1="%s" x2="%.1f" y2="%.1f" '
                     'stroke="rgba(255,255,255,.06)" stroke-dasharray="3 7"/>'
                     % (px(share), top, px(share), py(y_hi)))
        parts.append('<text x="%.1f" y="%.1f" class="axis-label" '
                     'text-anchor="middle">%d%%</text>'
                     % (px(share), py(y_hi) + 20, round(share * 100)))
        share += 0.05 if (x_hi - x_lo) <= 0.45 else 0.1

    for card in plotted:
        cx, cy = px(card["accuracy"]), py(card["cost"])
        color = DOMAIN_COLORS.get(card["domain"], "#888")
        name = human_short.get(card["domain"], card["domain"])
        parts.append(
            '<g class="em-pt" data-name="%s" data-acc="%d" data-cost="%+.1f" '
            'data-eff="%+.2f" data-color="%s">'
            '<circle cx="%.1f" cy="%.1f" r="30" fill="%s" opacity=".14"/>'
            '<circle cx="%.1f" cy="%.1f" r="13" fill="%s" stroke="#0B0F19" '
            'stroke-width="3"/></g>'
            % (name, round(card["accuracy"] * 100), card["cost"],
               card.get("efficiency") or 0, color,
               cx, cy, color, cx, cy, color))

    legend = "".join(
        '<span class="em-leg"><i style="background:%s"></i>%s</span>'
        % (DOMAIN_COLORS.get(c["domain"], "#888"),
           human_short.get(c["domain"], c["domain"]))
        for c in plotted)
    return ('<div class="em-wrap"><svg viewBox="0 0 %s %s" class="effort-map">%s'
            '</svg><div class="em-tip" hidden></div>'
            '<div class="em-legend">%s</div></div>'
            % (width, height, "".join(parts), legend))
