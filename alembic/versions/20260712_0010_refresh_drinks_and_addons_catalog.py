"""Refresh drinks and addons catalog.

Revision ID: 20260712_0010
Revises: 20260712_0009
Create Date: 2026-07-12 22:45:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260712_0010"
down_revision: str | None = "20260712_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


REMOVED_PRODUCT_CODES = (
    "GASEOSA",
    "LATA_GASEOSA",
    "POSTOBON_25",
    "TRES_LITROS",
    "JUGO_LUBY",
    "GATORADE",
    "JUGO_HIT_LITRO_TETRA",
    "COLA_POLA",
)


def upgrade() -> None:
    codes_sql = ", ".join(f"'{code}'" for code in REMOVED_PRODUCT_CODES)
    op.execute(f"DELETE FROM product_aliases WHERE product_id IN (SELECT id FROM products WHERE code IN ({codes_sql}))")
    op.execute(f"DELETE FROM products WHERE code IN ({codes_sql})")
    op.execute(
        """
        INSERT INTO products (
            code,
            name,
            category,
            price_cop,
            is_active,
            is_available,
            restricted_to,
            requires_age_verification,
            created_at,
            updated_at
        )
        VALUES
            ('GASEOSA_25', 'Gaseosa 2.5 L', 'BEBIDAS', 8500, TRUE, TRUE, 'NONE', FALSE, now(), now()),
            ('JUGO_HIT_PERSONAL', 'Jugos Hit personal', 'BEBIDAS', 3000, TRUE, TRUE, 'NONE', FALSE, now(), now()),
            ('JUGO_HIT_LITRO', 'Jugo Hit Litro', 'BEBIDAS', 6000, TRUE, TRUE, 'NONE', FALSE, now(), now()),
            ('YUCA_FRITA', 'Yuca frita', 'ADICIONALES', 5000, TRUE, TRUE, 'NONE', FALSE, now(), now())
        ON CONFLICT (code)
        DO UPDATE SET
            name = EXCLUDED.name,
            category = EXCLUDED.category,
            price_cop = EXCLUDED.price_cop,
            is_active = EXCLUDED.is_active,
            is_available = EXCLUDED.is_available,
            restricted_to = EXCLUDED.restricted_to,
            requires_age_verification = EXCLUDED.requires_age_verification,
            updated_at = now()
        """
    )
    op.execute(
        """
        UPDATE products
        SET
            name = 'Coca-Cola personal 400 ml',
            price_cop = 3500,
            is_active = TRUE,
            is_available = TRUE,
            updated_at = now()
        WHERE code = 'PERSONAL_400'
        """
    )
    op.execute(
        """
        UPDATE products
        SET
            name = 'Agua botella',
            price_cop = 2600,
            is_active = TRUE,
            is_available = TRUE,
            updated_at = now()
        WHERE code = 'AGUA_BOTELLA'
        """
    )
    op.execute("UPDATE products SET name = 'Papa o yuca salada' WHERE code = 'PAPA_SALADA'")
    op.execute("UPDATE stock_controls SET label = 'Papa o yuca salada' WHERE code = 'PAPA_SALADA'")


def downgrade() -> None:
    op.execute("UPDATE products SET name = 'Papa Salada' WHERE code = 'PAPA_SALADA'")
    op.execute("UPDATE stock_controls SET label = 'Papa Salada' WHERE code = 'PAPA_SALADA'")
