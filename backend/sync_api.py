"""统一同步 API。

本模块提供 /api/sync/* 标准接口，旧的 /tencent-docs/* 接口会复用这里的函数。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_roles
from models import SyncLog, User
from services.csv_reagent_sync import read_reagent_rows_from_csv, upsert_reagent_rows
from services.sync_providers import (
    ExcelSyncProvider,
    MockTencentDocsProvider,
    build_sync_status,
    log_export_result,
    log_import_result,
)


router = APIRouter(prefix="/api/sync", tags=["sync"])


class SyncStatusResponse(BaseModel):
    """统一同步状态响应。"""

    mode: Literal["mock", "local", "api", "real"] = Field(..., description="当前同步模式")
    mock_enabled: bool = Field(..., description="是否启用 Mock 同步")
    excel_enabled: bool = Field(..., description="是否启用本地 Excel/CSV 同步")
    tencent_docs_enabled: bool = Field(..., description="是否启用真实腾讯文档同步")
    client_id_configured: bool = Field(..., description="是否配置腾讯应用 ID")
    client_secret_configured: bool = Field(..., description="是否配置腾讯应用密钥")
    redirect_uri_configured: bool = Field(..., description="是否配置 OAuth 回调地址")
    access_token_configured: bool = Field(default=False, description="是否配置 Direct Token 模式 access_token")
    doc_id_configured: bool = Field(..., description="是否配置目标腾讯文档 ID")
    token_saved: bool = Field(..., description="是否保存授权 token")
    token_valid: bool = Field(default=False, description="腾讯文档 token 是否有效")
    token_expires_at: str | None = Field(default=None, description="腾讯文档 token 过期时间")
    open_id_saved: bool = Field(default=False, description="是否已保存 open_id")
    ready_for_oauth: bool = Field(default=False, description="是否具备 OAuth 授权配置")
    ready_for_direct_token: bool = Field(default=False, description="是否具备 Direct Token 同步配置")
    sheet_read_endpoint_configured: bool = Field(default=False, description="是否配置表格读取 endpoint")
    sheet_write_endpoint_configured: bool = Field(default=False, description="是否配置表格写入 endpoint")
    ready_for_api_endpoint: bool = Field(default=False, description="是否具备表格读写 endpoint 配置")
    ready_for_sync: bool = Field(default=False, description="是否具备真实同步条件")
    auth_mode: str = Field(default="oauth", description="腾讯文档授权模式")
    doc_id: str | None = Field(default=None, description="目标腾讯文档 ID")
    description: str = Field(..., description="同步模式说明")
    # 兼容旧页面字段。
    has_client_id: bool = Field(..., description="是否配置 client_id")
    has_client_secret: bool = Field(..., description="是否配置 client_secret")
    has_redirect_uri: bool = Field(..., description="是否配置 redirect_uri")
    has_access_token: bool = Field(default=False, description="是否配置 access_token")
    has_doc_id: bool = Field(..., description="是否配置 doc_id")
    has_sheet_id: bool = Field(..., description="是否配置 sheet_id")
    has_token: bool = Field(..., description="是否保存 token")


class SyncImportResponse(BaseModel):
    """统一导入响应。"""

    success: bool = Field(default=True, description="是否完成导入流程")
    message: str = Field(..., description="导入结果摘要")
    created: int = Field(default=0, description="新增库存流水数量")
    skipped: int = Field(default=0, description="跳过数量")
    failed: int = Field(default=0, description="失败数量")
    errors: list[dict[str, Any]] = Field(default_factory=list, description="错误明细")
    log_id: int = Field(..., description="同步日志 ID")
    created_count: int = Field(default=0, description="兼容字段：新增数量")
    imported_count: int = Field(default=0, description="兼容字段：导入数量")
    skipped_count: int = Field(default=0, description="兼容字段：跳过数量")
    updated_count: int = Field(default=0, description="兼容字段：更新数量")
    failed_count: int = Field(default=0, description="兼容字段：失败数量")
    created_reagents: int = Field(default=0, description="新增试剂数量")
    updated_reagents: int = Field(default=0, description="更新试剂数量")
    monthly_counts: dict[str, int] = Field(default_factory=dict, description="按月份统计的解析记录数量")


class SyncExportResponse(BaseModel):
    """统一导出响应。"""

    total_count: int = Field(..., description="导出行数")
    rows: list[dict[str, Any]] = Field(default_factory=list, description="导出行数据")
    log_id: int = Field(..., description="同步日志 ID")


class SyncLogResponse(BaseModel):
    """同步日志响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="日志 ID")
    source: str = Field(..., description="同步来源")
    sync_type: str = Field(..., description="同步类型")
    status: str = Field(..., description="同步状态")
    message: str | None = Field(default=None, description="同步消息")
    detail_json: str | None = Field(default=None, description="同步明细 JSON")
    created_at: Any = Field(..., description="创建时间")


def build_import_response(result_data: dict[str, Any], log_id: int) -> SyncImportResponse:
    """补齐兼容字段并构造导入响应。"""

    payload = {**result_data, "log_id": log_id}
    payload.setdefault("created_count", payload.get("created", 0))
    payload.setdefault("imported_count", payload.get("created", 0))
    payload.setdefault("skipped_count", payload.get("skipped", 0))
    payload.setdefault("updated_count", payload.get("updated_reagents", 0))
    payload.setdefault("failed_count", payload.get("failed", 0))
    return SyncImportResponse(**payload)


def get_status_payload() -> dict[str, Any]:
    """返回统一同步状态字典。"""

    return build_sync_status()


def list_sync_logs_data(db: Session, skip: int = 0, limit: int = 100) -> list[SyncLog]:
    """查询同步日志。"""

    stmt = select(SyncLog).order_by(SyncLog.id.desc()).offset(skip).limit(limit)
    return list(db.execute(stmt).scalars().all())


def run_mock_import(db: Session, current_user: User) -> SyncImportResponse:
    """执行 Mock 导入并写入日志。"""

    provider = MockTencentDocsProvider()
    try:
        result = provider.import_records(db=db, operator_id=current_user.id)
        sync_log = log_import_result(
            db=db,
            provider_source=provider.source,
            sync_type="mock_import",
            result=result,
            message_prefix="Mock 导入",
        )
        db.commit()
        db.refresh(sync_log)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Mock 导入失败") from exc

    return build_import_response(result.to_response(message=sync_log.message), sync_log.id)


def run_mock_export(db: Session, year: int = 2026) -> SyncExportResponse:
    """执行 Mock 导出并写入日志。"""

    provider = MockTencentDocsProvider()
    try:
        rows = provider.export_records(db=db, year=year)
        sync_log = log_export_result(
            db=db,
            provider_source=provider.source,
            sync_type="mock_export",
            message=f"Mock 导出完成，共生成 {len(rows)} 行",
            detail={"year": year, "total_count": len(rows)},
        )
        db.commit()
        db.refresh(sync_log)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Mock 导出失败") from exc

    return SyncExportResponse(total_count=len(rows), rows=rows, log_id=sync_log.id)


async def run_excel_import(
    db: Session,
    current_user: User,
    file: UploadFile,
) -> SyncImportResponse:
    """执行 Excel/CSV 导入并写入日志。"""

    try:
        content = await file.read()
        file_name = file.filename or ""
        suffix = Path(file_name).suffix.lower()

        if suffix in {".xlsx", ".xls"}:
            provider = ExcelSyncProvider()
            result = provider.import_records(
                db=db,
                operator_id=current_user.id,
                file_name=file_name,
                content=content,
            )
            sync_log = log_import_result(
                db=db,
                provider_source=provider.source,
                sync_type="excel_import",
                result=result,
                message_prefix="Excel 导入",
            )
            db.commit()
            db.refresh(sync_log)
            return build_import_response(result.to_response(message=sync_log.message), sync_log.id)

        if suffix != ".csv":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 .xlsx、.xls 或 .csv 文件")

        rows, parse_failed_count = read_reagent_rows_from_csv(content)
        created_count, updated_count, row_failed_count = upsert_reagent_rows(db, rows)
        failed_count = parse_failed_count + row_failed_count
        message = f"CSV 导入完成：新增 {created_count} 条，更新 {updated_count} 条，失败 {failed_count} 条"
        sync_log = log_export_result(
            db=db,
            provider_source="csv",
            sync_type="csv_import",
            message=message,
            detail={
                "created_reagents": created_count,
                "updated_reagents": updated_count,
                "failed": failed_count,
            },
        )
        db.commit()
        db.refresh(sync_log)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文件导入写入数据库失败") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"文件导入失败：{exc}") from exc

    return SyncImportResponse(
        success=True,
        message=message,
        created=created_count,
        skipped=0,
        failed=failed_count,
        errors=[],
        log_id=sync_log.id,
        created_count=created_count,
        updated_count=updated_count,
        failed_count=failed_count,
        imported_count=created_count,
        skipped_count=0,
        created_reagents=created_count,
        updated_reagents=updated_count,
    )


def run_excel_export(db: Session, year: int = 2026) -> FileResponse:
    """执行 Excel 导出并写入日志。"""

    try:
        provider = ExcelSyncProvider()
        file_path = provider.export_records(db=db, year=year)
        sync_log = log_export_result(
            db=db,
            provider_source=provider.source,
            sync_type="excel_export",
            message=f"Excel 导出完成：{year} 年库存流水模板",
            detail={"year": year, "file_name": file_path.name},
        )
        db.commit()
        db.refresh(sync_log)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Excel 导出写入日志失败") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Excel 导出失败：{exc}") from exc

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/status", response_model=SyncStatusResponse, summary="查询同步状态")
def get_sync_status(
    current_user: User = Depends(require_roles("manager", "admin", "superadmin")),
) -> SyncStatusResponse:
    """返回所有同步配置状态。"""

    _ = current_user
    return SyncStatusResponse(**get_status_payload())


@router.get("/logs", response_model=list[SyncLogResponse], summary="查询同步日志")
def list_sync_logs(
    skip: int = Query(default=0, ge=0, description="跳过记录数"),
    limit: int = Query(default=100, ge=1, le=500, description="返回记录数上限"),
    current_user: User = Depends(require_roles("manager", "admin", "superadmin")),
    db: Session = Depends(get_db),
) -> list[SyncLog]:
    """查询同步日志。"""

    _ = current_user
    return list_sync_logs_data(db=db, skip=skip, limit=limit)


@router.post("/mock/import", response_model=SyncImportResponse, summary="Mock 导入")
def mock_import(
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> SyncImportResponse:
    """调用 Mock Provider 导入库存流水。"""

    return run_mock_import(db=db, current_user=current_user)


@router.post("/mock/export", response_model=SyncExportResponse, summary="Mock 导出")
def mock_export(
    year: int = Query(default=2026, ge=2000, le=2100, description="导出年份"),
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> SyncExportResponse:
    """调用 Mock Provider 导出标准宽表数据。"""

    _ = current_user
    return run_mock_export(db=db, year=year)


@router.post("/excel/import", response_model=SyncImportResponse, summary="Excel/CSV 导入")
async def excel_import(
    file: UploadFile = File(..., description="支持 .xlsx / .xls / .csv 文件"),
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> SyncImportResponse:
    """调用 Excel Provider 导入文件。"""

    return await run_excel_import(db=db, current_user=current_user, file=file)


@router.get("/excel/export", summary="Excel 导出")
def excel_export(
    year: int = Query(default=2026, ge=2000, le=2100, description="导出年份"),
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> FileResponse:
    """调用 ExportService 导出 Excel 文件。"""

    _ = current_user
    return run_excel_export(db=db, year=year)
