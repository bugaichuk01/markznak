"""extend_emission_order_status_enum

Revision ID: a1b2c3d4e5f6
Revises: f3b2d4e5a6c7
Create Date: 2026-05-29 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f3b2d4e5a6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE emission_order_status ADD VALUE IF NOT EXISTS 'exhausted'")
    op.execute("ALTER TYPE emission_order_status ADD VALUE IF NOT EXISTS 'closed'")


def downgrade() -> None:
    pass  # enum values нельзя удалить в PostgreSQL без пересоздания типа
