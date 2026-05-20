"""腾讯文档真实同步相关表结构迁移。"""

from __future__ import annotations

from sqlalchemy import inspect, text

from database import Base, engine


TOKEN_COLUMNS: dict[str, str] = {
    "provider": "ALTER TABLE tencent_docs_tokens ADD COLUMN provider VARCHAR(50)",
    "access_token": "ALTER TABLE tencent_docs_tokens ADD COLUMN access_token TEXT",
    "refresh_token": "ALTER TABLE tencent_docs_tokens ADD COLUMN refresh_token TEXT",
    "expires_at": "ALTER TABLE tencent_docs_tokens ADD COLUMN expires_at DATETIME",
    "open_id": "ALTER TABLE tencent_docs_tokens ADD COLUMN open_id VARCHAR(128)",
    "scope": "ALTER TABLE tencent_docs_tokens ADD COLUMN scope VARCHAR(255)",
    "created_at": "ALTER TABLE tencent_docs_tokens ADD COLUMN created_at DATETIME",
    "updated_at": "ALTER TABLE tencent_docs_tokens ADD COLUMN updated_at DATETIME",
}


def ensure_tencent_docs_schema() -> None:
    """幂等创建/补齐腾讯文档 token 预留表。

    只执行 create_all 或 ADD COLUMN，不删除、不重建、不清空旧数据库。
    """

    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "tencent_docs_tokens" not in table_names:
        return

    existing_columns = {
        column["name"] for column in inspector.get_columns("tencent_docs_tokens")
    }
    with engine.begin() as connection:
        for column_name, ddl in TOKEN_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(text(ddl))

