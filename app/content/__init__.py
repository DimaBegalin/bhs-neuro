"""Содержимое батареи: утверждения, карточки, задачи, предметы, профессии.

Файлы JSON лежат рядом. Окну отдаётся только то, что нужно для показа:
ключи ответов заданий остаются в Python.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.scoring.match import Occupation
from app.scoring.tasks import BLOCKS

CONTENT_DIR = Path(__file__).resolve().parent


def available(name: str) -> bool:
    return (CONTENT_DIR / f"{name}.json").exists()


@lru_cache(maxsize=None)
def load(name: str):
    return json.loads((CONTENT_DIR / f"{name}.json").read_text(encoding="utf-8"))


def occupations() -> list[Occupation]:
    return [Occupation(o["id"], o["title"], o["cluster"], tuple(o["riasec"]), o.get("onet_code", ""))
            for o in load("occupations")["occupations"]]


def clusters() -> list[dict]:
    return load("occupations")["clusters"]


def card_types() -> dict[str, str]:
    return {c["id"]: c["type"] for c in load("cards")["cards"]}


def task_key(block: str) -> dict:
    """id задания → верный ответ: значение варианта у вращения, номер варианта у остальных."""
    if not available(block):
        return {}
    return {i["id"]: i["answer"] for i in load(block)["items"]}


def for_window(lang: str) -> dict:
    """Всё для показа на языке ученика, без ключей ответов."""
    def text(obj: dict) -> str:
        return obj.get(lang) or obj["ru"]

    interests = load("interests")
    cards = load("cards")
    subjects = load("subjects")
    data = {
        "interests": {
            "scale": interests["scale"].get(lang) or interests["scale"]["ru"],
            "items": [{"id": i["id"], "text": text(i["text"])} for i in interests["items"]],
        },
        "cards": [{"id": c["id"], "image": c["image"], "text": text(c["text"])} for c in cards["cards"]],
        "card_pairs": [list(pair) for pair in cards["pairs"]],
        "subjects": [{"id": s["id"], "text": text(s["text"])} for s in subjects["subjects"]],
        "max_subjects": subjects["max_choice"],
    }
    for block in BLOCKS:
        if available(block):
            data[block] = _task_block(load(block), text)
    if available("bigfive"):
        bigfive = load("bigfive")
        data["bigfive"] = {
            "scale": bigfive["scale"].get(lang) or bigfive["scale"]["ru"],
            "question": text(bigfive["question"]),
            "items": [{"id": i["id"], "text": text(i["text"])} for i in bigfive["items"]],
        }
    return data


def _task_block(data: dict, text) -> dict:
    """Блок заданий для окна: картинка или текст, варианты общие (вращение) или свои у задания."""
    def options(raw) -> list[dict]:
        labels = text(raw) if isinstance(raw, dict) else raw
        return [{"value": i, "label": label} for i, label in enumerate(labels)]

    items = []
    for item in data["items"]:
        shown = {"id": item["id"]}
        if "image" in item:
            shown["image"] = item["image"]
        if "text" in item:
            shown["text"] = text(item["text"])
        if "options" in item:
            shown["options"] = options(item["options"])
        items.append(shown)
    block = {"title": text(data["title"]), "instruction": text(data["instruction"]),
             "time_limit_s": data["time_limit_s"], "items": items}
    if "options" in data:
        block["options"] = [{"value": o["value"], "label": text(o["label"])} for o in data["options"]]
    return block


def task_rules(block: str) -> dict:
    """Шанс угадать и пороги уровней блока заданий."""
    if not available(block):
        return {}
    data = load(block)
    return {k: data[k] for k in ("chance", "strong_share", "weak_share")}
