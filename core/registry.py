"""Module registry: module name -> Router factory."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from aiogram import Router


@dataclass(frozen=True, slots=True)
class ModuleContext:
    """Read-only data a module may need while building its Router."""

    enabled_modules: tuple[str, ...]


RouterFactory = Callable[[ModuleContext], Router]


class UnknownModuleError(LookupError):
    """Raised when a requested module is not present in the registry."""

    def __init__(self, name: str, available: Iterable[str]) -> None:
        self.name = name
        self.available = tuple(available)
        known = ", ".join(self.available) or "<empty registry>"
        super().__init__(f"Unknown module {name!r}. Available modules: {known}")


class ModuleRegistry:
    """Maps module names to factories so the app can enable them from config."""

    def __init__(self) -> None:
        self._factories: dict[str, RouterFactory] = {}

    def register(self, name: str, factory: RouterFactory) -> None:
        key = self._normalize(name)
        if not key:
            raise ValueError("Module name must not be empty")
        if key in self._factories:
            raise ValueError(f"Module {key!r} is already registered")
        self._factories[key] = factory

    def create(self, name: str, context: ModuleContext) -> Router:
        key = self._normalize(name)
        factory = self._factories.get(key)
        if factory is None:
            raise UnknownModuleError(key, self.available)
        return factory(context)

    def create_all(self, names: Iterable[str], context: ModuleContext) -> tuple[Router, ...]:
        return tuple(self.create(name, context) for name in names)

    @property
    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self._normalize(name) in self._factories

    def __len__(self) -> int:
        return len(self._factories)

    @staticmethod
    def _normalize(name: str) -> str:
        return name.strip().lower()
