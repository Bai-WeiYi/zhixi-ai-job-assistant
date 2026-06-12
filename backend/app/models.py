from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


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
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    analysis: Mapped[Analysis] = relationship(back_populates="interview_attempts")


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
