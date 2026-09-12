"""phase 2: task scheduling columns (depends_on, enqueued)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("depends_on", sa.JSON(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column(
            "enqueued",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "enqueued")
    op.drop_column("tasks", "depends_on")
