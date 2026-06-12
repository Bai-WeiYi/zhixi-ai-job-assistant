"""建立现有业务表，并增加用户鉴权与数据归属。"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_auth"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """同时兼容全新数据库和已有的本地 SQLite 数据库。"""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("email"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if "analyses" not in tables:
        op.create_table(
            "analyses",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("resume_text", sa.Text(), nullable=False),
            sa.Column("job_description", sa.Text(), nullable=False),
            sa.Column("result_json", sa.Text(), nullable=False),
            sa.Column("model_name", sa.String(length=100), nullable=False),
            sa.Column("prompt_tokens", sa.Integer(), nullable=True),
            sa.Column("completion_tokens", sa.Integer(), nullable=True),
            sa.Column("total_tokens", sa.Integer(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                name="fk_analyses_user_id_users",
            ),
        )
        op.create_index("ix_analyses_user_id", "analyses", ["user_id"])
    else:
        columns = {column["name"] for column in inspector.get_columns("analyses")}
        if "user_id" not in columns:
            # batch 模式会重建 SQLite 表，从而安全增加外键并保留旧记录。
            with op.batch_alter_table("analyses") as batch_op:
                batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_analyses_user_id_users",
                    "users",
                    ["user_id"],
                    ["id"],
                )
                batch_op.create_index("ix_analyses_user_id", ["user_id"])

    inspector = sa.inspect(connection)
    if "interview_attempts" not in inspector.get_table_names():
        op.create_table(
            "interview_attempts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("analysis_id", sa.Integer(), nullable=False),
            sa.Column("question_number", sa.Integer(), nullable=False),
            sa.Column("question_text", sa.Text(), nullable=False),
            sa.Column("answer_text", sa.Text(), nullable=False),
            sa.Column("feedback_json", sa.Text(), nullable=False),
            sa.Column("model_name", sa.String(length=100), nullable=False),
            sa.Column("prompt_tokens", sa.Integer(), nullable=True),
            sa.Column("completion_tokens", sa.Integer(), nullable=True),
            sa.Column("total_tokens", sa.Integer(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["analysis_id"],
                ["analyses.id"],
                name="fk_interview_attempts_analysis_id_analyses",
            ),
        )
        op.create_index(
            "ix_interview_attempts_analysis_id",
            "interview_attempts",
            ["analysis_id"],
        )


def downgrade() -> None:
    """仅移除鉴权新增结构，不删除已有业务数据。"""
    with op.batch_alter_table("analyses") as batch_op:
        batch_op.drop_index("ix_analyses_user_id")
        batch_op.drop_constraint("fk_analyses_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
