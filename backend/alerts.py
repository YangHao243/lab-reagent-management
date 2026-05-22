"""低库存和即将过期报警 API。"""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models import AlertEvent, Reagent, User
from notifications import (
    format_expiring_message,
    format_low_stock_message,
    send_wechat_work_text,
)
from schemas import AlertEventResponse, ReagentResponse
from utils.timezone import now_beijing, today_beijing


router = APIRouter(prefix="/alerts", tags=["alerts"])

ALERT_TYPE_LOW_STOCK = "low_stock"
ALERT_TYPE_EXPIRING = "即将过期"


class AlertCheckResponse(BaseModel):
    """主动报警检查响应。"""

    new_alert_count: int = Field(..., description="本次新创建的报警数量")
    alerts: list[AlertEventResponse] = Field(..., description="本次新创建的报警列表")
    notify_success: bool | None = Field(default=None, description="通知发送是否全部成功")


def get_low_stock_reagents(db: Session) -> list[Reagent]:
    """查询当前低库存试剂。"""

    stmt = (
        select(Reagent)
        .where(Reagent.current_quantity <= Reagent.warning_threshold)
        .order_by(Reagent.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def get_expiring_reagents(db: Session, days: int) -> list[Reagent]:
    """查询即将过期试剂，范围为今天到今天 + days。"""

    today = today_beijing()
    end_date = today + timedelta(days=days)
    stmt = (
        select(Reagent)
        .where(Reagent.expiry_date.is_not(None))
        .where(Reagent.expiry_date >= today)
        .where(Reagent.expiry_date <= end_date)
        .order_by(Reagent.expiry_date.asc(), Reagent.id.desc())
    )
    return list(db.execute(stmt).scalars().all())


def unresolved_alert_exists(db: Session, reagent_id: int, alert_type: str) -> bool:
    """判断同一试剂、同一类型是否已有未解决报警。"""

    stmt = (
        select(AlertEvent.id)
        .where(AlertEvent.reagent_id == reagent_id)
        .where(AlertEvent.alert_type == alert_type)
        .where(AlertEvent.is_resolved.is_(False))
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def get_alert_level_for_low_stock(reagent: Reagent) -> str:
    """根据危险等级给低库存报警设置等级，当前先做轻量判断。"""

    hazard_level = reagent.hazard_level or ""
    if any(keyword in hazard_level for keyword in ("高危", "高毒", "强氧化")):
        return "critical"
    return "warning"


def build_low_stock_alert(reagent: Reagent) -> AlertEvent:
    """创建低库存报警对象。"""

    return AlertEvent(
        reagent_id=reagent.id,
        alert_type=ALERT_TYPE_LOW_STOCK,
        level=get_alert_level_for_low_stock(reagent),
        message=(
            f"试剂 {reagent.name_cn} 当前库存 {reagent.current_quantity}{reagent.unit}，"
            f"低于或等于报警阈值 {reagent.warning_threshold}{reagent.unit}；"
            f"存放位置：{reagent.location or '未填写'}"
        ),
        is_resolved=False,
    )


def ensure_low_stock_alert(db: Session, reagent: Reagent) -> AlertEvent | None:
    """确保低库存报警存在。

    当前库存小于或等于阈值时，如果没有未解决的 low_stock 报警，则创建一条；
    如果库存未触发低库存或已有未解决报警，则返回 None。
    """

    if reagent.current_quantity > reagent.warning_threshold:
        return None

    if unresolved_alert_exists(db, reagent.id, ALERT_TYPE_LOW_STOCK):
        return None

    alert = build_low_stock_alert(reagent)
    db.add(alert)
    return alert


def build_expiring_alert(reagent: Reagent) -> AlertEvent:
    """创建即将过期报警对象。"""

    return AlertEvent(
        reagent_id=reagent.id,
        alert_type=ALERT_TYPE_EXPIRING,
        level="warning",
        message=f"试剂 {reagent.name_cn} 将于 {reagent.expiry_date} 过期",
        is_resolved=False,
    )


@router.get(
    "/low-stock",
    response_model=list[ReagentResponse],
    summary="查询低库存试剂",
)
def list_low_stock_reagents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Reagent]:
    """返回当前库存小于或等于报警阈值的试剂。"""

    _ = current_user
    return get_low_stock_reagents(db)


@router.get(
    "/expiring",
    response_model=list[ReagentResponse],
    summary="查询即将过期试剂",
)
def list_expiring_reagents(
    days: int = Query(default=30, ge=0, description="未来多少天内即将过期"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Reagent]:
    """返回有效期在今天到今天 + days 之间的试剂。"""

    _ = current_user
    return get_expiring_reagents(db, days)


@router.post(
    "/check",
    response_model=AlertCheckResponse,
    summary="主动执行报警检查",
)
def check_alerts(
    days: int = Query(default=30, ge=0, description="未来多少天内即将过期"),
    notify: bool = Query(default=False, description="是否推送企业微信通知"),
    current_user: User = Depends(require_roles("manager", "admin", "superadmin")),
    db: Session = Depends(get_db),
) -> AlertCheckResponse:
    """检查低库存和即将过期试剂，并为新报警写入 AlertEvent。"""

    _ = current_user
    new_alerts: list[AlertEvent] = []
    # 保存新报警对应的试剂，数据库提交成功后再尝试推送通知。
    pending_notifications: list[tuple[str, Reagent]] = []

    try:
        for reagent in get_low_stock_reagents(db):
            alert = ensure_low_stock_alert(db, reagent)
            if alert is None:
                continue
            new_alerts.append(alert)
            pending_notifications.append((ALERT_TYPE_LOW_STOCK, reagent))

        for reagent in get_expiring_reagents(db, days):
            if unresolved_alert_exists(db, reagent.id, ALERT_TYPE_EXPIRING):
                continue
            alert = build_expiring_alert(reagent)
            db.add(alert)
            new_alerts.append(alert)
            pending_notifications.append((ALERT_TYPE_EXPIRING, reagent))

        db.commit()

        for alert in new_alerts:
            db.refresh(alert)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="报警检查失败",
        ) from exc

    notify_success: bool | None = None
    if notify:
        notify_success = True
        for alert_type, reagent in pending_notifications:
            if alert_type == ALERT_TYPE_LOW_STOCK:
                message = format_low_stock_message(reagent)
            else:
                message = format_expiring_message(reagent)

            # 通知失败不影响已创建的报警，只在返回值中标记。
            if not send_wechat_work_text(message):
                notify_success = False

    return AlertCheckResponse(
        new_alert_count=len(new_alerts),
        alerts=[
            AlertEventResponse.model_validate(alert)
            for alert in new_alerts
        ],
        notify_success=notify_success,
    )


@router.get(
    "/events",
    response_model=list[AlertEventResponse],
    summary="查询报警事件",
)
def list_alert_events(
    is_resolved: bool | None = Query(default=None, description="是否已处理"),
    alert_type: str | None = Query(default=None, description="报警类型"),
    year: int | None = Query(default=None, ge=2000, le=2100, description="按年份筛选，默认当前年份"),
    skip: int = Query(default=0, ge=0, description="跳过记录数"),
    limit: int = Query(default=100, ge=1, le=500, description="返回记录数上限"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """查询报警事件，按创建时间倒序返回，附带年度显示编号。"""

    _ = current_user

    filter_year = year or today_beijing().year
    year_start = datetime(filter_year, 1, 1)
    year_end = datetime(filter_year + 1, 1, 1)

    stmt = select(AlertEvent).where(
        AlertEvent.created_at >= year_start,
        AlertEvent.created_at < year_end,
    )

    if is_resolved is not None:
        stmt = stmt.where(AlertEvent.is_resolved == is_resolved)

    if alert_type:
        stmt = stmt.where(AlertEvent.alert_type == alert_type.strip())

    # 按 created_at 升序获取该年份全部匹配记录，分配稳定的年度编号。
    year_records = list(
        db.execute(
            stmt.order_by(AlertEvent.created_at.asc(), AlertEvent.id.asc())
        ).scalars().all()
    )

    indexed: list[dict[str, object]] = []
    for index, record in enumerate(year_records, start=1):
        data: dict[str, object] = AlertEventResponse.model_validate(record).model_dump()
        data["year_display_id"] = index
        indexed.append(data)

    indexed.reverse()
    return indexed[skip : skip + limit]


@router.put(
    "/events/{alert_id}/resolve",
    response_model=AlertEventResponse,
    summary="处理报警事件",
)
def resolve_alert_event(
    alert_id: int,
    current_user: User = Depends(require_roles("manager", "admin", "superadmin")),
    db: Session = Depends(get_db),
) -> AlertEvent:
    """将指定报警标记为已处理。"""

    _ = current_user
    alert = db.get(AlertEvent, alert_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="报警事件不存在",
        )

    alert.is_resolved = True
    alert.resolved_at = now_beijing()

    try:
        db.commit()
        db.refresh(alert)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="处理报警事件失败",
        ) from exc

    return alert


class BatchHandleResponse(BaseModel):
    """批量处理报警响应。"""

    handled_count: int = Field(..., description="本次处理的报警数量")
    message: str = Field(..., description="处理结果描述")


@router.post(
    "/handle-all",
    response_model=BatchHandleResponse,
    summary="一键批量处理所有未处理报警事件",
)
def batch_handle_alerts(
    current_user: User = Depends(require_roles("manager", "admin", "superadmin")),
    db: Session = Depends(get_db),
) -> BatchHandleResponse:
    """将所有未处理报警事件统一标记为已处理。"""

    _ = current_user
    stmt = select(AlertEvent).where(AlertEvent.is_resolved.is_(False))
    unresolved_alerts = list(db.execute(stmt).scalars().all())

    if not unresolved_alerts:
        return BatchHandleResponse(
            handled_count=0,
            message="当前没有需要处理的报警事件",
        )

    now = now_beijing()
    for alert in unresolved_alerts:
        alert.is_resolved = True
        alert.resolved_at = now

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="批量处理报警事件失败",
        ) from exc

    handled_count = len(unresolved_alerts)
    return BatchHandleResponse(
        handled_count=handled_count,
        message=f"已批量处理 {handled_count} 条报警事件",
    )
