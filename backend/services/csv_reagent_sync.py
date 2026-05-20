"""CSV 试剂主数据导入服务。"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Reagent


FILE_COLUMN_MAPPING: dict[str, str] = {
    "试剂中文名": "name_cn",
    "试剂英文名": "name_en",
    "CAS号": "cas_no",
    "分类": "category",
    "规格": "specification",
    "单位": "unit",
    "当前数量": "current_quantity",
    "预警阈值": "warning_threshold",
    "存放位置": "location",
    "供应商": "supplier",
    "危险等级": "hazard_level",
    "有效期": "expiry_date",
    "备注": "remark",
}


def is_blank(value: Any) -> bool:
    """判断单元格是否为空。"""

    return value is None or pd.isna(value) or str(value).strip() == ""


def clean_text(value: Any) -> str | None:
    """清理文本字段。"""

    if is_blank(value):
        return None
    return str(value).strip()


def clean_float(value: Any) -> float:
    """清理数量字段。"""

    if is_blank(value):
        return 0.0
    return float(value)


def clean_date(value: Any) -> date | None:
    """清理日期字段。"""

    if is_blank(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError("有效期格式不正确")
    return parsed.date()


def normalize_reagent_row(raw_row: dict[str, Any]) -> dict[str, Any]:
    """将中文列名行数据映射为 Reagent 字段。"""

    reagent_data: dict[str, Any] = {}
    for column_name, field_name in FILE_COLUMN_MAPPING.items():
        if column_name not in raw_row:
            continue
        value = raw_row[column_name]
        if field_name in {"current_quantity", "warning_threshold"}:
            reagent_data[field_name] = clean_float(value)
        elif field_name == "expiry_date":
            reagent_data[field_name] = clean_date(value)
        else:
            reagent_data[field_name] = clean_text(value)

    if not reagent_data.get("name_cn"):
        raise ValueError("试剂中文名不能为空")

    reagent_data.setdefault("unit", "瓶")
    reagent_data.setdefault("current_quantity", 0.0)
    reagent_data.setdefault("warning_threshold", 10.0)
    return reagent_data


def read_reagent_rows_from_csv(content: bytes) -> tuple[list[dict[str, Any]], int]:
    """读取 CSV 主数据。"""

    dataframe = pd.read_csv(BytesIO(content), encoding="utf-8-sig")
    rows: list[dict[str, Any]] = []
    failed_count = 0
    for raw_row in dataframe.to_dict(orient="records"):
        try:
            rows.append(normalize_reagent_row(raw_row))
        except (TypeError, ValueError):
            failed_count += 1
    return rows, failed_count


def upsert_reagent_rows(db: Session, rows: list[dict[str, Any]]) -> tuple[int, int, int]:
    """按 CAS 号优先、中文名兜底新增或更新试剂。"""

    created_count = 0
    updated_count = 0
    failed_count = 0

    for row in rows:
        try:
            cas_no = clean_text(row.get("cas_no"))
            name_cn = clean_text(row.get("name_cn"))
            if cas_no:
                stmt = select(Reagent).where(Reagent.cas_no == cas_no)
            else:
                stmt = select(Reagent).where(Reagent.name_cn == name_cn)

            reagent = db.execute(stmt).scalar_one_or_none()
            if reagent is None:
                db.add(Reagent(**row))
                created_count += 1
                continue

            for field_name, value in row.items():
                setattr(reagent, field_name, value)
            updated_count += 1
        except Exception:
            failed_count += 1

    return created_count, updated_count, failed_count
