# -*- coding: utf-8 -*-
"""Финальная сборка визита: профиль, побочные каналы, пульс, дашборд.

Запуск: finalize_session.py <session_id> [подпись] [side_channels.jsonl]
"""
import json
import sys

from analyzer.report_data import build_report_data
from report.build_html import build
from tools.side_decode import load, ppg_series, pulse_from_ppg, resist_series

session_id = sys.argv[1]
caption = sys.argv[2] if len(sys.argv) > 2 else ""
side_path = sys.argv[3] if len(sys.argv) > 3 else "data/side_channels.jsonl"

profile = json.load(open("data/%s.profile.json" % session_id, encoding="utf-8"))
report = build_report_data("data/%s.npz" % session_id,
                           "data/%s.events.json" % session_id, profile)

try:
    channels = load(side_path)
    wave = ppg_series(channels.get("08", []))
    pulse = pulse_from_ppg(wave)
    report["pulse"] = pulse
    resist = resist_series(channels.get("05", []))
    if resist:
        report["resist_last"] = resist[-1]
    print("пульс:", "медиана %d уд/мин (%d..%d)" % (pulse["bpm_median"],
          pulse["bpm_min"], pulse["bpm_max"]) if pulse.get("ok")
          else pulse.get("reason"))
except FileNotFoundError:
    print("побочных каналов нет, дашборд будет без пульса")

json.dump(report, open("data/%s.report.json" % session_id, "w", encoding="utf-8"),
          ensure_ascii=False)
out = build(report, "web/result.html", caption)
print("дашборд:", out)
print("итог: альфа-пик", report["iaf"], "| нейро-слой:", profile["has_eeg"])
