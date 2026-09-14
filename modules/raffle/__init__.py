"""Raffle module: giveaways with subscription conditions, draws and a demo mode."""

from __future__ import annotations

from modules.raffle.handlers import MODULE_NAME, create_router

__all__ = ["MODULE_NAME", "create_router"]
