"""为 inventory_records 表新增 operator_name 字段。

运行方式：
    python migrate_inventory_log_operator.py

幂等：重复运行不会报错，已存在字段时跳过。
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from database import engine


COLUMN_NAME = "operator_name"
MIGRATION_SQL = (
    f"ALTER TABLE inventory_records ADD COLUMN {COLUMN_NAME} VARCHAR(50)"
)


def run() -> None:
    inspector = inspect(engine)
    existing_columns = {
        column["name"]
        for column in inspector.get_columns("inventory_records")
    }

    if COLUMN_NAME in existing_columns:
        print(f"字段 {COLUMN_NAME} 已存在，无需迁移")
        return

    with engine.begin() as connection:
        connection.execute(text(MIGRATION_SQL))
        print(f"已新增字段：{COLUMN_NAME}")


if __name__ == "__main__":
    run()
