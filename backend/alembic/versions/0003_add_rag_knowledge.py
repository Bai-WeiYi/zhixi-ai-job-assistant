"""增加 RAG 知识库和评分引用快照。"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError


class VectorType(sa.types.UserDefinedType):
    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def get_col_spec(self, **kw) -> str:
        return f"vector({self.dimensions})"

revision: str = "0003_rag"
down_revision: str | Sequence[str] | None = "0002_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    vector_available = False
    if bind.dialect.name == "postgresql":
        # Neon 支持 pgvector；普通本地 PostgreSQL 未安装扩展时自动退化为 TEXT。
        try:
            with bind.begin_nested():
                bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
            vector_available = True
        except SQLAlchemyError:
            vector_available = False

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_knowledge_documents_user_id", "knowledge_documents", ["user_id"])

    embedding_type = VectorType(1024) if vector_available else sa.Text()
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", embedding_type, nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])
    op.create_index("ix_knowledge_chunks_user_id", "knowledge_chunks", ["user_id"])
    op.create_index(
        "ix_knowledge_chunks_user_id_document_id",
        "knowledge_chunks",
        ["user_id", "document_id"],
    )
    op.add_column(
        "interview_attempts",
        sa.Column("rag_context_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interview_attempts", "rag_context_json")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
