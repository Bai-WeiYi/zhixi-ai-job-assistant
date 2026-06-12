from app.config import Settings


def test_postgres_url_uses_psycopg_driver():
    settings = Settings(database_url="postgresql://user:pass@localhost:5432/zhixi")
    assert (
        settings.sqlalchemy_database_url()
        == "postgresql+psycopg://user:pass@localhost:5432/zhixi"
    )


def test_provider_postgres_url_is_supported():
    settings = Settings(database_url="postgres://user:pass@localhost:5432/zhixi")
    assert settings.sqlalchemy_database_url().startswith("postgresql+psycopg://")


def test_sqlite_url_is_unchanged():
    settings = Settings(database_url="sqlite:///./data/test.db")
    assert settings.sqlalchemy_database_url() == "sqlite:///./data/test.db"
