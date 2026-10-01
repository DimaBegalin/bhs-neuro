"""Сходство профиля ученика с профессиями и выбор кластеров (ADR 0004).

Сходство — корреляция Пирсона шести баллов ученика с профилем профессии
из O*NET: сравнивается форма профиля, а не щедрость оценок. Балл кластера —
среднее сходство трёх его ближайших профессий.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.scoring.interests import TYPES

MIN_SIMILARITY = 0.3
TOP_PER_CLUSTER_FOR_SCORE = 3


@dataclass(frozen=True)
class Occupation:
    id: str
    title: dict[str, str]  # язык → название
    cluster: str
    riasec: tuple[float, ...]  # R I A S E C, шкала O*NET 1–7
    onet_code: str = ""


def pearson(a: list[float] | tuple[float, ...], b: list[float] | tuple[float, ...]) -> float | None:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    da = [x - ma for x in a]
    db = [y - mb for y in b]
    va = math.sqrt(sum(x * x for x in da))
    vb = math.sqrt(sum(y * y for y in db))
    if va == 0 or vb == 0:
        return None
    return sum(x * y for x, y in zip(da, db)) / (va * vb)


def rank(vector: list[float], occupations: list[Occupation], clusters: list[str],
         top_clusters: int = 3, per_cluster: int = 5) -> dict:
    """Все кластеры с баллами (для технического отчёта) и тройка лучших."""
    if len(vector) != len(TYPES):
        raise ValueError("профиль должен содержать 6 баллов")
    by_cluster: dict[str, list[dict]] = {c: [] for c in clusters}
    for occ in occupations:
        sim = pearson(vector, occ.riasec)
        if occ.cluster not in by_cluster:
            raise ValueError(f"профессия {occ.id}: неизвестный кластер {occ.cluster}")
        by_cluster[occ.cluster].append({"id": occ.id, "title": occ.title,
                                        "similarity": None if sim is None else round(sim, 3)})
    ranked = []
    for cluster, items in by_cluster.items():
        valid = sorted((i for i in items if i["similarity"] is not None),
                       key=lambda i: -i["similarity"])
        head = valid[:TOP_PER_CLUSTER_FOR_SCORE]
        score = round(sum(i["similarity"] for i in head) / len(head), 3) if head else None
        ranked.append({"cluster": cluster, "score": score,
                       "professions": [i for i in valid if i["similarity"] >= MIN_SIMILARITY][:per_cluster],
                       "all": valid})
    ranked.sort(key=lambda c: (c["score"] is None, -(c["score"] or 0)))
    return {"clusters": ranked, "top": [c["cluster"] for c in ranked[:top_clusters]
                                        if c["score"] is not None]}
