"""phase 4: observability columns (durations, tokens, cost, tool_calls)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # executions
    op.add_column("executions", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("executions", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("executions", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("executions", sa.Column("total_tokens", sa.Integer(), nullable=True))
    op.add_column("executions", sa.Column("cost_usd", sa.Float(), nullable=True))

    # tasks
    op.add_column("tasks", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("total_tokens", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("cost_usd", sa.Float(), nullable=True))
    op.add_column("tasks", sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    for col in ("tool_calls", "cost_usd", "total_tokens", "duration_ms", "completed_at", "started_at"):
        op.drop_column("tasks", col)
    for col in ("cost_usd", "total_tokens", "duration_ms", "completed_at", "started_at"):
        op.drop_column("executions", col)
