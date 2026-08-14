# -*- coding: utf-8 -*-
"""Импорт поминутного экспорта штатного приложения.

Приложение умеет выгружать CSV со своими метриками: время, cognitive score,
focus, chill, stress, self-control, anger, relaxation index, concentration
index, fatigue score, reverse fatigue, alpha gravity, heart rate. Это тот же
прибор и те же четыре канала, просто их закрытые формулы поверх. Импортёр
даёт положить их слой рядом с нашим: для сверки и для разбора.
"""
import csv
from datetime import datetime


def load_mind_csv(path: str) -> list:
    rows = []
    with open(path, encoding="utf-8-sig") as fh:
        for raw in csv.DictReader(fh):
            try:
                moment = datetime.strptime(raw["time"].strip(), "%Y-%m-%d %H:%M")
            except (ValueError, KeyError):
                continue
            def num(key):
                try:
                    return float(raw.get(key, "").replace(",", "."))
                except (ValueError, AttributeError):
                    return None
            rows.append({
                "time": moment,
                "cognitive": num("cognitive score"),
                "focus": num("focus"),
                "chill": num("chill"),
                "stress": num("stress"),
                "self_control": num("self-control"),
                "anger": num("anger"),
                "relaxation_index": num("relaxation index"),
                "concentration_index": num("concentration index"),
                "fatigue": num("fatigue score"),
                "alpha_gravity": num("alpha gravity"),
                "heart_rate": num("heart rate"),
            })
    return rows
