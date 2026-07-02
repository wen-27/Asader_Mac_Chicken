"""SQLAlchemy ORM models for persistence. These classes are storage records, not domain entities."""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database.base import Base


class DeliveryZoneORM(Base):
    __tablename__ = "delivery_zones"
    __table_args__ = (
        CheckConstraint(
            "delivery_price_cop >= 0",
            name="ck_delivery_zones_delivery_price_cop_non_negative",
        ),
        UniqueConstraint("code", name="uq_delivery_zones_code"),
        UniqueConstraint("normalized_neighborhood", name="uq_delivery_zones_normalized_neighborhood"),
        Index("ix_delivery_zones_code", "code"),
        Index("ix_delivery_zones_normalized_neighborhood", "normalized_neighborhood"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    neighborhood: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_neighborhood: Mapped[str] = mapped_column(String(160), nullable=False)
    delivery_price_cop: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

