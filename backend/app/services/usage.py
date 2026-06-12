"""集中处理 AI 操作限额，模型失败也保留一次用量。"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AIUsageEvent
from app.schemas import UsageQuota, UsageSummary

ANALYSIS_OPERATION = "analysis"
INTERVIEW_OPERATION = "interview"
VALID_OPERATIONS = {ANALYSIS_OPERATION, INTERVIEW_OPERATION}


@dataclass
class UsageLimitExceeded(Exception):
    """携带下一次可用时间，路由层据此返回 429。"""

    reset_at: datetime


def utc_day_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or datetime.now(timezone.utc)
    start = current.astimezone(timezone.utc).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return start, start + timedelta(days=1)


def operation_limits(operation: str, settings: Settings) -> tuple[int, int]:
    if operation == ANALYSIS_OPERATION:
        return settings.user_daily_analysis_limit, settings.global_daily_analysis_limit
    if operation == INTERVIEW_OPERATION:
        return settings.user_daily_interview_limit, settings.global_daily_interview_limit
    raise ValueError(f"未知 AI 操作：{operation}")


def count_usage(
    db: Session,
    operation: str,
    start_at: datetime,
    user_id: int | None = None,
) -> int:
    statement = select(func.count(AIUsageEvent.id)).where(
        AIUsageEvent.operation == operation,
        AIUsageEvent.created_at >= start_at,
    )
    if user_id is not None:
        statement = statement.where(AIUsageEvent.user_id == user_id)
    return db.scalar(statement) or 0


def claim_usage(
    db: Session,
    user_id: int,
    operation: str,
    settings: Settings,
    now: datetime | None = None,
) -> AIUsageEvent:
    """先占用额度再调用模型，防止失败请求绕过成本控制。"""
    start_at, reset_at = utc_day_window(now)
    user_limit, global_limit = operation_limits(operation, settings)

    if db.bind is not None and db.bind.dialect.name == "postgresql":
        # 同一操作共用事务锁，使“计数 + 新增”在并发请求下保持原子性。
        lock_key = 71001 if operation == ANALYSIS_OPERATION else 71002
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})

    user_used = count_usage(db, operation, start_at, user_id)
    global_used = count_usage(db, operation, start_at)
    if user_used >= user_limit or global_used >= global_limit:
        db.rollback()
        raise UsageLimitExceeded(reset_at)

    event = AIUsageEvent(user_id=user_id, operation=operation, status="started")
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def finish_usage(db: Session, event: AIUsageEvent, status: str) -> None:
    event.status = status
    db.add(event)
    db.commit()


def build_usage_summary(
    db: Session,
    user_id: int,
    settings: Settings,
    now: datetime | None = None,
) -> UsageSummary:
    start_at, reset_at = utc_day_window(now)

    def quota(operation: str) -> UsageQuota:
        user_limit, _ = operation_limits(operation, settings)
        used = count_usage(db, operation, start_at, user_id)
        return UsageQuota(
            used=used,
            limit=user_limit,
            remaining=max(user_limit - used, 0),
            reset_at=reset_at,
        )

    return UsageSummary(
        analysis=quota(ANALYSIS_OPERATION),
        interview=quota(INTERVIEW_OPERATION),
    )
