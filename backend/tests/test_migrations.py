import sqlite3

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def run_upgrade(database_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    from app.config import get_settings

    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    get_settings.cache_clear()


def test_migration_creates_empty_database(tmp_path, monkeypatch):
    database_path = tmp_path / "empty.db"
    run_upgrade(database_path, monkeypatch)

    inspector = inspect(create_engine(f"sqlite:///{database_path.as_posix()}"))
    assert {
        "users",
        "analyses",
        "interview_attempts",
        "ai_usage_events",
        "alembic_version",
    } <= set(inspector.get_table_names())
    assert "user_id" in {
        column["name"] for column in inspector.get_columns("analyses")
    }


def test_migration_preserves_legacy_analysis(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE analyses (
            id INTEGER PRIMARY KEY,
            resume_text TEXT NOT NULL,
            job_description TEXT NOT NULL,
            result_json TEXT NOT NULL,
            model_name VARCHAR(100) NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            duration_ms INTEGER NOT NULL,
            created_at DATETIME NOT NULL
        );
        INSERT INTO analyses (
            id, resume_text, job_description, result_json, model_name,
            duration_ms, created_at
        ) VALUES (
            1, 'legacy resume', 'legacy jd', '{}', 'legacy-model',
            100, '2026-06-01 00:00:00'
        );
        """
    )
    connection.close()

    run_upgrade(database_path, monkeypatch)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as migrated:
        row = migrated.execute(
            text("SELECT id, user_id, model_name FROM analyses WHERE id = 1")
        ).one()
    assert row.id == 1
    assert row.user_id is None
    assert row.model_name == "legacy-model"
