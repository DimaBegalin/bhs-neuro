"""Состав батареи экспресс-режима.

С 07.10.2026 в тесте два модуля: интересы по модели Холланда и стиль работы
(Mini-IPIP); по интересам подбираются профессии O*NET. Карточки парами,
задания (вращение, числа, слова) и предметы выключены по решению
пользователя: код и содержимое остались, модуль возвращается одной строкой
в EXPRESS. Минуту фона в начале убрали 06.10.2026.
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
    Module("bigfive", content="bigfive"),
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
