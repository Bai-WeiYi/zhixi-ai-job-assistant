from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.models import AIUsageEvent, User
from app.services.usage import (
    ANALYSIS_OPERATION,
    INTERVIEW_OPERATION,
    KNOWLEDGE_OPERATION,
    UsageLimitExceeded,
    build_usage_summary,
    claim_usage,
    finish_usage,
)


def add_user(db_session, email: str) -> User:
    user = User(email=email, password_hash="hash")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def settings(**overrides) -> Settings:
    values = {
        "user_daily_analysis_limit": 3,
        "user_daily_interview_limit": 10,
        "global_daily_analysis_limit": 30,
        "global_daily_interview_limit": 100,
    }
    values.update(overrides)
    return Settings(**values)


def test_claim_and_finish_usage(db_session):
    user = add_user(db_session, "usage@example.com")
    event = claim_usage(db_session, user.id, ANALYSIS_OPERATION, settings())
    finish_usage(db_session, event, "succeeded")

    summary = build_usage_summary(db_session, user.id, settings())
    assert summary.analysis.used == 1
    assert summary.analysis.remaining == 2
    assert event.status == "succeeded"
    assert summary.knowledge.remaining == 5


def test_knowledge_usage_limit(db_session):
    user = add_user(db_session, "knowledge-usage@example.com")
    limits = settings(user_daily_knowledge_limit=1, global_daily_knowledge_limit=5)

    claim_usage(db_session, user.id, KNOWLEDGE_OPERATION, limits)
    with pytest.raises(UsageLimitExceeded):
        claim_usage(db_session, user.id, KNOWLEDGE_OPERATION, limits)


def test_global_limit_applies_across_users(db_session):
    first = add_user(db_session, "first@example.com")
    second = add_user(db_session, "second@example.com")
    limits = settings(global_daily_analysis_limit=1)

    claim_usage(db_session, first.id, ANALYSIS_OPERATION, limits)
    with pytest.raises(UsageLimitExceeded):
        claim_usage(db_session, second.id, ANALYSIS_OPERATION, limits)


def test_usage_resets_at_utc_midnight(db_session):
    user = add_user(db_session, "reset@example.com")
    now = datetime(2026, 6, 12, 8, tzinfo=timezone.utc)
    db_session.add_all(
        [
            AIUsageEvent(
                user_id=user.id,
                operation=INTERVIEW_OPERATION,
                status="failed",
                created_at=now - timedelta(days=1),
            ),
            AIUsageEvent(
                user_id=user.id,
                operation=INTERVIEW_OPERATION,
                status="succeeded",
                created_at=now,
            ),
        ]
    )
    db_session.commit()

    summary = build_usage_summary(db_session, user.id, settings(), now=now)
    assert summary.interview.used == 1
    assert summary.interview.reset_at == datetime(
        2026,
        6,
        13,
        tzinfo=timezone.utc,
    )
