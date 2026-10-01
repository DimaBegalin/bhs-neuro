# -*- coding: utf-8 -*-
"""PDF для родителя и технический PDF для менеджера (reportlab, без браузера)."""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

FONT_DIR = Path(__file__).resolve().parent / "fonts"
ACCENT = colors.HexColor("#8b3fc4")
MUTED = colors.HexColor("#6b6f78")
LINE = colors.HexColor("#e3e4e8")
BAR_BG = colors.HexColor("#f0eef4")

_registered = False


def _fonts() -> None:
    global _registered
    if _registered:
        return
    pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold")
    _registered = True


def _styles() -> dict[str, ParagraphStyle]:
    _fonts()
    base = ParagraphStyle("base", fontName="DejaVu", fontSize=10, leading=14)
    return {
        "base": base,
        "small": ParagraphStyle("small", parent=base, fontSize=7.5, leading=10, textColor=MUTED),
        "muted": ParagraphStyle("muted", parent=base, textColor=MUTED),
        "h1": ParagraphStyle("h1", parent=base, fontName="DejaVu-Bold", fontSize=18, leading=22),
        "h2": ParagraphStyle("h2", parent=base, fontName="DejaVu-Bold", fontSize=13, leading=17,
                             spaceBefore=10, spaceAfter=4, textColor=ACCENT),
        "h3": ParagraphStyle("h3", parent=base, fontName="DejaVu-Bold", fontSize=10.5, leading=14,
                             spaceBefore=4),
        "badge": ParagraphStyle("badge", parent=base, fontSize=8.5, textColor=colors.white,
                                backColor=MUTED, borderPadding=(3, 5, 3, 5)),
    }


def P(text: str, style) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _bars(rows: list[tuple[str, float]], width: float = 170 * mm, label_w: float = 52 * mm) -> Drawing:
    """Горизонтальные полосы 0–100 с подписью и значением."""
    _fonts()
    row_h = 15
    d = Drawing(width, row_h * len(rows) + 4)
    bar_w = width - label_w - 14 * mm
    for i, (label, value) in enumerate(rows):
        y = d.height - (i + 1) * row_h
        d.add(String(0, y + 4, label, fontName="DejaVu", fontSize=9))
        d.add(Rect(label_w, y + 2, bar_w, 9, fillColor=BAR_BG, strokeColor=None))
        v = max(0.0, min(100.0, float(value or 0)))
        d.add(Rect(label_w, y + 2, bar_w * v / 100, 9, fillColor=ACCENT, strokeColor=None))
        d.add(String(label_w + bar_w + 4, y + 4, f"{v:.0f}", fontName="DejaVu", fontSize=9))
    return d


def _header(model: dict, subtitle_key: str, s: dict) -> list:
    t = model["t"]
    st = model["student"]
    return [
        P(t["report_title"], s["muted"]),
        P(t[subtitle_key], s["h1"]),
        Spacer(1, 2 * mm),
        P(f"{st['name']} · {st['grade']} {t['grade']} · {model['date']}", s["base"]),
        Spacer(1, 4 * mm),
    ]


def _summary(model: dict, s: dict) -> list:
    out = [P(model["t"]["summary_title"], s["h2"])]
    for i, item in enumerate(model["summary"], start=1):
        block = [P(f"{i}. {item['title']}", s["h3"])]
        if "steps" in item:
            block += [P(f"• {step}", s["base"]) for step in item["steps"]]
        else:
            block.append(P(item["text"], s["base"]))
        out.append(KeepTogether(block))
    return out


def _comment(model: dict, s: dict) -> list:
    """Комментарий профориентолога: тот же стиль раздела, переносы строк сохраняются."""
    comment = model.get("comment")
    if not comment:
        return []
    body = "<br/>".join(escape(line) for line in comment["text"].splitlines())
    sign = " · ".join(x for x in (comment.get("author"), (comment.get("updated_at") or "")[:10]) if x)
    out = [P(model["t"]["comment_title"], s["h2"]), Paragraph(body, s["base"])]
    if sign:
        out.append(P(sign, s["muted"]))
    return [KeepTogether(out)]


def _footer_blocks(model: dict, s: dict) -> list:
    """«Как читать», затем комментарий профориентолога, внизу мелким — методики и атрибуция."""
    t = model["t"]
    out = [P(t["how_title"], s["h2"])]
    out += [P(f"• {item}", s["base"]) for item in t["how_items"]]
    out += _comment(model, s)
    out += [Spacer(1, 4 * mm), P(t["methods"], s["small"]), Spacer(1, 2 * mm), P(t["onet"], s["small"])]
    return out


def render_parent(model: dict, path: Path) -> Path:
    s = _styles()
    t = model["t"]
    story = _header(model, "parent_subtitle", s) + _summary(model, s)

    story += [P(t["profile_title"], s["h2"]), P(t["profile_note"], s["muted"]), Spacer(1, 2 * mm)]
    story.append(_bars([(row["name"], row["score"]) for row in model["interests"]["types"]]))
    story += [Paragraph(f"<b>{escape(r['name'])}</b> — {escape(r['desc'])}", s["small"])
              for r in model["interests"]["types"]]

    story.append(P(t["clusters_title"], s["h2"]))
    if model["clusters"]:
        for i, c in enumerate(model["clusters"], start=1):
            story.append(P(f"{i}. {c['title']}", s["h3"]))
            story.append(P(", ".join(c["professions"]) or "—", s["base"]))
    else:
        story.append(P(t["no_clusters"], s["base"]))

    spatial = model.get("spatial") or {}
    if spatial.get("total"):
        story += [P(t["spatial_title"], s["h2"]),
                  P(f"{spatial['correct']} / {spatial['total']}", s["base"])]
    if model.get("style"):
        story += [P(t["style_title"], s["h2"]), P(t["style_note"], s["muted"]), Spacer(1, 2 * mm),
                  _bars([(row["name"], row["score"]) for row in model["style"]])]

    story.append(P(t["neuro_title"], s["h2"]))
    if model.get("neuro"):
        story += [P(model["neuro"]["badge"], s["badge"]), Spacer(1, 3 * mm),
                  P(model["neuro"]["attention"], s["base"])]
    else:
        story.append(P(t["neuro_none"], s["muted"]))

    story += _footer_blocks(model, s)
    _build(path, story)
    return path


def _table(rows: list[list], s: dict, widths=None) -> Table:
    data = [[P(c, s["small"] if r else s["h3"]) for c in row] for r, row in enumerate(rows)]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return table


def render_manager(model: dict, path: Path) -> Path:
    """Технический отчёт (CONTEXT.md): баллы, флаги, качество сигнала, карточки."""
    s = _styles()
    r = model["result"]
    story = _header(model, "manager_subtitle", s) + _summary(model, s)

    story.append(P("Интересы RIASEC", s["h2"]))
    i = r["interests"]
    story.append(_table([["Тип", "Балл 0–100", "Ответов"]] +
                        [[k, f"{i['scores'][k]:.0f}", f"{i['answered'][k]}/{i['expected'][k]}"] for k in i["scores"]], s))
    story.append(P(f"Выраженность: {i['level']} (разброс {i['spread']:.0f})", s["base"]))

    story.append(P("Все кластеры", s["h2"]))
    story.append(_table([["Кластер", "Балл", "Профессии со сходством ≥ 0,3"]] +
                        [[c["title"]["ru"], "—" if c["score"] is None else f"{c['score']:.2f}",
                          ", ".join(f"{p['title']['ru']} ({p['similarity']:.2f})" for p in c["professions"])]
                         for c in r["recommendation"]["clusters"]], s, [45 * mm, 15 * mm, 110 * mm]))

    sp = r.get("spatial") or {}
    story.append(P("Задачи на вращение", s["h2"]))
    story.append(P(f"Верно {sp.get('correct')} из {sp.get('total')}, тайм-аутов {sp.get('timeouts')}, "
                   f"медиана времени {sp.get('median_rt_ms')} мс, уровень {sp.get('level')}, шанс {sp.get('chance')}", s["base"]))

    ws = r.get("work_style")
    if ws:
        story.append(P("Стиль работы (Mini-IPIP)", s["h2"]))
        story.append(_table([["Черта", "Балл"]] + [[k, "—" if v is None else f"{v:.0f}"] for k, v in ws["scores"].items()], s))

    story.append(P("Достоверность", s["h2"]))
    story.append(P("Флаги: " + (", ".join(r["flags"]) or "нет"), s["base"]))
    story.append(P("Расхождения с карточками: " + (", ".join(f"{d['type']} ({d['questionnaire']}/{d['cards']})" for d in r["discrepancies"]) or "нет"), s["base"]))

    mon = r.get("monitoring")
    story.append(P("Нейромониторинг", s["h2"]))
    if not mon:
        story.append(P("Без ободка.", s["base"]))
    else:
        bg = mon.get("background") or {}
        story.append(P(f"Фон: альфа-пик {bg.get('iaf_hz')}, реакция альфы {bg.get('alpha_reactivity')}, "
                       f"полоса {bg.get('band_hz')}, внимание к карточкам {'показано' if bg.get('reactive') else 'скрыто'}", s["base"]))
        story.append(P("Качество по модулям: " + ", ".join(f"{k} {v['quality']}" for k, v in (mon.get("modules") or {}).items()), s["base"]))
        st = mon.get("state") or {}
        story.append(P(f"Движения: {st.get('movement')}; θ/α к концу: {st.get('theta_alpha_change')}; усталость: {st.get('fatigue_signs')}", s["base"]))
        cards = (mon.get("cards") or {}).get("items") or []
        liked = {c["card"]: c.get("liked") for c in r.get("cards", [])}
        if cards:
            story.append(_table([["Карточка", "Тип", "Оценка", "Альфа, %", "Ранг внимания", "Чистых эпох"]] +
                                [[c["card"], c["type"], {True: "интересно", False: "не очень"}.get(liked.get(c["card"]), "—"),
                                  "—" if c["alpha_change_pct"] is None else f"{c['alpha_change_pct']:.0f}",
                                  c.get("attention_rank", "—"), c["clean_epochs"]] for c in cards], s))
    story += _comment(model, s)
    story += [Spacer(1, 4 * mm), P(model["t"]["methods"], s["small"]), P(model["t"]["onet"], s["small"])]
    _build(path, story)
    return path


def _build(path: Path, story: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title="Профориентация BHS", author="BHS")
    doc.build(story)
