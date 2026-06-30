from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from app.database import Base


class VectorType(UserDefinedType):
    """声明 pgvector 列；SQLite 编译时会退化为普通文本。"""

    cache_ok = True

    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def get_col_spec(self, **kw) -> str:
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect):
        del dialect

        def process(value):
            if isinstance(value, list):
                return "[" + ",".join(f"{item:.10g}" for item in value) + "]"
            return value

        return process


@compiles(VectorType, "sqlite")
def compile_vector_for_sqlite(type_, compiler, **kw):
    del type_, compiler, kw
    return "TEXT"


class User(Base):
    """保存登录用户；密码只存安全哈希，不保存明文。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="user")
    usage_events: Mapped[list["AIUsageEvent"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    knowledge_documents: Mapped[list["KnowledgeDocument"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Analysis(Base):
    """保存一次完整分析，并通过 user_id 隔离不同用户的数据。"""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 迁移前的旧记录暂时为空，首个注册用户会自动接管。
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=True,
    )
    resume_text: Mapped[str] = mapped_column(Text)
    job_description: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(
        String(50),
        default="legacy-v1",
        server_default="legacy-v1",
    )
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    interview_attempts: Mapped[list["InterviewAttempt"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
    )
    adaptive_interviews: Mapped[list["AdaptiveInterviewSession"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
    )
    user: Mapped[User | None] = relationship(back_populates="analyses")


class InterviewAttempt(Base):
    """保存一次单题回答与 AI 评分，允许同一道题保留多次练习。"""

    __tablename__ = "interview_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    question_number: Mapped[int] = mapped_column(Integer)
    question_text: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str] = mapped_column(Text)
    feedback_json: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(
        String(50),
        default="legacy-v1",
        server_default="legacy-v1",
    )
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    rag_context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    analysis: Mapped[Analysis] = relationship(back_populates="interview_attempts")


class AdaptiveInterviewSession(Base):
    """LangGraph 驱动的一场可中断、可恢复的自适应面试。"""

    __tablename__ = "adaptive_interview_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="awaiting_answer")
    workflow_version: Mapped[str] = mapped_column(String(50))
    max_rounds: Mapped[int] = mapped_column(Integer, default=5)
    completed_turns: Mapped[int] = mapped_column(Integer, default=0)
    current_node: Mapped[str] = mapped_column(String(50), default="await_answer")
    execution_path_json: Mapped[str] = mapped_column(Text, default="[]")
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    report_prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    analysis: Mapped[Analysis] = relationship(back_populates="adaptive_interviews")
    turns: Mapped[list["AdaptiveInterviewTurn"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AdaptiveInterviewTurn.round_number",
    )


class AdaptiveInterviewTurn(Base):
    """保存自适应面试中的问题、回答、评分和路由决策。"""

    __tablename__ = "adaptive_interview_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "round_number", name="uq_adaptive_turn_round"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("adaptive_interview_sessions.id"),
        index=True,
    )
    round_number: Mapped[int] = mapped_column(Integer)
    question_source: Mapped[str] = mapped_column(String(20))
    source_question_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    question_text: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    answer_points_json: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rag_context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    route_decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    session: Mapped[AdaptiveInterviewSession] = relationship(back_populates="turns")


class KnowledgeDocument(Base):
    """保存用户上传的知识资料及其切块统计。"""

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    character_count: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    user: Mapped[User] = relationship(back_populates="knowledge_documents")
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class KnowledgeChunk(Base):
    """保存可检索的文本片段和对应语义向量。"""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index("ix_knowledge_chunks_user_id_document_id", "user_id", "document_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id"),
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[str] = mapped_column(VectorType(1024))
    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")


class AIUsageEvent(Base):
    """记录一次用户发起的模型操作，失败请求同样用于限额统计。"""

    __tablename__ = "ai_usage_events"
    __table_args__ = (
        Index("ix_ai_usage_events_operation_created_at", "operation", "created_at"),
        Index(
            "ix_ai_usage_events_user_operation_created_at",
            "user_id",
            "operation",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    operation: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="started")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    user: Mapped[User] = relationship(back_populates="usage_events")
