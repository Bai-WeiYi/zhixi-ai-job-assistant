from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select

from app.database import Base
from app.migrate_sqlite_to_postgres import copy_sqlite_data
from app.models import Analysis, InterviewAttempt, User


def create_database(url: str) -> None:
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()


def seed_source(url: str) -> None:
    engine = create_engine(url)
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            User.__table__.insert(),
            {
                "id": 3,
                "email": "owner@example.com",
                "password_hash": "hash",
                "created_at": now,
            },
        )
        connection.execute(
            Analysis.__table__.insert(),
            {
                "id": 7,
                "user_id": 3,
                "resume_text": "resume",
                "job_description": "jd",
                "result_json": "{}",
                "model_name": "demo",
                "duration_ms": 10,
                "created_at": now,
            },
        )
        connection.execute(
            InterviewAttempt.__table__.insert(),
            {
                "id": 9,
                "analysis_id": 7,
                "question_number": 1,
                "question_text": "question",
                "answer_text": "answer",
                "feedback_json": "{}",
                "model_name": "demo",
                "duration_ms": 10,
                "created_at": now,
            },
        )
    engine.dispose()


def test_copy_preserves_records_and_relations(tmp_path):
    source_url = f"sqlite:///{(tmp_path / 'source.db').as_posix()}"
    target_url = f"sqlite:///{(tmp_path / 'target.db').as_posix()}"
    create_database(source_url)
    create_database(target_url)
    seed_source(source_url)

    copied = copy_sqlite_data(
        source_url,
        target_url,
        allow_sqlite_target=True,
    )

    assert copied == {"users": 1, "analyses": 1, "interview_attempts": 1}
    target_engine = create_engine(target_url)
    with target_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(User)) == 1
        analysis = connection.execute(select(Analysis)).mappings().one()
        attempt = connection.execute(select(InterviewAttempt)).mappings().one()
    assert analysis["id"] == 7
    assert analysis["user_id"] == 3
    assert attempt["analysis_id"] == 7
    target_engine.dispose()


def test_copy_refuses_nonempty_target(tmp_path):
    source_url = f"sqlite:///{(tmp_path / 'source.db').as_posix()}"
    target_url = f"sqlite:///{(tmp_path / 'target.db').as_posix()}"
    create_database(source_url)
    create_database(target_url)
    seed_source(source_url)
    seed_source(target_url)

    with pytest.raises(RuntimeError, match="目标数据库已有数据"):
        copy_sqlite_data(
            source_url,
            target_url,
            allow_sqlite_target=True,
        )
