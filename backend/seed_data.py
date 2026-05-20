"""初始化测试数据脚本。

运行方式：
    python seed_data.py
"""

from __future__ import annotations

from typing import Any

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal, init_db
from models import Reagent, User


DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123456"


# 第一阶段测试试剂数据，仅用于本地开发和接口联调。
TEST_REAGENTS: list[dict[str, Any]] = [
    {
        "name_cn": "丙酮",
        "name_en": "Acetone",
        "cas_no": "67-64-1",
        "category": "有机溶剂",
        "specification": "500ml",
        "unit": "瓶",
        "current_quantity": 12.0,
        "warning_threshold": 3.0,
        "location": "有机试剂柜 A1",
        "hazard_level": "易燃",
    },
    {
        "name_cn": "异丙醇",
        "name_en": "Isopropyl Alcohol",
        "cas_no": "67-63-0",
        "category": "有机溶剂",
        "specification": "500ml",
        "unit": "瓶",
        "current_quantity": 10.0,
        "warning_threshold": 3.0,
        "location": "有机试剂柜 A1",
        "hazard_level": "易燃",
    },
    {
        "name_cn": "盐酸",
        "name_en": "Hydrochloric Acid",
        "cas_no": "7647-01-0",
        "category": "无机酸",
        "specification": "500ml",
        "unit": "瓶",
        "current_quantity": 8.0,
        "warning_threshold": 2.0,
        "location": "酸柜 B1",
        "hazard_level": "腐蚀",
    },
    {
        "name_cn": "硫酸",
        "name_en": "Sulfuric Acid",
        "cas_no": "7664-93-9",
        "category": "无机酸",
        "specification": "500ml",
        "unit": "瓶",
        "current_quantity": 6.0,
        "warning_threshold": 2.0,
        "location": "酸柜 B1",
        "hazard_level": "强腐蚀",
    },
    {
        "name_cn": "硝酸",
        "name_en": "Nitric Acid",
        "cas_no": "7697-37-2",
        "category": "无机酸",
        "specification": "500ml",
        "unit": "瓶",
        "current_quantity": 5.0,
        "warning_threshold": 2.0,
        "location": "酸柜 B2",
        "hazard_level": "强氧化",
    },
    {
        "name_cn": "无水乙醇",
        "name_en": "Absolute Ethanol",
        "cas_no": "64-17-5",
        "category": "有机溶剂",
        "specification": "500ml",
        "unit": "瓶",
        "current_quantity": 15.0,
        "warning_threshold": 4.0,
        "location": "有机试剂柜 A2",
        "hazard_level": "易燃",
    },
    {
        "name_cn": "BOE",
        "name_en": "Buffered Oxide Etch",
        "cas_no": "混合物",
        "category": "刻蚀液",
        "specification": "500ml",
        "unit": "瓶",
        "current_quantity": 4.0,
        "warning_threshold": 1.0,
        "location": "腐蚀品柜 C1",
        "hazard_level": "腐蚀",
    },
    {
        "name_cn": "光刻胶",
        "name_en": "Photoresist",
        "cas_no": "混合物",
        "category": "光刻材料",
        "specification": "1L",
        "unit": "瓶",
        "current_quantity": 3.0,
        "warning_threshold": 1.0,
        "location": "光刻材料冰箱 D1",
        "hazard_level": "需冷藏",
    },
    {
        "name_cn": "显影液",
        "name_en": "Developer",
        "cas_no": "混合物",
        "category": "光刻材料",
        "specification": "500ml",
        "unit": "瓶",
        "current_quantity": 5.0,
        "warning_threshold": 1.0,
        "location": "光刻材料柜 D2",
        "hazard_level": "刺激性",
    },
]


def hash_password(password: str) -> str:
    """生成 bcrypt 密码哈希，避免把管理员明文密码写入数据库。"""

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def seed_admin_user(db: Session) -> tuple[int, int]:
    """创建默认管理员账号；已存在则跳过。"""

    existing_user = db.execute(
        select(User).where(User.username == DEFAULT_ADMIN_USERNAME)
    ).scalar_one_or_none()
    if existing_user is not None:
        return 0, 1

    admin_user = User(
        username=DEFAULT_ADMIN_USERNAME,
        full_name="默认管理员",
        password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
        role="admin",
        email=None,
        phone=None,
        wechat_openid=None,
        is_active=True,
    )
    db.add(admin_user)
    return 1, 0


def seed_reagents(db: Session) -> tuple[int, int]:
    """创建测试试剂；同名试剂已存在时不重复插入。"""

    inserted_count = 0
    skipped_count = 0

    for reagent_data in TEST_REAGENTS:
        existing_reagent = db.execute(
            select(Reagent).where(Reagent.name_cn == reagent_data["name_cn"])
        ).scalar_one_or_none()
        if existing_reagent is not None:
            skipped_count += 1
            continue

        db.add(Reagent(**reagent_data))
        inserted_count += 1

    return inserted_count, skipped_count


def seed() -> None:
    """初始化数据库表和基础测试数据。"""

    init_db()

    db = SessionLocal()
    try:
        reagent_inserted, reagent_skipped = seed_reagents(db)
        user_inserted, user_skipped = seed_admin_user(db)
        db.commit()

        print("初始化测试数据完成")
        print(f"试剂：新增 {reagent_inserted} 条，跳过 {reagent_skipped} 条")
        print(f"用户：新增 {user_inserted} 条，跳过 {user_skipped} 条")
        print(f"默认管理员用户名：{DEFAULT_ADMIN_USERNAME}")
        print(f"默认管理员测试密码：{DEFAULT_ADMIN_PASSWORD}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
