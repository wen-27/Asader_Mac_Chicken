"""Remove public bottle and generic icopor add-ons."""

from __future__ import annotations

from alembic import op


revision: str = "20260719_0012"
down_revision: str | None = "20260713_0011"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM product_aliases
        WHERE product_id IN (
            SELECT id FROM products WHERE code IN ('BOTELLA_VIDRIO', 'ICOPOR')
        )
        """
    )
    op.execute("DELETE FROM products WHERE code IN ('BOTELLA_VIDRIO', 'ICOPOR')")


def downgrade() -> None:
    op.execute(
        """
        INSERT INTO products (
            code, name, category, price_cop, is_active, is_available,
            restricted_to, requires_age_verification, created_at, updated_at
        )
        VALUES
            ('BOTELLA_VIDRIO', 'Botella Vidrio', 'ADICIONALES', 200, TRUE, TRUE, 'NONE', FALSE, now(), now()),
            ('ICOPOR', 'Icopores', 'ADICIONALES', 900, TRUE, TRUE, 'NONE', FALSE, now(), now())
        ON CONFLICT (code) DO NOTHING
        """
    )
