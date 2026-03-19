"""Enemy type registry/factory used by the server spawner."""

from __future__ import annotations

from collections.abc import Callable

from entities.enemy_base import EnemyBase
from entities.mimic import Mimic
from entities.siren import Siren
from entities.weeping_angel import WeepingAngel


class EnemyRegistry:
    """Stores enemy constructors keyed by logical enemy type."""

    _factories: dict[str, Callable[..., EnemyBase]] = {}

    @classmethod
    def register(cls, enemy_type: str, factory: Callable[..., EnemyBase]) -> None:
        cls._factories[enemy_type] = factory

    @classmethod
    def create(cls, enemy_type: str, **kwargs) -> EnemyBase:
        if enemy_type not in cls._factories:
            raise ValueError(f"Enemy type '{enemy_type}' is not registered")
        return cls._factories[enemy_type](**kwargs)

    @classmethod
    def registered_types(cls) -> list[str]:
        return sorted(cls._factories.keys())


EnemyRegistry.register("mimic", Mimic)
EnemyRegistry.register("weeping_angel", WeepingAngel)
EnemyRegistry.register("siren", Siren)
