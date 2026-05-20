"""初始化 Excel 试剂库存表中的 19 种预置试剂。

运行方式：
    python seed_excel_reagents.py

注意：
    脚本会自动为旧版 SQLite 的 reagents 表补齐新增主数据字段，不会删除或重建数据库。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from database import SessionLocal, engine, init_db
from models import Reagent


REQUIRED_REAGENT_COLUMNS = {
    "standard_name",
    "purity_grade",
    "alias_name",
    "display_order",
    "is_preset",
}


# SQLite 旧库迁移语句：只补新增列，不改已有列，也不清空历史数据。
REAGENT_COLUMN_MIGRATIONS = {
    "standard_name": "ALTER TABLE reagents ADD COLUMN standard_name VARCHAR(200)",
    "purity_grade": "ALTER TABLE reagents ADD COLUMN purity_grade VARCHAR(100)",
    "alias_name": "ALTER TABLE reagents ADD COLUMN alias_name VARCHAR(300)",
    "display_order": "ALTER TABLE reagents ADD COLUMN display_order INTEGER NOT NULL DEFAULT 0",
    "is_preset": "ALTER TABLE reagents ADD COLUMN is_preset BOOLEAN NOT NULL DEFAULT 0",
}


# 2026 年化学试剂库存管理 Excel 第 2 行中的 19 种试剂主数据。
EXCEL_REAGENTS: list[dict[str, Any]] = [
    {
        "name_cn": "丙酮",
        "name_en": "Acetone",
        "standard_name": "丙酮",
        "purity_grade": "MOS",
        "alias_name": None,
        "category": "有机溶剂",
        "hazard_level": None,
    },
    {
        "name_cn": "无水乙醇",
        "name_en": "Anhydrous Ethanol",
        "standard_name": "无水乙醇",
        "purity_grade": "MOS",
        "alias_name": None,
        "category": "有机溶剂",
        "hazard_level": None,
    },
    {
        "name_cn": "异丙醇",
        "name_en": "Isopropanol (IPA)",
        "standard_name": "异丙醇",
        "purity_grade": "MOS",
        "alias_name": None,
        "category": "有机溶剂",
        "hazard_level": None,
    },
    {
        "name_cn": "清洗剂3 (三氯乙烯)",
        "name_en": "Trichloroethylene (TCE)",
        "standard_name": "清洗剂3",
        "purity_grade": "AR",
        "alias_name": "三氯乙烯",
        "category": "清洗剂",
        "hazard_level": "有毒卤代清洗剂",
    },
    {
        "name_cn": "清洗剂4 (n甲基吡咯烷酮)",
        "name_en": "N-Methyl-2-pyrrolidone (NMP)",
        "standard_name": "清洗剂4",
        "purity_grade": "MOS",
        "alias_name": "n甲基吡咯烷酮",
        "category": "清洗剂",
        "hazard_level": None,
    },
    {
        "name_cn": "双氧水",
        "name_en": "Hydrogen Peroxide",
        "standard_name": "双氧水",
        "purity_grade": None,
        "alias_name": "过氧化氢",
        "category": "氧化剂",
        "hazard_level": None,
    },
    {
        "name_cn": "氟化铵",
        "name_en": "Ammonium Fluoride",
        "standard_name": "氟化铵",
        "purity_grade": None,
        "alias_name": None,
        "category": "含氟盐",
        "hazard_level": None,
    },
    {
        "name_cn": "氨水",
        "name_en": "Ammonia Solution",
        "standard_name": "氨水",
        "purity_grade": None,
        "alias_name": None,
        "category": "碱类",
        "hazard_level": None,
    },
    {
        "name_cn": "盐酸",
        "name_en": "Hydrochloric Acid",
        "standard_name": "盐酸",
        "purity_grade": None,
        "alias_name": None,
        "category": "酸类",
        "hazard_level": "腐蚀性",
    },
    {
        "name_cn": "硫酸",
        "name_en": "Sulfuric Acid",
        "standard_name": "硫酸",
        "purity_grade": None,
        "alias_name": None,
        "category": "酸类",
        "hazard_level": "强腐蚀性",
    },
    {
        "name_cn": "硝酸",
        "name_en": "Nitric Acid",
        "standard_name": "硝酸",
        "purity_grade": None,
        "alias_name": None,
        "category": "酸类",
        "hazard_level": "氧化性强酸",
    },
    {
        "name_cn": "磷酸",
        "name_en": "Phosphoric Acid",
        "standard_name": "磷酸",
        "purity_grade": None,
        "alias_name": None,
        "category": "酸类",
        "hazard_level": None,
    },
    {
        "name_cn": "甲酸",
        "name_en": "Formic Acid",
        "standard_name": "甲酸",
        "purity_grade": None,
        "alias_name": None,
        "category": "酸类",
        "hazard_level": None,
    },
    {
        "name_cn": "氢氟酸",
        "name_en": "Hydrofluoric Acid",
        "standard_name": "氢氟酸",
        "purity_grade": None,
        "alias_name": None,
        "category": "酸类",
        "hazard_level": "高危腐蚀性",
    },
    {
        "name_cn": "三氯甲烷",
        "name_en": "Chloroform",
        "standard_name": "三氯甲烷",
        "purity_grade": "AR",
        "alias_name": "氯仿",
        "category": "有机溶剂",
        "hazard_level": "有毒卤代溶剂",
    },
    {
        "name_cn": "重铬酸钾",
        "name_en": "Potassium Dichromate",
        "standard_name": "重铬酸钾",
        "purity_grade": None,
        "alias_name": None,
        "category": "氧化剂",
        "hazard_level": "强氧化性/高毒",
    },
    {
        "name_cn": "溴化氢",
        "name_en": "Hydrogen Bromide",
        "standard_name": "溴化氢",
        "purity_grade": None,
        "alias_name": None,
        "category": "酸类",
        "hazard_level": None,
    },
    {
        "name_cn": "一水合柠檬酸",
        "name_en": "Citric Acid Monohydrate",
        "standard_name": "一水合柠檬酸",
        "purity_grade": None,
        "alias_name": None,
        "category": "酸类",
        "hazard_level": None,
    },
    {
        "name_cn": "甲醇",
        "name_en": "Methanol",
        "standard_name": "甲醇",
        "purity_grade": None,
        "alias_name": None,
        "category": "有机溶剂",
        "hazard_level": "有毒",
    },
]


def ensure_reagent_columns() -> None:
    """检查当前数据库是否已经包含 Reagent 新增主数据字段。"""

    existing_columns = {
        column["name"] for column in inspect(engine).get_columns(Reagent.__tablename__)
    }
    missing_columns = sorted(REQUIRED_REAGENT_COLUMNS - existing_columns)
    if missing_columns:
        raise RuntimeError(
            "当前数据库缺少 Reagent 新字段："
            f"{', '.join(missing_columns)}。自动迁移未成功，请检查数据库文件权限。"
        )


def migrate_reagent_columns() -> None:
    """为旧版 SQLite 数据库自动补齐 Reagent 新增字段。

    只执行 ALTER TABLE ADD COLUMN，不删除、不重建表，因此会保留已有库存、
    出入库流水、报警事件等历史数据。
    """

    inspector = inspect(engine)
    existing_columns = {
        column["name"] for column in inspector.get_columns(Reagent.__tablename__)
    }
    missing_columns = [
        column_name
        for column_name in REAGENT_COLUMN_MIGRATIONS
        if column_name not in existing_columns
    ]

    if not missing_columns:
        print("Reagent 表字段已完整，无需迁移")
        return

    with engine.begin() as connection:
        for column_name in missing_columns:
            connection.execute(text(REAGENT_COLUMN_MIGRATIONS[column_name]))
            print(f"已补齐 Reagent 字段：{column_name}")


def build_reagent_data(index: int, reagent_data: dict[str, Any]) -> dict[str, Any]:
    """补齐预置试剂的默认库存字段。"""

    return {
        **reagent_data,
        "display_order": index,
        "is_preset": True,
        "unit": "瓶",
        "current_quantity": 0.0,
        "warning_threshold": 1.0,
        "location": "待补充",
    }


def find_existing_reagent(db: Session, reagent_data: dict[str, Any]) -> Reagent | None:
    """按 name_cn 精确匹配预置试剂；未匹配到时以 standard_name 兜底。

    当用户修改了 name_cn（例如从"清洗剂3#（三氯乙烯）（AR）"改为
    "清洗剂3 (三氯乙烯)"）后，seed 仍能通过 standard_name 找到同一条记录，
    避免重复插入。
    """

    # 第一优先级：按当前 name_cn 精确匹配。
    name_cn = reagent_data.get("name_cn", "")
    if name_cn:
        reagent = db.execute(
            select(Reagent).where(Reagent.name_cn == name_cn)
        ).scalar_one_or_none()
        if reagent is not None:
            return reagent

    # 第二优先级：按 standard_name + is_preset 匹配。
    standard_name = reagent_data.get("standard_name")
    if standard_name:
        reagent = db.execute(
            select(Reagent).where(
                Reagent.standard_name == standard_name,
                Reagent.is_preset.is_(True),
            )
        ).scalar_one_or_none()
        if reagent is not None:
            return reagent

    # 第三优先级：按 alias_name + is_preset 匹配。
    alias_name = reagent_data.get("alias_name")
    if alias_name:
        reagent = db.execute(
            select(Reagent).where(
                Reagent.alias_name == alias_name,
                Reagent.is_preset.is_(True),
            )
        ).scalar_one_or_none()
        if reagent is not None:
            return reagent

    return None


def seed_excel_reagents(db: Session) -> tuple[int, int, int]:
    """新增或更新 19 种 Excel 预置试剂。"""

    inserted_count = 0
    updated_count = 0
    skipped_count = 0

    for index, reagent_data in enumerate(EXCEL_REAGENTS, start=1):
        full_data = build_reagent_data(index, reagent_data)
        existing_reagent = find_existing_reagent(db, full_data)

        if existing_reagent is None:
            db.add(Reagent(**full_data))
            inserted_count += 1
            continue

        changed = False
        # 同名试剂已存在时，只更新主数据相关字段和预置标记，不覆盖当前库存。
        for field_name in (
            "category",
            "hazard_level",
            "name_en",
            "standard_name",
            "purity_grade",
            "alias_name",
            "display_order",
            "is_preset",
        ):
            new_value = full_data[field_name]
            if getattr(existing_reagent, field_name) != new_value:
                setattr(existing_reagent, field_name, new_value)
                changed = True

        if changed:
            updated_count += 1
        else:
            skipped_count += 1

    return inserted_count, updated_count, skipped_count


def seed() -> None:
    """初始化表结构，并写入 Excel 预置试剂主数据。"""

    init_db()
    migrate_reagent_columns()
    ensure_reagent_columns()

    db = SessionLocal()
    try:
        inserted_count, updated_count, skipped_count = seed_excel_reagents(db)
        db.commit()

        print("Excel 预置试剂初始化完成")
        print(f"新增数量：{inserted_count}")
        print(f"更新数量：{updated_count}")
        print(f"跳过数量：{skipped_count}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
