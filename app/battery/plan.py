"""Состав батареи экспресс-режима.

Порядок из документа «Методология 2.0»: интересы (пока ученик не устал),
карточки парами, задания (вращение, числа, слова), стиль работы (Mini-IPIP),
предметы. Минуту фона в начале убрали 06.10.2026: тест был слишком долгим.
Задания на числа и слова добавлены тогда же: способности проверяются делом,
а не вопросами.
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
    Module("interests"),
    Module("cards"),
    Module("spatial", content="spatial"),
    Module("numeric", content="numeric"),
    Module("verbal", content="verbal"),
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
