# -*- coding: utf-8 -*-
"""HTML-версия отчёта для родителя: уходит в облако и открывается в веб-панели."""
from __future__ import annotations

from html import escape

CSS = """body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:760px;margin:24px auto;
padding:0 16px;color:#16171a;background:#fff;line-height:1.5}h1{font-size:26px;margin:4px 0}
h2{color:#8b3fc4;font-size:19px;margin-top:28px}h3{font-size:15px;margin:14px 0 4px}.muted{color:#6b6f78}
.bar{display:grid;grid-template-columns:200px 1fr 36px;gap:10px;align-items:center;margin:6px 0}
.track{background:#f0eef4;height:10px;border-radius:5px}.fill{background:#8b3fc4;height:10px;border-radius:5px}
.badge{display:inline-block;background:#6b6f78;color:#fff;font-size:12px;padding:3px 8px;border-radius:6px}
.small{font-size:11px;color:#6b6f78}"""


def _bar(name: str, value) -> str:
    v = max(0.0, min(100.0, float(value or 0)))
    return (f'<div class="bar"><span>{escape(name)}</span><div class="track">'
            f'<div class="fill" style="width:{v:.0f}%"></div></div><b>{v:.0f}</b></div>')


def render_parent_html(model: dict) -> str:
    t = model["t"]
    st = model["student"]
    parts = [f"<!doctype html><html lang='{model['lang']}'><head><meta charset='utf-8'>",
             f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(st['name'])}</title>",
             f"<style>{CSS}</style></head><body>",
             f"<div class='muted'>{escape(t['report_title'])}</div><h1>{escape(t['parent_subtitle'])}</h1>",
             f"<p>{escape(st['name'])} · {escape(str(st['grade']))} {escape(t['grade'])} · {escape(model['date'])}</p>",
             f"<h2>{escape(t['summary_title'])}</h2>"]
    for i, item in enumerate(model["summary"], start=1):
        parts.append(f"<h3>{i}. {escape(item['title'])}</h3>")
        if "steps" in item:
            parts.append("<ul>" + "".join(f"<li>{escape(x)}</li>" for x in item["steps"]) + "</ul>")
        else:
            parts.append(f"<p>{escape(item['text'])}</p>")
    parts.append(f"<h2>{escape(t['profile_title'])}</h2><p class='muted'>{escape(t['profile_note'])}</p>")
    parts += [_bar(r["name"], r["score"]) for r in model["interests"]["types"]]
    parts.append(f"<h2>{escape(t['clusters_title'])}</h2>")
    if model["clusters"]:
        for i, c in enumerate(model["clusters"], start=1):
            parts.append(f"<h3>{i}. {escape(c['title'])}</h3><p>{escape(', '.join(c['professions']) or '—')}</p>")
    else:
        parts.append(f"<p>{escape(t['no_clusters'])}</p>")
    if model.get("style"):
        parts.append(f"<h2>{escape(t['style_title'])}</h2><p class='muted'>{escape(t['style_note'])}</p>")
        parts += [_bar(r["name"], r["score"]) for r in model["style"]]
    parts.append(f"<h2>{escape(t['neuro_title'])}</h2>")
    if model.get("neuro"):
        parts.append(f"<span class='badge'>{escape(model['neuro']['badge'])}</span><p>{escape(model['neuro']['attention'])}</p>")
    else:
        parts.append(f"<p class='muted'>{escape(t['neuro_none'])}</p>")
    parts.append(f"<h2>{escape(t['how_title'])}</h2><ul>" + "".join(f"<li>{escape(x)}</li>" for x in t["how_items"]) + "</ul>")
    parts.append(f"<p class='small'>{escape(t['methods'])}</p><p class='small'>{escape(t['onet'])}</p></body></html>")
    return "".join(parts)
