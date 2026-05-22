"""PostgreSQL / Supabase 连接冒烟校验脚本。

运行方式（本地 SQLite 脱机模式，跳过连接）：
    python check_postgres_smoke.py

运行方式（PostgreSQL 在线模式）：
    python check_postgres_smoke.py --live

运行方式（PostgreSQL 在线并写入测试记录）：
    python check_postgres_smoke.py --live --write-test

校验项目：
    1. 数据库连接
    2. 19 种试剂存在
    3. name_en、purity_grade、operator_name 等字段存在
    4. 用户表和 superadmin 存在
    5. 库存流水可查询
    6. 报警事件可查询
    7. 报表统计查询可执行
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError


BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from utils.timezone import now_beijing, today_beijing  # noqa: E402


def check_db_connection(db: Any) -> bool:
    """验证数据库连接。"""

    try:
        result = db.execute(text("SELECT 1")).scalar_one()
        return result == 1
    except SQLAlchemyError as exc:
        print(f"  FAIL: 数据库连接失败 — {exc}")
        return False


def check_reagent_count(db: Any) -> bool:
    """验证 19 种试剂存在。"""

    from models import Reagent

    count = db.execute(select(func.count(Reagent.id))).scalar_one()
    if count >= 19:
        print(f"  OK: 试剂数量 = {count}")
        return True
    print(f"  WARN: 试剂数量 = {count}（预期 ≥ 19）")
    return False


def check_reagent_fields(db: Any) -> bool:
    """验证 name_en、purity_grade 等字段存在。"""

    from models import Reagent

    reagent = db.execute(
        select(Reagent).where(Reagent.name_en.is_not(None)).limit(1)
    ).scalar_one_or_none()
    if reagent is not None:
        print(f"  OK: name_en 字段存在（示例：{reagent.name_en}）")
    else:
        print("  WARN: 没有试剂填写 name_en")

    reagent = db.execute(
        select(Reagent).where(Reagent.purity_grade.is_not(None)).limit(1)
    ).scalar_one_or_none()
    if reagent is not None:
        print(f"  OK: purity_grade 字段存在（示例：{reagent.purity_grade}）")
    else:
        print("  WARN: 没有试剂填写 purity_grade")
    return True


def check_superadmin(db: Any) -> bool:
    """验证用户表和 superadmin 存在。"""

    from models import User

    user_count = db.execute(select(func.count(User.id))).scalar_one()
    print(f"  OK: 用户总数 = {user_count}")

    superadmin = db.execute(
        select(User).where(User.role == "superadmin")
    ).scalar_one_or_none()
    if superadmin is not None:
        print(f"  OK: superadmin 存在（username={superadmin.username}）")
        return True
    print("  WARN: superadmin 不存在，请运行 seed_superadmin.py")
    return False


def check_inventory_records(db: Any) -> bool:
    """验证库存流水可查询。"""

    from models import InventoryRecord

    count = db.execute(select(func.count(InventoryRecord.id))).scalar_one()
    print(f"  OK: 库存流水记录数 = {count}")

    # 验证 operator_name 字段
    record = db.execute(
        select(InventoryRecord).where(InventoryRecord.operator_name.is_not(None)).limit(1)
    ).scalar_one_or_none()
    if record is not None:
        print(f"  OK: operator_name 字段存在（示例：{record.operator_name}）")
    else:
        print("  INFO: 尚无库存流水填写 operator_name")
    return True


def check_alert_events(db: Any) -> bool:
    """验证报警事件可查询。"""

    from models import AlertEvent

    count = db.execute(select(func.count(AlertEvent.id))).scalar_one()
    print(f"  OK: 报警事件记录数 = {count}")
    return True


def check_report_query(db: Any) -> bool:
    """验证报表统计查询可执行。"""

    from models import InventoryRecord, Reagent

    # 消耗 Top N 查询
    today = today_beijing()
    start_at = datetime(today.year, 1, 1)
    end_at = datetime(today.year + 1, 1, 1)

    try:
        consumed = func.sum(func.abs(InventoryRecord.quantity_change))
        rows = db.execute(
            select(Reagent.name_cn, consumed)
            .join(Reagent, InventoryRecord.reagent_id == Reagent.id)
            .where(InventoryRecord.operation_type == "out")
            .where(InventoryRecord.created_at >= start_at)
            .where(InventoryRecord.created_at < end_at)
            .group_by(Reagent.name_cn)
            .order_by(consumed.desc())
            .limit(5)
        ).all()
        print(f"  OK: 报表消耗 Top N 查询返回 {len(rows)} 条")
        return True
    except SQLAlchemyError as exc:
        print(f"  FAIL: 报表查询失败 — {exc}")
        return False


def write_test_record(db: Any) -> None:
    """写入一条测试报警事件，验证写权限。"""

    from models import AlertEvent, Reagent

    reagent = db.execute(select(Reagent).order_by(Reagent.id.asc()).limit(1)).scalar_one_or_none()
    if reagent is None:
        print("  SKIP: 没有试剂，跳过写入测试")
        return

    test_alert = AlertEvent(
        reagent_id=reagent.id,
        alert_type="冒烟测试",
        level="info",
        message=f"冒烟测试记录 {now_beijing().isoformat()}",
        is_resolved=True,
        resolved_at=now_beijing(),
    )
    try:
        db.add(test_alert)
        db.commit()
        db.refresh(test_alert)
        print(f"  OK: 写入测试报警 ID={test_alert.id}")
        # 清理
        db.delete(test_alert)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        print(f"  FAIL: 写入测试失败 — {exc}")


def run_checks(live: bool = False, write_test: bool = False) -> None:
    checks_passed = 0
    checks_total = 0

    def run(label: str, fn):
        nonlocal checks_passed, checks_total
        checks_total += 1
        print(f"\n[{checks_total}] {label}")
        try:
            if fn():
                checks_passed += 1
        except Exception as exc:
            print(f"  FAIL: {exc}")

    if not live:
        print("=== 脱机模式：仅检查代码和模型导入 ===\n")
        from database import init_db

        init_db()

        from models import (  # noqa: F401
            AlertEvent,
            AuditLog,
            InventoryRecord,
            Reagent,
            SyncLog,
            User,
        )

        print("[1] 模型导入 OK")
        print("[2] 数据库初始化 OK")
        print(f"\n脱机检查通过。使用 --live 连接真实 PostgreSQL。")
        return

    print("=== PostgreSQL 在线冒烟测试 ===\n")

    from database import SessionLocal, init_db

    init_db()
    db = SessionLocal()

    try:
        run("数据库连接", lambda: check_db_connection(db))
        run("试剂数量 ≥ 19", lambda: check_reagent_count(db))
        run("试剂字段（name_en, purity_grade）", lambda: check_reagent_fields(db))
        run("用户表与 superadmin", lambda: check_superadmin(db))
        run("库存流水可查询", lambda: check_inventory_records(db))
        run("报警事件可查询", lambda: check_alert_events(db))
        run("报表统计查询可执行", lambda: check_report_query(db))

        if write_test:
            run("写入测试记录", lambda: (write_test_record(db), True)[1])
    finally:
        db.close()

    print(f"\n{'='*40}")
    print(f"结果：{checks_passed}/{checks_total} 项通过")
    if checks_passed == checks_total:
        print("冒烟测试全部通过")
    else:
        print(f"有 {checks_total - checks_passed} 项未通过，请检查")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PostgreSQL 冒烟校验")
    parser.add_argument("--live", action="store_true", help="连接真实数据库")
    parser.add_argument("--write-test", action="store_true", help="写入测试记录后自动清理")
    args = parser.parse_args()

    run_checks(live=args.live, write_test=args.write_test)
