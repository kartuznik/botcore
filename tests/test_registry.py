"""Registry seam: names map to Router factories."""

from __future__ import annotations

import pytest
from aiogram import Router

from core.registry import ModuleContext, ModuleRegistry, UnknownModuleError
from modules import build_default_registry

CONTEXT = ModuleContext(enabled_modules=("demo",))


def make_factory(name: str) -> object:
    def factory(context: ModuleContext) -> Router:
        return Router(name=name)

    return factory


def test_registered_module_produces_router() -> None:
    registry = ModuleRegistry()
    registry.register("Demo", make_factory("demo"))  # type: ignore[arg-type]

    router = registry.create("demo", CONTEXT)

    assert "demo" in registry
    assert registry.available == ("demo",)
    assert isinstance(router, Router)
    assert router.name == "demo"


def test_duplicate_registration_is_rejected() -> None:
    registry = ModuleRegistry()
    registry.register("demo", make_factory("demo"))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="already registered"):
        registry.register("demo", make_factory("demo"))  # type: ignore[arg-type]


def test_unknown_module_raises_with_available_names() -> None:
    registry = ModuleRegistry()
    registry.register("demo", make_factory("demo"))  # type: ignore[arg-type]

    with pytest.raises(UnknownModuleError) as error_info:
        registry.create("missing", CONTEXT)

    assert error_info.value.available == ("demo",)


def test_default_registry_contains_health() -> None:
    registry = build_default_registry()

    assert "health" in registry
    assert isinstance(registry.create("health", ModuleContext(("health",))), Router)
