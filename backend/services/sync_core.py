"""统一同步核心服务。

Provider 只负责把外部数据转换为 NormalizedInventoryRecord；
实际写入数据库、库存计算、同步日志由本模块统一处理。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import InventoryRecord, Reagent, SyncLog


OperationType = Literal["in", "out"]


@dataclass
class SyncErrorItem:
    """同步导入错误。"""

    sheet: str | None
    row: int | None
    reagent: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """转换为接口响应字典。"""

        return {
            "sheet": self.sheet,
            "row": self.row,
            "reagent": self.reagent,
            "reason": self.reason,
        }


@dataclass
class NormalizedInventoryRecord:
    """统一库存流水中间结构。"""

    year: int
    month: int
    event_date: date
    reagent_name: str
    operation_text: str
    operation_type: OperationType
    quantity: float
    operator: str
    remark: str | None
    source: str
    source_sheet: str | None = None
    source_row: int | None = None
    source_col: int | None = None
    source_hash: str | None = None


@dataclass
class SyncImportResult:
    """统一导入结果。"""

    created: int = 0
    skipped: int = 0
    failed: int = 0
    created_reagents: int = 0
    updated_reagents: int = 0
    monthly_counts: dict[str, int] = field(default_factory=dict)
    errors: list[SyncErrorItem] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """只要流程完成即视为成功，行级失败通过 failed/errors 表达。"""

        return True

    @property
    def message(self) -> str:
        """生成统一导入摘要。"""

        return f"导入完成，新增 {self.created} 条，跳过 {self.skipped} 条，失败 {self.failed} 条"

    def add_error(
        self,
        sheet: str | None,
        row: int | None,
        reagent: str | None,
        reason: str,
    ) -> None:
        """记录行级错误。"""

        self.failed += 1
        self.errors.append(SyncErrorItem(sheet=sheet, row=row, reagent=reagent, reason=reason))

    def to_response(self, message: str | None = None, log_id: int | None = None) -> dict[str, Any]:
        """转换为接口响应。"""

        data = {
            "success": self.success,
            "message": message or self.message,
            "created": self.created,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": [error.to_dict() for error in self.errors],
            "created_reagents": self.created_reagents,
            "updated_reagents": self.updated_reagents,
            "monthly_counts": self.monthly_counts,
        }
        if log_id is not None:
            data["log_id"] = log_id
        return data

    def to_detail_json(self) -> str:
        """转换为同步日志明细 JSON。"""

        return json.dumps(
            {
                "created": self.created,
                "skipped": self.skipped,
                "failed": self.failed,
                "created_reagents": self.created_reagents,
                "updated_reagents": self.updated_reagents,
                "errors": [error.to_dict() for error in self.errors[:200]],
                "monthly_counts": self.monthly_counts,
            },
            ensure_ascii=False,
        )


def canonical_text(value: str | None) -> str:
    """用于试剂名称弱匹配的规范化文本。"""

    if not value:
        return ""
    return (
        value.lower()
        .replace(" ", "")
        .replace("\t", "")
        .replace("#", "")
        .replace("（", "(")
        .replace("）", ")")
    )


def parse_reagent_name(raw_name: str) -> tuple[str, str | None, str | None]:
    """从试剂显示名提取标准名称、纯度和别名。"""

    name = raw_name.strip()
    parts = re.findall(r"[（(]([^）)]+)[）)]", name)
    base_name = re.sub(r"[（(][^）)]+[）)]", "", name).strip()
    purity_grade: str | None = None
    alias_parts: list[str] = []

    for part in parts:
        cleaned = part.strip()
        if cleaned.upper() in {"MOS", "AR", "GR", "CP"}:
            purity_grade = cleaned.upper()
        else:
            alias_parts.append(cleaned)

    standard_name = base_name or name
    alias_name = "；".join(alias_parts) if alias_parts else None
    return standard_name, purity_grade, alias_name


def build_source_hash(record: NormalizedInventoryRecord) -> str:
    """生成标准去重哈希。"""

    raw = "|".join(
        [
            record.source,
            record.source_sheet or "",
            str(record.source_row or ""),
            str(record.source_col or ""),
            record.reagent_name.strip(),
            record.operation_type,
            f"{record.quantity:g}",
            record.operator.strip(),
            record.event_date.isoformat(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ImportService:
    """统一导入服务，负责标准流水入库和库存更新。"""

    def __init__(self, db: Session, operator_id: int | None = None):
        self.db = db
        self.operator_id = operator_id

    def import_records(self, records: list[NormalizedInventoryRecord]) -> SyncImportResult:
        """导入标准化库存流水，不主动提交事务。"""

        result = SyncImportResult()
        seen_hashes: set[str] = set()

        for record in records:
            self._import_one_record(record, result, seen_hashes)

        return result

    def _import_one_record(
        self,
        record: NormalizedInventoryRecord,
        result: SyncImportResult,
        seen_hashes: set[str],
    ) -> None:
        """导入单条标准化流水。"""

        if not record.reagent_name.strip():
            result.add_error(record.source_sheet, record.source_row, None, "试剂名称不能为空")
            return
        if record.operation_type not in {"in", "out"}:
            result.add_error(
                record.source_sheet,
                record.source_row,
                record.reagent_name,
                "操作类型必须为 in 或 out",
            )
            return
        if record.quantity <= 0:
            result.add_error(
                record.source_sheet,
                record.source_row,
                record.reagent_name,
                "数量必须大于 0",
            )
            return
        if not record.operator.strip():
            result.add_error(
                record.source_sheet,
                record.source_row,
                record.reagent_name,
                "操作人不能为空",
            )
            return

        source_hash = record.source_hash or build_source_hash(record)
        if source_hash in seen_hashes:
            result.skipped += 1
            return

        existing_record = self.db.execute(
            select(InventoryRecord.id).where(InventoryRecord.source_hash == source_hash)
        ).scalar_one_or_none()
        if existing_record is not None:
            seen_hashes.add(source_hash)
            result.skipped += 1
            return

        reagent = self._find_or_create_reagent(record.reagent_name, result)
        before_quantity = reagent.current_quantity
        quantity_change = record.quantity if record.operation_type == "in" else -record.quantity
        after_quantity = before_quantity + quantity_change
        if after_quantity < 0:
            result.add_error(
                record.source_sheet,
                record.source_row,
                record.reagent_name,
                "库存不足，无法导入领取记录",
            )
            return

        reagent.current_quantity = after_quantity
        inventory_record = InventoryRecord(
            reagent_id=reagent.id,
            operation_type=record.operation_type,
            quantity_change=quantity_change,
            before_quantity=before_quantity,
            after_quantity=after_quantity,
            operator_id=self.operator_id,
            operator_name=record.operator.strip(),
            reason="领料入库" if record.operation_type == "in" else "实验领用",
            remark=record.remark,
            event_date=record.event_date,
            source=record.source,
            source_sheet=record.source_sheet,
            source_row=record.source_row,
            source_col=record.source_col,
            source_hash=source_hash,
            created_at=datetime.combine(record.event_date, time.min),
        )
        self.db.add(inventory_record)
        seen_hashes.add(source_hash)
        result.created += 1

    def _find_or_create_reagent(
        self,
        raw_name: str,
        result: SyncImportResult,
    ) -> Reagent:
        """按名称、标准名称、别名查找或创建试剂。"""

        standard_name, purity_grade, alias_name = parse_reagent_name(raw_name)
        candidates = list(self.db.execute(select(Reagent)).scalars().all())
        raw_canonical = canonical_text(raw_name)
        standard_canonical = canonical_text(standard_name)
        alias_canonical = canonical_text(alias_name)

        for reagent in candidates:
            names = {
                canonical_text(reagent.name_cn),
                canonical_text(reagent.standard_name),
                canonical_text(reagent.alias_name),
            }
            if raw_canonical in names or standard_canonical in names or (
                alias_canonical and alias_canonical in names
            ):
                changed = False
                if not reagent.standard_name and standard_name:
                    reagent.standard_name = standard_name
                    changed = True
                if not reagent.purity_grade and purity_grade:
                    reagent.purity_grade = purity_grade
                    changed = True
                if not reagent.alias_name and alias_name:
                    reagent.alias_name = alias_name
                    changed = True
                if changed:
                    result.updated_reagents += 1
                return reagent

        reagent = Reagent(
            name_cn=standard_name,
            standard_name=standard_name,
            purity_grade=purity_grade,
            alias_name=alias_name,
            unit="瓶",
            current_quantity=0.0,
            warning_threshold=1.0,
            is_preset=False,
        )
        self.db.add(reagent)
        self.db.flush()
        result.created_reagents += 1
        return reagent


class ExportService:
    """统一导出服务，负责从数据库生成标准宽表行。"""

    def __init__(self, db: Session):
        self.db = db

    def export_rows(self, year: int) -> list[dict[str, Any]]:
        """生成便于 Mock/真实腾讯文档写回的宽表行。"""

        records = list(
            self.db.execute(
                select(InventoryRecord)
                .where(InventoryRecord.operation_type.in_(["in", "out"]))
                .order_by(InventoryRecord.created_at.asc(), InventoryRecord.id.asc())
            ).scalars().all()
        )
        rows: list[dict[str, Any]] = []
        for record in records:
            event_date = record.event_date or record.created_at.date()
            if event_date.year != year:
                continue
            rows.append(
                {
                    "year": event_date.year,
                    "month": event_date.month,
                    "event_date": event_date.isoformat(),
                    "reagent_id": record.reagent_id,
                    "reagent_name": record.reagent.name_cn if record.reagent else None,
                    "operation_text": "入库" if record.operation_type == "in" else "领取",
                    "operation_type": record.operation_type,
                    "quantity": abs(record.quantity_change),
                    "operator": record.operator_name,
                    "remark": record.remark,
                    "source": record.source,
                    "source_sheet": record.source_sheet,
                    "source_row": record.source_row,
                    "source_col": record.source_col,
                    "source_hash": record.source_hash,
                }
            )
        return rows


class SyncLogService:
    """统一同步日志服务。"""

    def __init__(self, db: Session):
        self.db = db

    def create_log(
        self,
        source: str,
        sync_type: str,
        status_value: str,
        message: str,
        detail: dict[str, Any] | str | None = None,
    ) -> SyncLog:
        """创建同步日志，不主动提交事务。"""

        if isinstance(detail, str):
            detail_json = detail
        elif detail is None:
            detail_json = None
        else:
            detail_json = json.dumps(detail, ensure_ascii=False)

        sync_log = SyncLog(
            source=source,
            sync_type=sync_type,
            status=status_value,
            message=message,
            detail_json=detail_json,
        )
        self.db.add(sync_log)
        self.db.flush()
        return sync_log
