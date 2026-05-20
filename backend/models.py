"""数据库 ORM 模型定义。

本文件只描述数据库表结构和模型关系，不包含入库、出库、报警等业务逻辑。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    """系统用户表。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), index=True, nullable=False, default="viewer")
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    wechat_openid: Mapped[str | None] = mapped_column(String(128), unique=True, index=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, index=True, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class Reagent(Base):
    """化学试剂基础信息与当前库存表。"""

    __tablename__ = "reagents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name_cn: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    cas_no: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    # Excel 主数据迁移补充字段，用于保留标准名称、别名、纯度和预置排序信息。
    standard_name: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    purity_grade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    alias_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_preset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    category: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    specification: Mapped[str | None] = mapped_column(String(200), nullable=True)
    unit: Mapped[str] = mapped_column(String(50), nullable=False, default="瓶")
    current_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    warning_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    location: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    supplier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    hazard_level: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    msds_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # 与库存流水表建立一对多关系。
    inventory_records: Mapped[list[InventoryRecord]] = relationship(
        "InventoryRecord",
        back_populates="reagent",
    )


class InventoryRecord(Base):
    """库存变动记录表，operation_type 使用 in / out / adjust。"""

    __tablename__ = "inventory_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    reagent_id: Mapped[int] = mapped_column(ForeignKey("reagents.id"), index=True, nullable=False)
    operation_type: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    quantity_change: Mapped[float] = mapped_column(Float, nullable=False)
    before_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    after_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    operator_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 本地 Excel/CSV 同步来源字段：用于记录历史表格来源和幂等去重。
    event_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_col: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # 与试剂表建立多对一关系。
    reagent: Mapped[Reagent] = relationship(
        "Reagent",
        back_populates="inventory_records",
    )


class AlertEvent(Base):
    """报警事件表，alert_type 可表示低库存、即将过期、异常消耗。"""

    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    reagent_id: Mapped[int] = mapped_column(ForeignKey("reagents.id"), index=True, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    level: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="warning")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, index=True, nullable=False, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False, default=datetime.utcnow)


class SyncLog(Base):
    """外部同步日志表，第一阶段主要为后续腾讯文档同步预留。"""

    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    sync_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 同步明细 JSON 字符串，保存导入统计和错误摘要，避免第一阶段新增复杂表结构。
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False, default=datetime.utcnow)


class TencentDocsToken(Base):
    """腾讯文档授权 token 预留表。

    本阶段只预留结构，不主动调用真实 OpenAPI；token 明文仅保存在后端数据库，
    不通过接口返回给前端。后续生产部署可再接入密钥管理或加密存储。
    """

    __tablename__ = "tencent_docs_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False, default="tencent_docs")
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    open_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class AuditLog(Base):
    """审计日志表，用于记录关键操作。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False, default=datetime.utcnow)
