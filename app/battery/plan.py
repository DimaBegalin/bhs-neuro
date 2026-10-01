"""Состав батареи экспресс-режима.

Этап 1 содержит только модуль фона. Интересы, карточки, пространственные
задачи и контекст добавляются на этапе 2 (см. docs/v2/README.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Module:
    id: str
    params: dict = field(default_factory=dict)
    needs_headband: bool = False


EXPRESS: tuple[Module, ...] = (
    Module("background", {"closed_s": 30, "open_s": 30}, needs_headband=True),
)


FAST_SECONDS = 3


def plan_for(with_headband: bool, fast: bool = False) -> list[Module]:
    """Модули сессии. fast укорачивает все отрезки до секунд (разработка, e2e)."""
    modules = [m for m in EXPRESS if with_headband or not m.needs_headband]
    if fast:
        modules = [Module(m.id, {k: (FAST_SECONDS if k.endswith("_s") else v)
                                 for k, v in m.params.items()}, m.needs_headband)
                   for m in modules]
    return modules
