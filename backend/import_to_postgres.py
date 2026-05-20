"""将 SQLite 导出的 JSON 数据导入 PostgreSQL。

运行方式：
    python import_to_postgres.py exports/sqlite_export_YYYYMMDD_HHMMSS.json

参数：
    --dry-run   只打印导入摘要，不写入数据库
    --force     允许重复导入（跳过安全保护）

注意：
    - 导入前请确保 DATABASE_URL 指向目标 PostgreSQL 实例
    - 导入按依赖顺序执行（users → reagents → inventory_records → ...）
    - 保留原始 id 值，导入后自动校准序列
    - 不导出/导入 password_hash 以外的敏感字段
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from database import SessionLocal, init_db
from models import (
    AlertEvent,
    AuditLog,
    InventoryRecord,
    Reagent,
    SyncLog,
    User,
)

IMPORT_ORDER = [
    ("users", User),
    ("reagents", Reagent),
    ("inventory_records", InventoryRecord),
    ("alert_events", AlertEvent),
    ("sync_logs", SyncLog),
    ("audit_logs", AuditLog),
]


def parse_iso(value: str | None, target_type: type):
    """将 ISO 字符串转为目标 Python 类型。"""

    if value is None:
        return None
    if target_type in (datetime, date):
        return datetime.fromisoformat(value) if target_type is datetime else date.fromisoformat(value)
    return value


def import_data(json_path: Path, dry_run: bool = False, force: bool = False) -> None:
    init_db()
    db = SessionLocal()

    try:
        with open(json_path, encoding="utf-8") as f:
            data: dict[str, list[dict]] = json.load(f)

        # 安全检查：目标表是否已有数据
        if not force:
            for table_name, model in IMPORT_ORDER:
                existing = db.execute(select(func.count()).select_from(model)).scalar_one()
                if existing > 0:
                    print(f"ERROR: {table_name} 已有 {existing} 条数据，添加 --force 参数以强制导入")
                    sys.exit(1)

        if dry_run:
            print("=== DRY RUN ===")
            for table_name, model in IMPORT_ORDER:
                rows = data.get(table_name, [])
                print(f"{table_name}: 将导入 {len(rows)} 条")
            return

        for table_name, model in IMPORT_ORDER:
            rows = data.get(table_name, [])
            if not rows:
                continue

            inserted = 0
            for row_dict in rows:
                # Build kwargs from row, converting dates
                kwargs = {}
                for col in model.__table__.columns:
                    val = row_dict.get(col.name)
                    if isinstance(val, str):
                        val = parse_iso(val, col.type.python_type)
                    kwargs[col.name] = val

                obj = model(**kwargs)
                db.add(obj)
                inserted += 1

            db.flush()
            print(f"{table_name}: 已写入 {inserted} 条")

        # 校准序列
        for table_name, model in IMPORT_ORDER:
            table_obj = model.__table__
            max_id = db.execute(select(func.max(table_obj.c.id))).scalar_one()
            if max_id:
                seq_name = f"{table_obj.name}_id_seq"
                try:
                    db.execute(
                        text(
                            f"SELECT setval(:seq, :val, true)"
                        ).bindparams(seq=seq_name, val=max_id)
                    )
                except SQLAlchemyError:
                    pass  # 序列不存在时忽略（SQLite 无序列概念）

        db.commit()
        print("\n导入完成")

        # 打印最终统计
        for table_name, model in IMPORT_ORDER:
            count = db.execute(select(func.count()).select_from(model)).scalar_one()
            print(f"  {table_name}: {count} 条")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将 SQLite 导出数据导入 PostgreSQL")
    parser.add_argument("json_file", help="导出的 JSON 文件路径")
    parser.add_argument("--dry-run", action="store_true", help="仅打印摘要，不写入")
    parser.add_argument("--force", action="store_true", help="允许重复导入")
    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"ERROR: 文件不存在: {json_path}")
        sys.exit(1)

    import_data(json_path, dry_run=args.dry_run, force=args.force)
