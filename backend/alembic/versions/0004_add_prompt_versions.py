"""Track the prompt version used for persisted AI results."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004_prompt_versions"
down_revision: str | Sequence[str] | None = "0003_rag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("analyses") as batch_op:
        batch_op.add_column(
            sa.Column(
                "prompt_version",
                sa.String(length=50),
                nullable=False,
                server_default="legacy-v1",
            )
        )
    with op.batch_alter_table("interview_attempts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "prompt_version",
                sa.String(length=50),
                nullable=False,
                server_default="legacy-v1",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("interview_attempts") as batch_op:
        batch_op.drop_column("prompt_version")
    with op.batch_alter_table("analyses") as batch_op:
        batch_op.drop_column("prompt_version")
