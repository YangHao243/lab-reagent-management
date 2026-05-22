"""导出 SQLite 核心数据为 JSON，用于迁移到 PostgreSQL。

运行方式：
    python export_sqlite_data.py

输出文件：backend/exports/sqlite_export_YYYYMMDD_HHMMSS.json
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from models import (
    AlertEvent,
    AuditLog,
    InventoryRecord,
    Reagent,
    SyncLog,
    User,
)
from utils.timezone import now_beijing

EXPORT_DIR = Path(__file__).resolve().parent / "exports"
DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent / "lab_reagent.db"
SQLITE_DATABASE_URL = os.getenv(
    "SQLITE_DATABASE_URL",
    f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}",
)
EXPORT_TABLES = [
    ("users", User),
    ("reagents", Reagent),
    ("inventory_records", InventoryRecord),
    ("alert_events", AlertEvent),
    ("sync_logs", SyncLog),
    ("audit_logs", AuditLog),
]


def row_to_dict(obj: object) -> dict:
    """将 ORM 对象转为普通 dict，处理日期时间序列化。"""

    result: dict = {}
    for col in obj.__table__.columns:
        value = getattr(obj, col.name)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        result[col.name] = value
    return result


def export() -> None:
    # 迁移导出必须固定读取本地 SQLite，不能复用 .env 中指向 Supabase 的 DATABASE_URL。
    engine = create_engine(
        SQLITE_DATABASE_URL,
        connect_args={"check_same_thread": False}
        if SQLITE_DATABASE_URL.startswith("sqlite")
        else {},
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = now_beijing().strftime("%Y%m%d_%H%M%S")
    output_path = EXPORT_DIR / f"sqlite_export_{timestamp}.json"

    export_data: dict[str, list[dict]] = {}

    try:
        for table_name, model in EXPORT_TABLES:
            count = db.execute(select(func.count()).select_from(model)).scalar_one()
            print(f"{table_name}: {count} 条")
            rows = db.execute(select(model).order_by(model.id)).scalars().all()
            export_data[table_name] = [row_to_dict(row) for row in rows]

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        print(f"\n导出完成：{output_path}")
        total = sum(len(v) for v in export_data.values())
        print(f"总计导出 {total} 条记录")
    finally:
        db.close()


if __name__ == "__main__":
    export()
