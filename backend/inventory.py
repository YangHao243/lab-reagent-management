"""库存入库、出库、校正与流水查询 API。"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from audit_logs import create_audit_log
from alerts import ensure_low_stock_alert
from database import get_db
from dependencies import get_current_user, require_roles
from models import InventoryRecord, Reagent, User
from schemas import (
    InventoryEditRequest,
    InventoryOperationRequest,
    InventoryOperationResponse,
    InventoryRecordResponse,
    ReagentStockResponse,
)


router = APIRouter(prefix="/inventory", tags=["inventory"])

VALID_REASONS = {"领料入库", "实验领用", "其他原因"}


def validate_inventory_quantity(quantity: object) -> int:
    """校验入库/出库数量必须是大于 0 的整数。

    FastAPI/Pydantic 将 JSON 中的 1.0 静默转为 int(1)，这里额外拒绝任何 float
    或非整数，确保只有纯整数能通过。
    """

    if isinstance(quantity, bool):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="数量必须为大于 0 的整数",
        )
    if isinstance(quantity, float):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="数量必须为大于 0 的整数",
        )
    try:
        int_value = int(quantity)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="数量必须为大于 0 的整数",
        ) from None
    if int_value <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="数量必须为大于 0 的整数",
        )
    return int_value


def validate_inventory_reason(reason: str | None, remark: str | None) -> None:
    """校验入库/出库原因和备注的必填规则。

    要求：
    - reason 不能为空
    - reason 只能是 领料入库 / 实验领用 / 其他原因
    - 当 reason == "其他原因" 时，remark 不能为空且不能全为空格
    """

    if not reason or not reason.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请选择原因",
        )

    reason_cleaned = reason.strip()
    if reason_cleaned not in VALID_REASONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原因类型不合法",
        )

    if reason_cleaned == "其他原因" and (not remark or not remark.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="选择其他原因时，请在备注中补充说明",
        )


def validate_operator_name(operator_name: str | None) -> str:
    """校验操作员姓名必填且非空。"""

    if not operator_name or not operator_name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入操作员姓名",
        )
    return operator_name.strip()


class InventoryAdjustRequest(InventoryOperationRequest):
    """库存校正请求。

    入库、出库的 quantity 必须大于 0；校正时 quantity 表示最终库存，允许为 0。
    """

    quantity: float = Field(..., ge=0, description="校正后的最终库存，不能小于 0")


def get_reagent_or_404(db: Session, reagent_id: int) -> Reagent:
    """按 ID 查询试剂，不存在时返回 404。"""

    reagent = db.get(Reagent, reagent_id)
    if reagent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="试剂不存在",
        )
    return reagent


def build_inventory_response(
    record: InventoryRecord,
    reagent: Reagent,
) -> dict[str, object]:
    """把库存流水记录转换为接口响应，并附带前端展示字段。"""

    data = InventoryRecordResponse.model_validate(record).model_dump()
    data["reagent_name"] = reagent.name_cn
    data["unit"] = reagent.unit
    # 操作后库存小于或等于阈值时，Web 和小程序可直接显示低库存提示。
    data["low_stock"] = record.after_quantity <= reagent.warning_threshold
    data["warning_threshold"] = reagent.warning_threshold
    return data


def build_audit_detail(
    reagent: Reagent,
    before_quantity: float,
    after_quantity: float,
    quantity_change: float,
) -> str:
    """生成库存操作日志详情。"""

    return (
        f"试剂名称：{reagent.name_cn}；"
        f"操作前数量：{before_quantity}；"
        f"操作后数量：{after_quantity}；"
        f"变化数量：{quantity_change}"
    )


def commit_inventory_change(
    db: Session,
    record: InventoryRecord,
    reagent: Reagent,
    action: str,
    detail: str,
    check_low_stock_alert: bool = False,
) -> InventoryRecord:
    """提交库存变更和操作日志，失败时统一回滚。"""

    try:
        db.add(record)
        # 操作日志与库存数量、库存流水处于同一个事务中。
        create_audit_log(
            db=db,
            user_id=record.operator_id,
            action=action,
            target_type="reagent",
            target_id=reagent.id,
            detail=detail,
        )
        if check_low_stock_alert:
            # 低库存报警只写入 AlertEvent，不在库存模块直接发送企业微信通知。
            ensure_low_stock_alert(db, reagent)
        db.commit()
        db.refresh(record)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="库存操作失败",
        ) from exc
    return record


@router.post(
    "/in",
    response_model=InventoryOperationResponse,
    summary="试剂入库",
)
def stock_in(
    payload: InventoryOperationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """试剂入库：增加当前库存并写入入库流水。"""

    validate_inventory_reason(payload.reason, payload.remark)
    validate_inventory_quantity(payload.quantity)
    operator_name = validate_operator_name(payload.operator_name)
    reagent = get_reagent_or_404(db, payload.reagent_id)
    before_quantity = reagent.current_quantity
    after_quantity = before_quantity + payload.quantity

    reagent.current_quantity = after_quantity
    record = InventoryRecord(
        reagent_id=reagent.id,
        operation_type="in",
        quantity_change=payload.quantity,
        before_quantity=before_quantity,
        after_quantity=after_quantity,
        operator_id=current_user.id,
        operator_name=operator_name,
        reason=payload.reason,
        remark=payload.remark,
    )

    record = commit_inventory_change(
        db=db,
        record=record,
        reagent=reagent,
        action="inventory_in",
        detail=build_audit_detail(
            reagent=reagent,
            before_quantity=before_quantity,
            after_quantity=after_quantity,
            quantity_change=payload.quantity,
        ),
    )
    return build_inventory_response(record, reagent)


@router.post(
    "/out",
    response_model=InventoryOperationResponse,
    summary="试剂出库",
)
def stock_out(
    payload: InventoryOperationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """试剂出库：检查库存是否足够，扣减库存并写入出库流水。"""

    validate_inventory_reason(payload.reason, payload.remark)
    validate_inventory_quantity(payload.quantity)
    operator_name = validate_operator_name(payload.operator_name)
    reagent = get_reagent_or_404(db, payload.reagent_id)
    before_quantity = reagent.current_quantity

    if before_quantity < payload.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="库存不足，无法出库",
        )

    after_quantity = before_quantity - payload.quantity
    reagent.current_quantity = after_quantity
    record = InventoryRecord(
        reagent_id=reagent.id,
        operation_type="out",
        quantity_change=-payload.quantity,
        before_quantity=before_quantity,
        after_quantity=after_quantity,
        operator_id=current_user.id,
        operator_name=operator_name,
        reason=payload.reason,
        remark=payload.remark,
    )

    record = commit_inventory_change(
        db=db,
        record=record,
        reagent=reagent,
        action="inventory_out",
        detail=build_audit_detail(
            reagent=reagent,
            before_quantity=before_quantity,
            after_quantity=after_quantity,
            quantity_change=-payload.quantity,
        ),
        check_low_stock_alert=True,
    )
    return build_inventory_response(record, reagent)


@router.post(
    "/adjust",
    response_model=InventoryOperationResponse,
    summary="库存校正",
)
def adjust_stock(
    payload: InventoryAdjustRequest,
    current_user: User = Depends(require_roles("manager", "admin", "superadmin")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """库存校正：payload.quantity 表示校正后的最终库存。"""

    reagent = get_reagent_or_404(db, payload.reagent_id)
    before_quantity = reagent.current_quantity
    after_quantity = payload.quantity
    quantity_change = after_quantity - before_quantity

    reagent.current_quantity = after_quantity
    record = InventoryRecord(
        reagent_id=reagent.id,
        operation_type="adjust",
        quantity_change=quantity_change,
        before_quantity=before_quantity,
        after_quantity=after_quantity,
        operator_id=current_user.id,
        reason=payload.reason,
        remark=payload.remark,
    )

    record = commit_inventory_change(
        db=db,
        record=record,
        reagent=reagent,
        action="inventory_adjust",
        detail=build_audit_detail(
            reagent=reagent,
            before_quantity=before_quantity,
            after_quantity=after_quantity,
            quantity_change=quantity_change,
        ),
        check_low_stock_alert=True,
    )
    return build_inventory_response(record, reagent)


@router.get(
    "/stock/{reagent_id}",
    response_model=ReagentStockResponse,
    summary="查询单个试剂库存余量",
)
def get_reagent_stock(
    reagent_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReagentStockResponse:
    """按试剂 ID 查询库存状态，供 Web 和小程序实时显示库存余量。"""

    _ = current_user
    reagent = get_reagent_or_404(db, reagent_id)
    return ReagentStockResponse(
        reagent_id=reagent.id,
        name_cn=reagent.name_cn,
        category=reagent.category,
        current_quantity=reagent.current_quantity,
        unit=reagent.unit,
        warning_threshold=reagent.warning_threshold,
        low_stock=reagent.current_quantity <= reagent.warning_threshold,
        location=reagent.location,
        hazard_level=reagent.hazard_level,
        updated_at=reagent.updated_at,
    )


@router.get(
    "/records",
    response_model=list[InventoryRecordResponse],
    summary="查询出入库记录",
)
def list_inventory_records(
    reagent_id: int | None = Query(default=None, gt=0, description="按试剂 ID 筛选"),
    operation_type: Literal["in", "out", "adjust"] | None = Query(
        default=None,
        description="按操作类型筛选：in / out / adjust",
    ),
    start_date: date | None = Query(default=None, description="开始日期，格式 YYYY-MM-DD"),
    end_date: date | None = Query(default=None, description="结束日期，格式 YYYY-MM-DD"),
    year: int | None = Query(default=None, ge=2000, le=2100, description="按年份筛选，默认当前年份"),
    skip: int = Query(default=0, ge=0, description="跳过记录数"),
    limit: int = Query(default=100, ge=1, le=500, description="返回记录数上限"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """查询库存流水，按创建时间倒序返回，附带年度显示编号。"""

    _ = current_user
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="开始日期不能晚于结束日期",
        )

    filter_year = year or date.today().year
    year_start = datetime(filter_year, 1, 1)
    year_end = datetime(filter_year + 1, 1, 1)

    stmt = select(InventoryRecord).where(
        InventoryRecord.created_at >= year_start,
        InventoryRecord.created_at < year_end,
    )

    if reagent_id is not None:
        stmt = stmt.where(InventoryRecord.reagent_id == reagent_id)

    if operation_type is not None:
        stmt = stmt.where(InventoryRecord.operation_type == operation_type)

    if start_date is not None:
        stmt = stmt.where(
            InventoryRecord.created_at >= datetime.combine(start_date, time.min)
        )

    if end_date is not None:
        stmt = stmt.where(
            InventoryRecord.created_at <= datetime.combine(end_date, time.max)
        )

    # 先按 created_at 升序获取该年份全部匹配记录，用于分配稳定的年度编号。
    year_records = list(
        db.execute(
            stmt.order_by(InventoryRecord.created_at.asc(), InventoryRecord.id.asc())
        ).scalars().all()
    )

    # 为每条记录分配 year_display_id，然后转为按时间倒序分页。
    indexed: list[dict[str, object]] = []
    for index, record in enumerate(year_records, start=1):
        data: dict[str, object] = InventoryRecordResponse.model_validate(record).model_dump()
        data["year_display_id"] = index
        indexed.append(data)

    indexed.reverse()
    return indexed[skip : skip + limit]


@router.get(
    "/records/{record_id}",
    response_model=InventoryRecordResponse,
    summary="查询单条出入库记录",
)
def get_inventory_record(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InventoryRecord:
    """按 ID 查询单条库存流水。"""

    _ = current_user
    record = db.get(InventoryRecord, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="库存记录不存在",
        )
    return record


def recalculate_reagent_inventory(db: Session, reagent_id: int) -> None:
    """重新计算指定试剂所有库存流水的 before/after 数量及当前库存。

    按 created_at asc, id asc 排序，从库存 0 开始逐条推算。
    任何一步导致库存为负时抛出 400 错误并回滚。
    """

    records = list(
        db.execute(
            select(InventoryRecord)
            .where(InventoryRecord.reagent_id == reagent_id)
            .order_by(InventoryRecord.created_at.asc(), InventoryRecord.id.asc())
        ).scalars().all()
    )

    running = 0.0
    for record in records:
        if record.operation_type == "in":
            running += record.quantity_change
        elif record.operation_type == "out":
            running += record.quantity_change
        elif record.operation_type == "adjust":
            before = running
            running = record.after_quantity
            record.before_quantity = before
            record.quantity_change = running - before
            record.after_quantity = running
            continue

        if running < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="修改或删除后库存不能为负，请检查该流水记录",
            )
        record.before_quantity = running - record.quantity_change
        record.after_quantity = running

    reagent = db.get(Reagent, reagent_id)
    if reagent is not None:
        reagent.current_quantity = running


@router.put(
    "/records/{record_id}",
    summary="编辑库存流水（仅超级管理员）",
)
def edit_inventory_record(
    record_id: int,
    payload: InventoryEditRequest,
    current_user: User = Depends(require_roles("superadmin")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """编辑库存流水的数量、原因、备注，并重算库存。"""

    _ = current_user
    validate_inventory_reason(payload.reason, payload.remark)
    validate_inventory_quantity(payload.quantity)
    operator_name = validate_operator_name(payload.operator_name)

    record = db.get(InventoryRecord, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="库存记录不存在",
        )

    try:
        if record.operation_type == "in":
            record.quantity_change = payload.quantity
        elif record.operation_type == "out":
            record.quantity_change = -payload.quantity
        else:
            record.quantity_change = payload.quantity - record.before_quantity

        record.operator_name = operator_name
        record.reason = payload.reason
        record.remark = payload.remark
        recalculate_reagent_inventory(db, record.reagent_id)
        db.commit()
        db.refresh(record)
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="编辑库存流水失败",
        ) from exc

    return build_inventory_response(record, get_reagent_or_404(db, record.reagent_id))


@router.delete(
    "/records/{record_id}",
    summary="删除库存流水（仅超级管理员）",
)
def delete_inventory_record(
    record_id: int,
    current_user: User = Depends(require_roles("superadmin")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """删除库存流水并重算该试剂所有流水的库存。"""

    _ = current_user
    record = db.get(InventoryRecord, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="库存记录不存在",
        )

    reagent_id = record.reagent_id
    try:
        db.delete(record)
        recalculate_reagent_inventory(db, reagent_id)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除库存流水失败",
        ) from exc

    return {"message": "库存流水已删除", "record_id": record_id}
