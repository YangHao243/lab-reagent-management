"""试剂库存与出入库统计报表 API。

本阶段只返回 JSON 数据，方便前端后续使用 ECharts 可视化，不生成 Excel。
"""

from __future__ import annotations

import calendar
from datetime import date as Date
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import InventoryRecord, Reagent, User
from utils.timezone import now_beijing, today_beijing


router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(get_current_user)],
)


class ReportSummary(BaseModel):
    """系统总览报表。"""

    reagent_total: int = Field(..., description="试剂总数")
    total_reagents: int = Field(..., description="试剂总数，兼容旧版前端字段")
    low_stock_count: int = Field(..., description="低库存试剂数量")
    today_in_count: int = Field(..., description="今日入库次数")
    today_out_count: int = Field(..., description="今日出库次数")
    month_in_count: int = Field(..., description="本月入库次数")
    month_out_count: int = Field(..., description="本月出库次数")
    total_inventory_records: int = Field(..., description="库存流水总数")


class InventoryRecordReportItem(BaseModel):
    """报表中的库存流水记录项。"""

    id: int = Field(..., description="库存记录 ID")
    reagent_id: int = Field(..., description="试剂 ID")
    operation_type: str = Field(..., description="操作类型：in / out / adjust")
    quantity_change: float = Field(..., description="库存变化数量")
    before_quantity: float = Field(..., description="操作前库存")
    after_quantity: float = Field(..., description="操作后库存")
    reason: str | None = Field(default=None, description="操作原因")
    remark: str | None = Field(default=None, description="备注")
    created_at: datetime = Field(..., description="操作时间")


class DailyReport(BaseModel):
    """日报表响应。"""

    date: str = Field(..., description="统计日期")
    in_count: int = Field(..., description="入库次数")
    out_count: int = Field(..., description="出库次数")
    adjust_count: int = Field(..., description="校正次数")
    in_quantity_total: float = Field(..., description="入库数量合计")
    out_quantity_total: float = Field(..., description="出库数量合计")
    records: list[InventoryRecordReportItem] = Field(..., description="当天库存流水")


class DailySummaryItem(BaseModel):
    """月报中的每日统计项。"""

    date: str = Field(..., description="日期")
    in_count: int = Field(..., description="入库次数")
    out_count: int = Field(..., description="出库次数")
    in_quantity_total: float = Field(..., description="入库数量合计")
    out_quantity_total: float = Field(..., description="出库数量合计")


class MonthlyReport(BaseModel):
    """月报表响应。"""

    year: int = Field(..., description="年份")
    month: int = Field(..., description="月份")
    days: list[DailySummaryItem] = Field(..., description="每日统计数组")


class MonthlySummaryItem(BaseModel):
    """年报中的每月统计项。"""

    month: int = Field(..., description="月份")
    in_count: int = Field(..., description="入库次数")
    out_count: int = Field(..., description="出库次数")
    in_quantity_total: float = Field(..., description="入库数量合计")
    out_quantity_total: float = Field(..., description="出库数量合计")


class YearlyReport(BaseModel):
    """年报表响应。"""

    year: int = Field(..., description="年份")
    months: list[MonthlySummaryItem] = Field(..., description="每月统计数组")


class TimeSeriesPoint(BaseModel):
    """出入库时序图中的单个时间点。"""

    date: str = Field(..., description="日期、月份或年份标签")
    inbound_count: int = Field(..., description="入库次数")
    outbound_count: int = Field(..., description="出库次数")
    inbound_quantity: float = Field(..., description="入库数量合计")
    outbound_quantity: float = Field(..., description="出库数量合计")


class TimeSeriesReport(BaseModel):
    """出入库时序统计响应。"""

    period: Literal["daily", "monthly", "yearly"] = Field(..., description="统计维度")
    current: str = Field(..., description="当前统计范围")
    series: list[TimeSeriesPoint] = Field(..., description="连续时序数据")


class CalendarInventoryRecordItem(BaseModel):
    """日历视图中的库存流水记录项。"""

    id: int = Field(..., description="库存记录 ID")
    reagent_id: int = Field(..., description="试剂 ID")
    reagent_name: str = Field(..., description="试剂中文名称")
    operation_type: str = Field(..., description="操作类型：in / out / adjust")
    quantity_change: float = Field(..., description="库存变化数量")
    operator_name: str = Field(default="", description="操作人名称")
    reason: str | None = Field(default=None, description="操作原因")
    remark: str | None = Field(default=None, description="备注")
    created_at: datetime = Field(..., description="操作时间")


class CalendarDayItem(BaseModel):
    """日历视图中的每日统计项。"""

    date: str = Field(..., description="日期")
    in_count: int = Field(..., description="入库次数")
    out_count: int = Field(..., description="出库次数")
    adjust_count: int = Field(..., description="校正次数")
    in_quantity_total: float = Field(..., description="入库数量合计")
    out_quantity_total: float = Field(..., description="出库数量合计")
    records: list[CalendarInventoryRecordItem] = Field(..., description="当天库存流水")


class InventoryCalendarReport(BaseModel):
    """库存流水日历报表响应。"""

    year: int = Field(..., description="年份")
    month: int = Field(..., description="月份")
    days: list[CalendarDayItem] = Field(..., description="日历每日流水数组")


class MovementStats(BaseModel):
    """出入库统计项。"""

    label: str = Field(..., description="统计标签，例如日期或月份")
    in_count: int = Field(..., description="入库次数")
    in_quantity: float = Field(..., description="入库数量")
    out_count: int = Field(..., description="出库次数")
    out_quantity: float = Field(..., description="出库数量")
    adjust_count: int = Field(..., description="校正次数")
    adjust_quantity: float = Field(..., description="校正变化数量绝对值合计")


class TopConsumedItem(BaseModel):
    """消耗量最高试剂统计项。"""

    reagent_id: int = Field(..., description="试剂 ID")
    name_cn: str = Field(..., description="试剂中文名称")
    unit: str = Field(..., description="库存单位")
    out_count: int = Field(..., description="出库次数")
    total_consumed: float = Field(..., description="出库消耗总量")
    inbound_count: int = Field(default=0, description="入库次数")
    inbound_quantity: float = Field(default=0.0, description="入库数量")
    correction_quantity: float = Field(default=0.0, description="校正量（保留正负号）")


class CategorySummaryItem(BaseModel):
    """分类库存统计项。"""

    category: str = Field(..., description="试剂分类")
    reagent_count: int = Field(..., description="试剂数量")
    low_stock_count: int = Field(..., description="低库存数量")
    total_quantity: float = Field(..., description="当前库存总量")


def day_range(target_date: Date) -> tuple[datetime, datetime]:
    """返回某一天的起止时间，结束时间使用开区间。"""

    start_at = datetime.combine(target_date, time.min)
    end_at = start_at + timedelta(days=1)
    return start_at, end_at


def month_range(year: int, month: int) -> tuple[datetime, datetime]:
    """返回某个月的起止时间，结束时间使用开区间。"""

    start_at = datetime(year, month, 1)
    if month == 12:
        end_at = datetime(year + 1, 1, 1)
    else:
        end_at = datetime(year, month + 1, 1)
    return start_at, end_at


def year_range(year: int) -> tuple[datetime, datetime]:
    """返回某一年的起止时间，结束时间使用开区间。"""

    return datetime(year, 1, 1), datetime(year + 1, 1, 1)


def count_inventory_records(
    db: Session,
    operation_type: str,
    start_at: datetime,
    end_at: datetime,
) -> int:
    """统计指定时间范围内某类库存操作次数。"""

    stmt = (
        select(func.count(InventoryRecord.id))
        .where(InventoryRecord.operation_type == operation_type)
        .where(InventoryRecord.created_at >= start_at)
        .where(InventoryRecord.created_at < end_at)
    )
    return int(db.execute(stmt).scalar_one())


def get_records_in_range(
    db: Session,
    start_at: datetime,
    end_at: datetime,
) -> list[InventoryRecord]:
    """查询指定时间范围内的库存流水。"""

    stmt = (
        select(InventoryRecord)
        .where(InventoryRecord.created_at >= start_at)
        .where(InventoryRecord.created_at < end_at)
        .order_by(InventoryRecord.created_at.asc(), InventoryRecord.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def summarize_inventory_records(records: list[InventoryRecord]) -> dict[str, int | float]:
    """聚合库存流水，出库数量按绝对值统计。"""

    in_records = [record for record in records if record.operation_type == "in"]
    out_records = [record for record in records if record.operation_type == "out"]
    adjust_records = [record for record in records if record.operation_type == "adjust"]

    return {
        "in_count": len(in_records),
        "out_count": len(out_records),
        "adjust_count": len(adjust_records),
        "in_quantity_total": float(sum(record.quantity_change for record in in_records)),
        "out_quantity_total": float(sum(abs(record.quantity_change) for record in out_records)),
        "adjust_quantity_total": float(sum(abs(record.quantity_change) for record in adjust_records)),
    }


def build_record_item(record: InventoryRecord) -> InventoryRecordReportItem:
    """把库存流水 ORM 对象转换为报表记录项。"""

    return InventoryRecordReportItem(
        id=record.id,
        reagent_id=record.reagent_id,
        operation_type=record.operation_type,
        quantity_change=record.quantity_change,
        before_quantity=record.before_quantity,
        after_quantity=record.after_quantity,
        reason=record.reason,
        remark=record.remark,
        created_at=record.created_at,
    )


def summarize_calendar_records(
    records: list[CalendarInventoryRecordItem],
) -> dict[str, int | float]:
    """聚合日历流水记录，出库数量按绝对值统计。"""

    in_records = [record for record in records if record.operation_type == "in"]
    out_records = [record for record in records if record.operation_type == "out"]
    adjust_records = [record for record in records if record.operation_type == "adjust"]
    return {
        "in_count": len(in_records),
        "out_count": len(out_records),
        "adjust_count": len(adjust_records),
        "in_quantity_total": float(sum(record.quantity_change for record in in_records)),
        "out_quantity_total": float(sum(abs(record.quantity_change) for record in out_records)),
    }


def build_movement_stats(label: str, records: list[InventoryRecord]) -> MovementStats:
    """把库存流水聚合为入库、出库、校正统计。"""

    in_records = [record for record in records if record.operation_type == "in"]
    out_records = [record for record in records if record.operation_type == "out"]
    adjust_records = [record for record in records if record.operation_type == "adjust"]

    return MovementStats(
        label=label,
        in_count=len(in_records),
        in_quantity=sum(record.quantity_change for record in in_records),
        out_count=len(out_records),
        out_quantity=sum(abs(record.quantity_change) for record in out_records),
        adjust_count=len(adjust_records),
        adjust_quantity=sum(abs(record.quantity_change) for record in adjust_records),
    )


def build_time_series_point(label: str, records: list[InventoryRecord]) -> TimeSeriesPoint:
    """把库存流水聚合为前端曲线图使用的统一字段。"""

    stats = summarize_inventory_records(records)
    return TimeSeriesPoint(
        date=label,
        inbound_count=int(stats["in_count"]),
        outbound_count=int(stats["out_count"]),
        inbound_quantity=float(stats["in_quantity_total"]),
        outbound_quantity=float(stats["out_quantity_total"]),
    )


def validate_date_range(start_date: Date, end_date: Date) -> None:
    """校验日期范围。"""

    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="开始日期不能晚于结束日期",
        )


@router.get(
    "/summary",
    response_model=ReportSummary,
    summary="系统总览报表",
)
def get_summary(db: Session = Depends(get_db)) -> ReportSummary:
    """返回试剂总数、低库存数量以及今日/本月出入库次数。"""

    today = today_beijing()
    today_start, today_end = day_range(today)
    month_start, month_end = month_range(today.year, today.month)

    total_reagents = int(db.execute(select(func.count(Reagent.id))).scalar_one())
    low_stock_count = int(
        db.execute(
            select(func.count(Reagent.id)).where(
                Reagent.current_quantity <= Reagent.warning_threshold
            )
        ).scalar_one()
    )
    total_inventory_records = int(
        db.execute(select(func.count(InventoryRecord.id))).scalar_one()
    )

    return ReportSummary(
        reagent_total=total_reagents,
        total_reagents=total_reagents,
        low_stock_count=low_stock_count,
        today_in_count=count_inventory_records(db, "in", today_start, today_end),
        today_out_count=count_inventory_records(db, "out", today_start, today_end),
        month_in_count=count_inventory_records(db, "in", month_start, month_end),
        month_out_count=count_inventory_records(db, "out", month_start, month_end),
        total_inventory_records=total_inventory_records,
    )


@router.get(
    "/daily",
    response_model=DailyReport,
    summary="日报表",
)
def get_daily_report(
    target_date: Date | None = Query(default=None, alias="date", description="统计日期，默认今天"),
    db: Session = Depends(get_db),
) -> DailyReport:
    """返回指定日期的入库、出库、校正次数和数量。"""

    report_date = target_date or today_beijing()
    start_at, end_at = day_range(report_date)
    records = get_records_in_range(db, start_at, end_at)
    stats = summarize_inventory_records(records)
    return DailyReport(
        date=report_date.isoformat(),
        in_count=int(stats["in_count"]),
        out_count=int(stats["out_count"]),
        adjust_count=int(stats["adjust_count"]),
        in_quantity_total=float(stats["in_quantity_total"]),
        out_quantity_total=float(stats["out_quantity_total"]),
        records=[build_record_item(record) for record in records],
    )


@router.get(
    "/weekly",
    response_model=list[MovementStats],
    summary="周报表",
)
def get_weekly_report(
    start_date: Date | None = Query(default=None, description="开始日期，默认今天往前 6 天"),
    db: Session = Depends(get_db),
) -> list[MovementStats]:
    """返回连续 7 天内每天的入库/出库/校正统计。"""

    first_day = start_date or (today_beijing() - timedelta(days=6))
    results: list[MovementStats] = []

    for offset in range(7):
        current_day = first_day + timedelta(days=offset)
        start_at, end_at = day_range(current_day)
        records = get_records_in_range(db, start_at, end_at)
        results.append(build_movement_stats(current_day.isoformat(), records))

    return results


@router.get(
    "/monthly",
    response_model=MonthlyReport,
    summary="月报表",
)
def get_monthly_report(
    year: int = Query(..., ge=2000, le=2100, description="年份"),
    month: int = Query(..., ge=1, le=12, description="月份"),
    db: Session = Depends(get_db),
) -> MonthlyReport:
    """返回指定月份每日入库/出库/校正统计。"""

    day_count = calendar.monthrange(year, month)[1]
    days: list[DailySummaryItem] = []

    for day in range(1, day_count + 1):
        current_day = Date(year, month, day)
        start_at, end_at = day_range(current_day)
        records = get_records_in_range(db, start_at, end_at)
        stats = summarize_inventory_records(records)
        days.append(
            DailySummaryItem(
                date=current_day.isoformat(),
                in_count=int(stats["in_count"]),
                out_count=int(stats["out_count"]),
                in_quantity_total=float(stats["in_quantity_total"]),
                out_quantity_total=float(stats["out_quantity_total"]),
            )
        )

    return MonthlyReport(year=year, month=month, days=days)


@router.get(
    "/yearly",
    response_model=YearlyReport,
    summary="年报表",
)
def get_yearly_report(
    year: int = Query(..., ge=2000, le=2100, description="年份"),
    db: Session = Depends(get_db),
) -> YearlyReport:
    """返回指定年份每月入库/出库/校正统计。"""

    months: list[MonthlySummaryItem] = []

    for month in range(1, 13):
        start_at, end_at = month_range(year, month)
        records = get_records_in_range(db, start_at, end_at)
        stats = summarize_inventory_records(records)
        months.append(
            MonthlySummaryItem(
                month=month,
                in_count=int(stats["in_count"]),
                out_count=int(stats["out_count"]),
                in_quantity_total=float(stats["in_quantity_total"]),
                out_quantity_total=float(stats["out_quantity_total"]),
            )
        )

    return YearlyReport(year=year, months=months)


@router.get(
    "/timeseries",
    response_model=TimeSeriesReport,
    summary="出入库时序统计",
)
def get_inventory_timeseries(
    period: Literal["daily", "monthly", "yearly"] = Query(
        default="daily",
        description="统计维度：daily=按天，monthly=按月，yearly=按年",
    ),
    year: int | None = Query(default=None, ge=2000, le=2100, description="统计年份"),
    month: int | None = Query(default=None, ge=1, le=12, description="统计月份，仅按天统计时使用"),
    years: int = Query(default=5, ge=1, le=20, description="按年统计时返回的连续年份数量"),
    db: Session = Depends(get_db),
) -> TimeSeriesReport:
    """返回连续时间序列数据，供前端 ECharts 曲线图直接使用。

    daily：返回指定月份每天的数据；monthly：返回指定年份 1-12 月；
    yearly：返回以指定年份为结束点的连续年份数据。没有记录的时间点补 0。
    """

    today = today_beijing()
    report_year = year or today.year
    series: list[TimeSeriesPoint] = []

    if period == "daily":
        report_month = month or today.month
        day_count = calendar.monthrange(report_year, report_month)[1]
        for day in range(1, day_count + 1):
            current_day = Date(report_year, report_month, day)
            start_at, end_at = day_range(current_day)
            records = get_records_in_range(db, start_at, end_at)
            series.append(build_time_series_point(current_day.isoformat(), records))

        return TimeSeriesReport(
            period=period,
            current=f"{report_year}-{report_month:02d}",
            series=series,
        )

    if period == "monthly":
        for current_month in range(1, 13):
            start_at, end_at = month_range(report_year, current_month)
            records = get_records_in_range(db, start_at, end_at)
            series.append(
                build_time_series_point(f"{report_year}-{current_month:02d}", records)
            )

        return TimeSeriesReport(
            period=period,
            current=str(report_year),
            series=series,
        )

    start_year = report_year - years + 1
    for current_year in range(start_year, report_year + 1):
        start_at, end_at = year_range(current_year)
        records = get_records_in_range(db, start_at, end_at)
        series.append(build_time_series_point(str(current_year), records))

    return TimeSeriesReport(
        period=period,
        current=f"{start_year}-{report_year}",
        series=series,
    )


@router.get(
    "/inventory-calendar",
    response_model=InventoryCalendarReport,
    summary="日历式库存流水",
)
def get_inventory_calendar(
    year: int = Query(..., ge=2000, le=2100, description="年份"),
    month: int = Query(..., ge=1, le=12, description="月份"),
    reagent_id: int | None = Query(default=None, gt=0, description="按试剂 ID 筛选"),
    operation_type: Literal["in", "out", "adjust"] | None = Query(
        default=None,
        description="按操作类型筛选：in / out / adjust",
    ),
    db: Session = Depends(get_db),
) -> InventoryCalendarReport:
    """返回整月日历式库存流水，方便前端 Calendar 视图直接渲染。"""

    start_at, end_at = month_range(year, month)
    stmt = (
        select(
            InventoryRecord,
            Reagent.name_cn,
            User.full_name,
            User.username,
        )
        .join(Reagent, InventoryRecord.reagent_id == Reagent.id)
        .join(User, InventoryRecord.operator_id == User.id, isouter=True)
        .where(InventoryRecord.created_at >= start_at)
        .where(InventoryRecord.created_at < end_at)
        .order_by(InventoryRecord.created_at.asc(), InventoryRecord.id.asc())
    )

    if reagent_id is not None:
        stmt = stmt.where(InventoryRecord.reagent_id == reagent_id)

    if operation_type is not None:
        stmt = stmt.where(InventoryRecord.operation_type == operation_type)

    # 先把整月流水按日期分组，避免前端为了日历视图再做复杂整理。
    records_by_date: dict[str, list[CalendarInventoryRecordItem]] = {}
    for record, reagent_name, full_name, username in db.execute(stmt).all():
        date_key = record.created_at.date().isoformat()
        records_by_date.setdefault(date_key, []).append(
            CalendarInventoryRecordItem(
                id=record.id,
                reagent_id=record.reagent_id,
                reagent_name=reagent_name or "未知试剂",
                operation_type=record.operation_type,
                quantity_change=record.quantity_change,
                operator_name=full_name or username or "",
                reason=record.reason,
                remark=record.remark,
                created_at=record.created_at,
            )
        )

    day_count = calendar.monthrange(year, month)[1]
    days: list[CalendarDayItem] = []
    for day in range(1, day_count + 1):
        current_date = Date(year, month, day).isoformat()
        records = records_by_date.get(current_date, [])
        stats = summarize_calendar_records(records)
        days.append(
            CalendarDayItem(
                date=current_date,
                in_count=int(stats["in_count"]),
                out_count=int(stats["out_count"]),
                adjust_count=int(stats["adjust_count"]),
                in_quantity_total=float(stats["in_quantity_total"]),
                out_quantity_total=float(stats["out_quantity_total"]),
                records=records,
            )
        )

    return InventoryCalendarReport(year=year, month=month, days=days)


@router.get(
    "/top-consumed",
    response_model=list[TopConsumedItem],
    summary="消耗量最高试剂 Top N",
)
def get_top_consumed(
    start_date: Date = Query(..., description="开始日期，格式 YYYY-MM-DD"),
    end_date: Date = Query(..., description="结束日期，格式 YYYY-MM-DD"),
    limit: int = Query(default=10, ge=1, le=100, description="返回 Top N 数量"),
    db: Session = Depends(get_db),
) -> list[TopConsumedItem]:
    """返回指定时间范围内出库消耗量最高的试剂。"""

    validate_date_range(start_date, end_date)
    start_at = datetime.combine(start_date, time.min)
    end_at = datetime.combine(end_date + timedelta(days=1), time.min)

    # Conditional aggregation via case expressions; coalesce to 0.
    zero = func.coalesce(0, 0)
    _out_count = func.coalesce(
        func.sum(case((InventoryRecord.operation_type == "out", 1), else_=0)), 0
    )
    _consumed_qty = func.coalesce(
        func.sum(case((InventoryRecord.operation_type == "out",
                       func.abs(InventoryRecord.quantity_change)), else_=0)), 0.0
    )
    _in_count = func.coalesce(
        func.sum(case((InventoryRecord.operation_type == "in", 1), else_=0)), 0
    )
    _in_qty = func.coalesce(
        func.sum(case((InventoryRecord.operation_type == "in",
                       func.abs(InventoryRecord.quantity_change)), else_=0)), 0.0
    )
    # Correction keeps sign — do not use abs()
    _corr_qty = func.coalesce(
        func.sum(case((InventoryRecord.operation_type == "adjust",
                       InventoryRecord.quantity_change), else_=0.0)), 0.0
    )

    stmt = (
        select(
            Reagent.id,
            Reagent.name_cn,
            Reagent.unit,
            _out_count,
            _consumed_qty,
            _in_count,
            _in_qty,
            _corr_qty,
        )
        .join(Reagent, InventoryRecord.reagent_id == Reagent.id)
        .where(InventoryRecord.operation_type.in_(["in", "out", "adjust"]))
        .where(InventoryRecord.created_at >= start_at)
        .where(InventoryRecord.created_at < end_at)
        .group_by(Reagent.id, Reagent.name_cn, Reagent.unit)
        .order_by(_consumed_qty.desc(), _out_count.desc(), Reagent.id.asc())
        .limit(limit)
    )

    rows = db.execute(stmt).all()
    return [
        TopConsumedItem(
            reagent_id=row[0],
            name_cn=row[1],
            unit=row[2],
            out_count=int(row[3] or 0),
            total_consumed=float(row[4] or 0),
            inbound_count=int(row[5] or 0),
            inbound_quantity=float(row[6] or 0),
            correction_quantity=float(row[7] or 0),
        )
        for row in rows
    ]


@router.get(
    "/category-summary",
    response_model=list[CategorySummaryItem],
    summary="分类库存汇总",
)
def get_category_summary(db: Session = Depends(get_db)) -> list[CategorySummaryItem]:
    """返回不同分类下的试剂数量、低库存数量和库存总量。"""

    category_name = case(
        ((Reagent.category.is_(None)) | (Reagent.category == ""), "未分类"),
        else_=Reagent.category,
    )
    low_stock_case = case(
        (Reagent.current_quantity <= Reagent.warning_threshold, 1),
        else_=0,
    )

    stmt = (
        select(
            category_name,
            func.count(Reagent.id),
            func.sum(low_stock_case),
            func.coalesce(func.sum(Reagent.current_quantity), 0),
        )
        .group_by(category_name)
        .order_by(category_name.asc())
    )

    rows = db.execute(stmt).all()
    return [
        CategorySummaryItem(
            category=row[0],
            reagent_count=int(row[1] or 0),
            low_stock_count=int(row[2] or 0),
            total_quantity=float(row[3] or 0),
        )
        for row in rows
    ]


@router.get(
    "/export/inventory-records",
    summary="导出库存流水 Excel",
)
def export_inventory_records(
    start_date: Date | None = Query(default=None, description="开始日期，格式 YYYY-MM-DD"),
    end_date: Date | None = Query(default=None, description="结束日期，格式 YYYY-MM-DD"),
    operation_type: Literal["in", "out", "adjust"] | None = Query(
        default=None,
        description="操作类型：in / out / adjust",
    ),
    db: Session = Depends(get_db),
) -> FileResponse:
    """导出库存流水记录为 xlsx 文件。"""

    if start_date is not None and end_date is not None:
        validate_date_range(start_date, end_date)

    stmt = (
        select(
            InventoryRecord.id,
            InventoryRecord.reagent_id,
            Reagent.name_cn,
            InventoryRecord.operation_type,
            InventoryRecord.quantity_change,
            InventoryRecord.before_quantity,
            InventoryRecord.after_quantity,
            InventoryRecord.reason,
            InventoryRecord.remark,
            InventoryRecord.created_at,
        )
        .join(Reagent, InventoryRecord.reagent_id == Reagent.id, isouter=True)
        .order_by(InventoryRecord.id.desc())
    )

    if start_date is not None:
        stmt = stmt.where(
            InventoryRecord.created_at >= datetime.combine(start_date, time.min)
        )

    if end_date is not None:
        stmt = stmt.where(
            InventoryRecord.created_at < datetime.combine(end_date + timedelta(days=1), time.min)
        )

    if operation_type is not None:
        stmt = stmt.where(InventoryRecord.operation_type == operation_type)

    rows = db.execute(stmt).all()
    export_rows = [
        {
            "记录ID": row[0],
            "试剂ID": row[1],
            "试剂中文名": row[2] or "未知试剂",
            "操作类型": row[3],
            "变化数量": row[4],
            "操作前数量": row[5],
            "操作后数量": row[6],
            "操作原因": row[7] or "",
            "备注": row[8] or "",
            "操作时间": row[9].strftime("%Y-%m-%d %H:%M:%S") if row[9] else "",
        }
        for row in rows
    ]

    # 导出目录固定在 backend/exports，目录不存在时自动创建。
    export_dir = Path(__file__).resolve().parent / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    timestamp = now_beijing().strftime("%Y%m%d_%H%M%S")
    file_path = export_dir / f"inventory_records_{timestamp}.xlsx"

    # 使用 pandas 写入 Excel，并显式指定 openpyxl 引擎。
    df = pd.DataFrame(export_rows)
    df.to_excel(file_path, index=False, engine="openpyxl")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
