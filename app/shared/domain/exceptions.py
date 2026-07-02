"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

class DomainError(Exception):
    """Base exception for pure domain rule violations."""


class InvalidValueError(DomainError):
    """Raised when a value object receives invalid data."""


class BusinessRuleViolation(DomainError):
    """Raised when an entity operation violates a business rule."""

