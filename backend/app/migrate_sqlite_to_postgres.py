"""把现有 SQLite 业务数据一次性复制到已经迁移好的 PostgreSQL。"""

import argparse
from collections.abc import Mapping

from sqlalchemy import MetaData, Table, create_engine, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.config import get_settings

TABLE_NAMES = ("users", "analyses", "interview_attempts")


def load_tables(engine: Engine) -> dict[str, Table]:
    """反射数据库表，确保复制前两端结构都已准备完成。"""
    metadata = MetaData()
    metadata.reflect(bind=engine, only=TABLE_NAMES)
    missing = set(TABLE_NAMES) - set(metadata.tables)
    if missing:
        names = "、".join(sorted(missing))
        raise RuntimeError(f"数据库缺少表：{names}，请先执行 alembic upgrade head")
    return {name: metadata.tables[name] for name in TABLE_NAMES}


def table_count(engine: Engine, table: Table) -> int:
    with engine.connect() as connection:
        return connection.scalar(select(func.count()).select_from(table)) or 0


def read_rows(engine: Engine, table: Table) -> list[Mapping[str, object]]:
    with engine.connect() as connection:
        rows = connection.execute(select(table).order_by(table.c.id)).mappings()
        return [dict(row) for row in rows]


def reset_postgres_sequences(engine: Engine) -> None:
    """显式写入主键后同步序列，避免下一次新增记录发生 ID 冲突。"""
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as connection:
        for table_name in TABLE_NAMES:
            connection.execute(
                text(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table_name}', 'id'),
                        COALESCE((SELECT MAX(id) FROM {table_name}), 1),
                        EXISTS (SELECT 1 FROM {table_name})
                    )
                    """
                )
            )


def copy_sqlite_data(
    source_url: str,
    target_url: str,
    *,
    allow_sqlite_target: bool = False,
) -> dict[str, int]:
    """按外键顺序复制数据；目标非空时停止，避免覆盖或合并用户数据。"""
    source_backend = make_url(source_url).get_backend_name()
    target_backend = make_url(target_url).get_backend_name()
    if source_backend != "sqlite":
        raise ValueError("源数据库必须是 SQLite")
    if target_backend != "postgresql" and not allow_sqlite_target:
        raise ValueError("目标数据库必须是 PostgreSQL")
    if source_url == target_url:
        raise ValueError("源数据库和目标数据库不能相同")

    source_engine = create_engine(source_url, poolclass=NullPool)
    target_engine = create_engine(target_url, poolclass=NullPool)
    try:
        source_tables = load_tables(source_engine)
        target_tables = load_tables(target_engine)

        nonempty = [
            name
            for name, table in target_tables.items()
            if table_count(target_engine, table) > 0
        ]
        if nonempty:
            names = "、".join(nonempty)
            raise RuntimeError(f"目标数据库已有数据（{names}），已停止复制")

        copied: dict[str, int] = {}
        with target_engine.begin() as connection:
            for name in TABLE_NAMES:
                rows = read_rows(source_engine, source_tables[name])
                if rows:
                    connection.execute(target_tables[name].insert(), rows)
                copied[name] = len(rows)

        reset_postgres_sequences(target_engine)
        return copied
    finally:
        source_engine.dispose()
        target_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="把旧 SQLite 数据复制到 DATABASE_URL 指向的 PostgreSQL",
    )
    parser.add_argument(
        "--source",
        default="sqlite:///./data/job_assistant.db",
        help="旧 SQLite 地址，默认读取 backend/data/job_assistant.db",
    )
    args = parser.parse_args()

    settings = get_settings()
    target_url = settings.sqlalchemy_database_url()
    copied = copy_sqlite_data(args.source, target_url)
    print(
        "迁移完成："
        f"用户 {copied['users']} 条，"
        f"分析 {copied['analyses']} 条，"
        f"答题 {copied['interview_attempts']} 条。"
    )


if __name__ == "__main__":
    main()
