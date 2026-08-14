"""PDF для родителя: вертикальный формат под телефон, 100x200 мм.

Кириллица требует TrueType-шрифта, стандартные шрифты reportlab её не несут.
Берём системный Arial macOS, при его отсутствии падаем на Vera из reportlab
и честно пишем об этом в лог, чтобы поломанный документ не ушёл семье.
"""
import os

from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from analyzer.wording import describe_domain, describe_profile

PAGE = (100 * mm, 200 * mm)
MARGIN = 9 * mm
INK = HexColor("#16181d")
MUTED = HexColor("#6b7079")
LEVEL_COLORS = {"strong": HexColor("#3f9f2c"), "solid": HexColor("#3a76c4"),
                "costly": HexColor("#d1494f")}
FONT_CANDIDATES = [
    ("BHS", "/System/Library/Fonts/Supplemental/Arial.ttf",
     "BHS-Bold", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("BHS", "/Library/Fonts/Arial.ttf", "BHS-Bold", "/Library/Fonts/Arial Bold.ttf"),
]


def register_fonts() -> tuple[str, str]:
    for regular_name, regular_path, bold_name, bold_path in FONT_CANDIDATES:
        if os.path.exists(regular_path) and os.path.exists(bold_path):
            pdfmetrics.registerFont(TTFont(regular_name, regular_path))
            pdfmetrics.registerFont(TTFont(bold_name, bold_path))
            return regular_name, bold_name
    print("шрифт с кириллицей не найден, документ выйдет нечитаемым")
    return "Helvetica", "Helvetica-Bold"


def _wrap(pdf, text: str, font: str, size: float, width: float) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if pdfmetrics.stringWidth(candidate, font, size) > width:
            if current:
                lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def build_report(profile: dict, out_path: str, lang: str = "ru") -> str:
    regular, bold = register_fonts()
    summary = describe_profile(profile, lang)
    width, height = PAGE
    text_width = width - MARGIN * 2
    pdf = canvas.Canvas(out_path, pagesize=PAGE)
    y = height - MARGIN - 5 * mm

    def line(text, font, size, color=INK, gap=4.6):
        nonlocal y
        pdf.setFont(font, size)
        pdf.setFillColor(color)
        for chunk in _wrap(pdf, text, font, size, text_width):
            pdf.drawString(MARGIN, y, chunk)
            y -= gap * mm

    line("Профориентация Beta High School", bold, 12)
    y -= 2 * mm
    line(summary["headline"], regular, 8, MUTED)
    y -= 3 * mm

    cards = sorted(profile["domains"],
                   key=lambda c: -(c["efficiency"] if c["efficiency"] is not None else -99))
    for card in cards:
        text = describe_domain(card, lang)
        pdf.setFillColor(LEVEL_COLORS[text["level"]])
        pdf.circle(MARGIN + 1.2 * mm, y + 1.1 * mm, 1.2 * mm, stroke=0, fill=1)
        pdf.setFont(bold, 10)
        pdf.setFillColor(INK)
        pdf.drawString(MARGIN + 4.5 * mm, y, text["title"])
        y -= 5 * mm
        line(text["verdict"], regular, 8, LEVEL_COLORS[text["level"]])
        line(text["detail"], regular, 8, MUTED)
        y -= 2.5 * mm

    if summary["attention"]:
        line(summary["attention"], regular, 8, INK)
        y -= 2 * mm

    line("Куда это ведёт: " + summary["directions"], regular, 8, INK)
    y -= 3 * mm
    line(summary["disclaimer"], regular, 7, MUTED, gap=3.9)

    pdf.setFont(regular, 6)
    pdf.setFillColor(MUTED)
    pdf.drawString(MARGIN, MARGIN, f"методика версии {profile['method_version']}")
    pdf.showPage()
    pdf.save()
    return out_path


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("profile_json")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    data = json.load(open(args.profile_json, encoding="utf-8"))
    print(build_report(data, args.out, data.get("lang", "ru")))
