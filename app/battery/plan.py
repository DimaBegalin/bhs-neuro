"""Состав батареи экспресс-режима.

Порядок из документа «Методология 2.0»: фон, интересы (пока ученик не
устал), карточки, пространственные задачи, стиль работы (Mini-IPIP), предметы. Фон нужен только
с ободком; карточки остаются и без него — их оценки тоже самоотчёт.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Module:
    id: str
    params: dict = field(default_factory=dict)
    needs_headband: bool = False
    content: str | None = None  # модуль показывается, только если его содержимое на месте


EXPRESS: tuple[Module, ...] = (
    Module("background", {"closed_s": 30, "open_s": 30}, needs_headband=True),
    Module("interests"),
    Module("cards", {"show_s": 10, "rest_s": 1.5}),
    Module("spatial", content="spatial"),
    Module("bigfive", content="bigfive"),
    Module("context"),
)


FAST_SECONDS = 3


def plan_for(with_headband: bool, fast: bool = False) -> list[Module]:
    """Модули сессии. fast укорачивает все отрезки до секунд (разработка, e2e)."""
    from app import content
    modules = [m for m in EXPRESS if (with_headband or not m.needs_headband)
               and (m.content is None or content.available(m.content))]
    if fast:
        modules = [Module(m.id, {k: (min(v, FAST_SECONDS) if k.endswith("_s") else v)
                                 for k, v in m.params.items()}, m.needs_headband, m.content)
                   for m in modules]
    return modules
