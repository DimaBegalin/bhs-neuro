"""Блоки в логике часов: кольца заполненности и плитки показателей.

Смысл колец тот же, что у колец активности: показываем не абсолютное число,
которое ничего не говорит родителю, а насколько заполнена личная норма.
"""
import math


def watch_rings(values, colors, labels, size=190):
    circles, marks = [], []
    for index, (value, color, label) in enumerate(zip(values, colors, labels)):
        radius = size / 2 - 14 - index * 26
        circumference = 2 * math.pi * radius
        filled = max(0.03, min(1.0, value)) * circumference
        circles.append(
            f'<circle cx="{size/2}" cy="{size/2}" r="{radius:.1f}" fill="none" '
            f'stroke="{color}" stroke-opacity=".18" stroke-width="20"/>'
            f'<circle cx="{size/2}" cy="{size/2}" r="{radius:.1f}" fill="none" '
            f'stroke="{color}" stroke-width="20" stroke-linecap="round" '
            f'stroke-dasharray="{filled:.1f} {circumference:.1f}" '
            f'transform="rotate(-90 {size/2} {size/2})"/>')
        marks.append(f'<span class="ring-leg"><i style="background:{color}"></i>'
                     f'{label}<b>{value*100:.0f}%</b></span>')
    return (f'<svg viewBox="0 0 {size} {size}" class="rings">{"".join(circles)}</svg>'
            f'<div class="ring-legend">{"".join(marks)}</div>')


def _spark(points, color, width=96, height=28):
    if not points or len(points) < 2:
        return ""
    low, high = min(points), max(points)
    span = (high - low) or 1
    step = width / (len(points) - 1)
    coords = " ".join(f"{i*step:.1f},{height - (v-low)/span*(height-6) - 3:.1f}"
                      for i, v in enumerate(points))
    return (f'<svg viewBox="0 0 {width} {height}" class="tile-spark">'
            f'<polyline points="{coords}" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linecap="round"/></svg>')


def watch_tiles(tiles):
    """Плитки показателей: название, число, короткий тренд, микрографик."""
    cells = []
    for title, value, unit, trend, color, points in tiles:
        cells.append(
            f'<div class="tile"><div class="tile-title" style="color:{color}">{title}</div>'
            f'<div class="tile-value">{value}<small>{unit}</small></div>'
            f'<div class="tile-trend">{trend}</div>{_spark(points, color)}</div>')
    return f'<div class="tiles">{"".join(cells)}</div>'
