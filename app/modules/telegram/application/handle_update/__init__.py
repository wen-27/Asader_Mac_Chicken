"""Package marker. Keep it light so importing the package does not trigger infrastructure side effects."""

from __future__ import annotations

from app.modules.telegram.application.handle_update.use_case import HandleTelegramUpdateUseCase

__all__ = ["HandleTelegramUpdateUseCase"]

