"""Supabase PostgreSQL 项目级数据备份脚本。

运行方式：
    # 试运行（仅打印表名和行数）
    python backup_postgres_data.py --dry-run

    # 正式备份
    python backup_postgres_data.py

输出：backups/pg_backup_YYYYMMDD_HHMMSS.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select

BACKEND_DIR = Path(__file__).resolve().parent
BACKUP_DIR = BACKEND_DIR / "backups"
sys.path.insert(0, str(BACKEND_DIR))

BACKUP_TABLES = [
    ("users", "User"),
    ("reagents", "Reagent"),
    ("inventory_records", "InventoryRecord"),
    ("alert_events", "AlertEvent"),
    ("sync_logs", "SyncLog"),
    ("audit_logs", "AuditLog"),
]

# 这些字段不导出（明文密码等）
SKIP_COLUMNS: dict[str, set[str]] = {
    "users": set(),
}


def row_to_dict(obj: object) -> dict:
    """ORM 对象转可序列化 dict，日期时间转 ISO 格式。"""

    result: dict = {}
    table_name = obj.__table__.name
    skip = SKIP_COLUMNS.get(table_name, set())
    for col in obj.__table__.columns:
        if col.name in skip:
            continue
        value = getattr(obj, col.name)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        result[col.name] = value
    return result


def backup(dry_run: bool = False) -> None:
    from database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    try:
        export_data: dict[str, dict] = {}

        for table_name, model_name in BACKUP_TABLES:
            module = __import__("models", fromlist=[model_name])
            model = getattr(module, model_name)

            count = db.execute(select(func.count()).select_from(model)).scalar_one()
            print(f"  {table_name}: {count} 条")

            if dry_run:
                export_data[table_name] = {"count": count, "rows": []}
                continue

            rows = db.execute(select(model).order_by(model.id)).scalars().all()
            export_data[table_name] = {
                "count": count,
                "rows": [row_to_dict(row) for row in rows],
            }

        if dry_run:
            print("\n[Dry-run 完成] 未写入文件")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = BACKUP_DIR / f"pg_backup_{timestamp}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        total = sum(v["count"] for v in export_data.values())
        print(f"\n备份完成 → {output_path}")
        print(f"总计 {total} 条记录，{len(export_data)} 张表")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PostgreSQL 数据备份")
    parser.add_argument("--dry-run", action="store_true", help="仅打印表结构，不导出数据")
    args = parser.parse_args()
    backup(dry_run=args.dry_run)
