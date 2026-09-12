"""phase 5: indexes for frequently queried fields

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-12
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # "recent executions" listing (ORDER BY created_at DESC).
    op.create_index("ix_executions_created_at", "executions", ["created_at"])
    # stale-task reaper (status = RUNNING AND updated_at < cutoff).
    op.create_index("ix_tasks_status_updated_at", "tasks", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_tasks_status_updated_at", table_name="tasks")
    op.drop_index("ix_executions_created_at", table_name="executions")
