"""Feature modules. Each module exposes a Router factory registered here."""

from __future__ import annotations

from core.registry import ModuleRegistry
from modules import health, raffle


def build_default_registry() -> ModuleRegistry:
    """Registry with every module shipped in this repository."""
    registry = ModuleRegistry()
    registry.register(health.MODULE_NAME, health.create_router)
    registry.register(raffle.MODULE_NAME, raffle.create_router)
    return registry


__all__ = ["build_default_registry"]
