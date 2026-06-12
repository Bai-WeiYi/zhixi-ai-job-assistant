from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()
settings.ensure_data_directory()

database_url = settings.sqlalchemy_database_url()
if database_url.startswith("sqlite"):
    engine_options = {"connect_args": {"check_same_thread": False}}
else:
    # PostgreSQL 连接池复用连接，并在取出连接时检查其是否仍然可用。
    engine_options = {
        "pool_pre_ping": True,
        "pool_size": settings.database_pool_size,
        "max_overflow": settings.database_max_overflow,
        "pool_recycle": settings.database_pool_recycle_seconds,
        "connect_args": {
            "connect_timeout": settings.database_connect_timeout_seconds,
        },
    }

engine = create_engine(database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """每个请求使用独立数据库会话，请求结束后统一关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
