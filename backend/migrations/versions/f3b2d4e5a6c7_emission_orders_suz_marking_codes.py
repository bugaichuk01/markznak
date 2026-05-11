"""Emission orders: cached marking codes from SUZ list payload.

Revision ID: f3b2d4e5a6c7
Revises: e3c0a1b2d4f5
Create Date: 2026-05-11 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f3b2d4e5a6c7"
down_revision: Union[str, Sequence[str], None] = "e3c0a1b2d4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "emission_orders",
        sa.Column("suz_marking_codes", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("emission_orders", "suz_marking_codes")
