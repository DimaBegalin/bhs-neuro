"""Содержимое батареи: утверждения, карточки, задачи, предметы, профессии.

Файлы JSON лежат рядом. Окну отдаётся только то, что нужно для показа:
ключи ответов пространственных задач остаются в Python.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.scoring.match import Occupation

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


def spatial_key() -> dict[str, str]:
    if not available("spatial"):
        return {}
    return {i["id"]: i["answer"] for i in load("spatial")["items"]}


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
        "subjects": [{"id": s["id"], "text": text(s["text"])} for s in subjects["subjects"]],
        "max_subjects": subjects["max_choice"],
    }
    if available("spatial"):
        spatial = load("spatial")
        data["spatial"] = {
            "instruction": text(spatial["instruction"]),
            "time_limit_s": spatial["time_limit_s"],
            "options": [{"value": o["value"], "label": text(o["label"])} for o in spatial["options"]],
            "items": [{"id": i["id"], "image": i["image"]} for i in spatial["items"]],
        }
    if available("bigfive"):
        bigfive = load("bigfive")
        data["bigfive"] = {
            "scale": bigfive["scale"].get(lang) or bigfive["scale"]["ru"],
            "question": text(bigfive["question"]),
            "items": [{"id": i["id"], "text": text(i["text"])} for i in bigfive["items"]],
        }
    return data


def spatial_rules() -> dict:
    """Шанс угадать и пороги уровней пространственного блока."""
    if not available("spatial"):
        return {}
    data = load("spatial")
    return {k: data[k] for k in ("chance", "strong_share", "weak_share")}
