"""Add durable adaptive interview sessions and turns."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_adaptive_interviews"
down_revision: str | Sequence[str] | None = "0004_prompt_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "adaptive_interview_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analysis_id", sa.Integer(), sa.ForeignKey("analyses.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("workflow_version", sa.String(length=50), nullable=False),
        sa.Column("max_rounds", sa.Integer(), nullable=False),
        sa.Column("completed_turns", sa.Integer(), nullable=False),
        sa.Column("current_node", sa.String(length=50), nullable=False),
        sa.Column("execution_path_json", sa.Text(), nullable=False),
        sa.Column("report_json", sa.Text(), nullable=True),
        sa.Column("report_model_name", sa.String(length=100), nullable=True),
        sa.Column("report_prompt_version", sa.String(length=50), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_adaptive_interview_sessions_analysis_id", "adaptive_interview_sessions", ["analysis_id"])
    op.create_index("ix_adaptive_interview_sessions_user_id", "adaptive_interview_sessions", ["user_id"])
    op.create_index("ix_adaptive_interview_sessions_thread_id", "adaptive_interview_sessions", ["thread_id"], unique=True)

    op.create_table(
        "adaptive_interview_turns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("adaptive_interview_sessions.id"), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("question_source", sa.String(length=20), nullable=False),
        sa.Column("source_question_number", sa.Integer(), nullable=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("answer_points_json", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("feedback_json", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("rag_context_json", sa.Text(), nullable=True),
        sa.Column("route_decision", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", "round_number", name="uq_adaptive_turn_round"),
    )
    op.create_index("ix_adaptive_interview_turns_session_id", "adaptive_interview_turns", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_adaptive_interview_turns_session_id", table_name="adaptive_interview_turns")
    op.drop_table("adaptive_interview_turns")
    op.drop_index("ix_adaptive_interview_sessions_thread_id", table_name="adaptive_interview_sessions")
    op.drop_index("ix_adaptive_interview_sessions_user_id", table_name="adaptive_interview_sessions")
    op.drop_index("ix_adaptive_interview_sessions_analysis_id", table_name="adaptive_interview_sessions")
    op.drop_table("adaptive_interview_sessions")
