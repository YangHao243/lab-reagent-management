"""基础操作日志模块。"""

from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_roles
from models import AuditLog


router = APIRouter(
    prefix="/audit-logs",
    tags=["audit-logs"],
    dependencies=[Depends(require_roles("admin", "superadmin"))],
)


class AuditLogResponse(BaseModel):
    """操作日志响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="日志 ID")
    user_id: int | None = Field(default=None, description="操作用户 ID")
    action: str = Field(..., description="操作动作")
    target_type: str | None = Field(default=None, description="操作对象类型")
    target_id: int | None = Field(default=None, description="操作对象 ID")
    detail: str | None = Field(default=None, description="操作详情")
    created_at: datetime = Field(..., description="创建时间")


def create_audit_log(
    db: Session,
    user_id: int | None,
    action: str,
    target_type: str | None,
    target_id: int | None,
    detail: str | None,
) -> AuditLog:
    """创建操作日志，供其他模块在同一个事务中调用。

    本函数只负责 add 和 flush，不主动 commit；调用方应在业务操作完成后统一提交。
    """

    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
    db.add(audit_log)
    db.flush()
    return audit_log


@router.get(
    "/",
    response_model=list[AuditLogResponse],
    summary="查询操作日志",
)
def list_audit_logs(
    user_id: int | None = Query(default=None, gt=0, description="按操作用户 ID 筛选"),
    target_type: str | None = Query(default=None, description="按操作对象类型筛选"),
    start_date: date | None = Query(default=None, description="开始日期，格式 YYYY-MM-DD"),
    end_date: date | None = Query(default=None, description="结束日期，格式 YYYY-MM-DD"),
    skip: int = Query(default=0, ge=0, description="跳过记录数"),
    limit: int = Query(default=100, ge=1, le=500, description="返回记录数上限"),
    db: Session = Depends(get_db),
) -> list[AuditLog]:
    """查询操作日志，结果按 ID 倒序排列。"""

    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="开始日期不能晚于结束日期",
        )

    stmt = select(AuditLog)

    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)

    if target_type:
        stmt = stmt.where(AuditLog.target_type == target_type.strip())

    if start_date is not None:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(start_date, time.min))

    if end_date is not None:
        stmt = stmt.where(AuditLog.created_at <= datetime.combine(end_date, time.max))

    stmt = stmt.order_by(AuditLog.id.desc()).offset(skip).limit(limit)

    try:
        return list(db.execute(stmt).scalars().all())
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="查询操作日志失败",
        ) from exc
