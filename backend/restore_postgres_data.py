"""从项目级 JSON 备份恢复 Supabase PostgreSQL 数据。

运行方式：
    # 试运行（校验备份文件，不写入）
    python restore_postgres_data.py --file backups/pg_backup_YYYYMMDD_HHMMSS.json --dry-run

    # 正式恢复（需要显式确认）
    python restore_postgres_data.py --file backups/xxx.json --confirm-restore

安全机制：
    - 默认 --dry-run，不写入数据库
    - 正式恢复必须带 --confirm-restore
    - 目标表已有数据时拒绝恢复（除非 --force）
    - 恢复后自动校准 sequence
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

RESTORE_ORDER = [
    ("users", "User"),
    ("reagents", "Reagent"),
    ("inventory_records", "InventoryRecord"),
    ("alert_events", "AlertEvent"),
    ("sync_logs", "SyncLog"),
    ("audit_logs", "AuditLog"),
]


def parse_value(raw: Any, col_type: Any) -> Any:
    """将 JSON 字符串值转换为 Python 类型。"""

    if raw is None:
        return None
    py_type = getattr(col_type, "python_type", lambda: str)()
    if py_type in (datetime, date) and isinstance(raw, str):
        return datetime.fromisoformat(raw) if py_type is datetime else date.fromisoformat(raw)
    return raw


def calibrate_sequence(db: Any, table_name: str) -> None:
    """校准 PostgreSQL sequence 到当前最大 id + 1。"""

    module = __import__("models", fromlist=[""])
    model = getattr(module, RESTORE_ORDER[0][1].__class__)
    # Find the model class
    for tname, mname in RESTORE_ORDER:
        if tname == table_name:
            model = getattr(module, mname)
            break
    else:
        return

    table_obj = model.__table__
    max_id = db.execute(select(func.max(table_obj.c.id))).scalar_one()
    if max_id is None:
        return

    seq_name = f"{table_name}_id_seq"
    try:
        db.execute(text(f"SELECT setval('{seq_name}', :val, true)"), {"val": max_id})
        print(f"  sequence {seq_name} 已校准到 {max_id}")
    except SQLAlchemyError:
        pass


def restore(json_path: Path, dry_run: bool = True, force: bool = False) -> None:
    if not json_path.exists():
        print(f"ERROR: 备份文件不存在: {json_path}")
        sys.exit(1)

    with open(json_path, encoding="utf-8") as f:
        data: dict[str, dict] = json.load(f)

    print(f"备份文件: {json_path.name}")
    print(f"包含表: {', '.join(data.keys())}")
    print()

    for table_name in data:
        meta = data[table_name]
        print(f"  {table_name}: {meta['count']} 条")

    if dry_run:
        print(f"\n[Dry-run 完成] 未写入数据库。")
        print("如需正式恢复，请添加 --confirm-restore")
        return

    if not force:
        print("\n" + "!" * 60)
        print("  WARNING: 即将向数据库写入数据")
        print("  此操作不可逆，请确保已备份当前数据")
        print("!" * 60)
        response = input("\n确认恢复？输入 'yes' 继续: ")
        if response.strip().lower() != "yes":
            print("已取消")
            return

    from database import SessionLocal, init_db

    init_db()
    db = SessionLocal()

    try:
        # 安全检查：表是否已有数据
        if not force:
            module = __import__("models", fromlist=[""])
            for table_name, model_name in RESTORE_ORDER:
                if table_name not in data:
                    continue
                model = getattr(module, model_name)
                count = db.execute(select(func.count()).select_from(model)).scalar_one()
                if count > 0:
                    print(f"ERROR: {table_name} 已有 {count} 条数据，使用 --force 强制覆盖")
                    sys.exit(1)

        for table_name, model_name in RESTORE_ORDER:
            if table_name not in data:
                continue
            meta = data[table_name]
            rows = meta.get("rows", [])
            if not rows:
                continue

            module = __import__("models", fromlist=[model_name])
            model = getattr(module, model_name)
            inserted = 0

            for row_dict in rows:
                kwargs = {}
                for col in model.__table__.columns:
                    raw = row_dict.get(col.name)
                    kwargs[col.name] = parse_value(raw, col.type)
                db.add(model(**kwargs))
                inserted += 1

            db.flush()
            calibrate_sequence(db, table_name)
            print(f"  {table_name}: 已写入 {inserted} 条")

        db.commit()
        print("\n恢复完成")

        for table_name, _ in RESTORE_ORDER:
            if table_name not in data:
                continue
            module = __import__("models", fromlist=[""])
            model = getattr(module, dict(RESTORE_ORDER)[table_name])
            count = db.execute(select(func.count()).select_from(model)).scalar_one()
            print(f"  {table_name}: 当前 {count} 条")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PostgreSQL 数据恢复")
    parser.add_argument("--file", required=True, help="备份 JSON 文件路径")
    parser.add_argument("--dry-run", action="store_true", default=True, help="仅校验，不写入（默认）")
    parser.add_argument("--confirm-restore", action="store_true", default=False, help="确认执行恢复")
    parser.add_argument("--force", action="store_true", help="覆盖已有数据")
    args = parser.parse_args()

    is_dry = not args.confirm_restore
    restore(Path(args.file), dry_run=is_dry, force=args.force)
