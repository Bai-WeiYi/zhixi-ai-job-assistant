"""增加 AI 调用用量表。"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_usage"
down_revision: str | Sequence[str] | None = "0001_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_ai_usage_events_user_id_users",
        ),
    )
    op.create_index("ix_ai_usage_events_user_id", "ai_usage_events", ["user_id"])
    op.create_index(
        "ix_ai_usage_events_operation_created_at",
        "ai_usage_events",
        ["operation", "created_at"],
    )
    op.create_index(
        "ix_ai_usage_events_user_operation_created_at",
        "ai_usage_events",
        ["user_id", "operation", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("ai_usage_events")
