"""腾讯文档真实同步配置骨架接口。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from dependencies import require_roles
from models import User
from services.sync_core import SyncImportResult
from services.sync_providers import (
    RealTencentDocsProvider,
    TencentDocsEndpointConfigError,
    TencentDocsApiError,
    TencentDocsApiNotImplementedError,
    TencentDocsConfigError,
    log_export_result,
    log_import_result,
)
from services import tencent_docs_jobs
from services.token_expiry import get_token_expiry_info, save_token_expiry_setting


router = APIRouter(prefix="/api/tencent-docs", tags=["tencent-docs-real"])


class TencentDocsRealStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    """腾讯文档真实同步配置状态。"""

    mode: Literal["real", "mock", "local"] = Field(..., description="当前同步模式")
    auth_mode: Literal["oauth", "direct_token"] = Field(..., description="授权配置模式")
    client_id_configured: bool = Field(..., description="是否配置 Client ID")
    client_secret_configured: bool = Field(..., description="是否配置 Client Secret")
    redirect_uri_configured: bool = Field(..., description="是否配置 OAuth Redirect URI")
    access_token_configured: bool = Field(..., description="是否配置 Direct Token 模式的 Access Token")
    doc_id_configured: bool = Field(..., description="是否配置腾讯文档 ID")
    doc_id: str | None = Field(default=None, description="腾讯文档 ID")
    default_year: int = Field(default=2026, description="默认同步年份")
    ready_for_direct_token: bool = Field(..., description="是否具备 Direct Token 同步配置")
    sheet_read_endpoint_configured: bool = Field(..., description="是否配置表格读取 endpoint")
    sheet_write_endpoint_configured: bool = Field(..., description="是否配置表格写入 endpoint")
    ready_for_api_endpoint: bool = Field(..., description="是否具备表格读写 endpoint 配置")
    token_saved: bool = Field(..., description="是否保存 token")
    token_valid: bool = Field(..., description="token 是否有效")
    token_expires_at: str | None = Field(default=None, description="token 过期时间")
    open_id_saved: bool = Field(..., description="是否保存 open_id")
    ready_for_oauth: bool = Field(..., description="是否具备 OAuth 授权配置")
    ready_for_sync: bool = Field(..., description="是否具备真实同步条件")


class OAuthUrlResponse(BaseModel):
    """OAuth 授权地址响应。"""

    oauth_url: str = Field(..., description="腾讯文档 OAuth 授权地址")


class PlaceholderResponse(BaseModel):
    """真实 API 占位响应。"""

    detail: str = Field(..., description="占位提示")


class TencentDocsImportResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    """腾讯文档真实导入响应。"""

    success: bool = Field(default=True, description="是否完成导入流程")
    message: str = Field(..., description="导入摘要")
    created: int = Field(default=0, description="新增库存流水数量")
    skipped: int = Field(default=0, description="跳过数量")
    failed: int = Field(default=0, description="失败数量")
    created_count: int = Field(default=0, description="新增数量")
    skipped_count: int = Field(default=0, description="跳过数量")
    failed_count: int = Field(default=0, description="失败数量")
    errors: list[dict] = Field(default_factory=list, description="错误明细")
    log_id: int = Field(..., description="同步日志 ID")


class TencentDocsExportResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    """腾讯文档真实导出响应。"""

    success: bool = Field(default=True, description="是否完成导出流程")
    message: str = Field(..., description="导出摘要")
    written_sheets: int = Field(default=0, description="写回 sheet 数量")
    total_rows: int = Field(default=0, description="写回行数")
    log_id: int = Field(..., description="同步日志 ID")


class TencentDocsTokenExpiryRequest(BaseModel):
    """腾讯文档 Direct Token 过期时间维护请求。"""

    token_expires_at: str | None = Field(default=None, description="人工维护的 token 过期时间")


class TencentDocsTokenExpiryResponse(BaseModel):
    """腾讯文档 Direct Token 过期时间状态响应。"""

    token_expires_at: str | None = Field(default=None, description="token 过期时间")
    source: str = Field(..., description="过期时间来源：database/env/none")
    status: str = Field(..., description="过期提醒状态")
    remaining_seconds: int | None = Field(default=None, description="剩余秒数")
    remaining_text: str = Field(..., description="剩余有效期文本")
    warning_threshold_days: int = Field(default=7, description="即将过期阈值天数")


def build_provider(db: Session | None = None) -> RealTencentDocsProvider:
    """创建真实腾讯文档 Provider。"""

    return RealTencentDocsProvider(db=db)


def _write_failed_export_log(db: Session, exc: TencentDocsApiError) -> None:
    """Write a failed sync log with API error details, then rollback."""

    import json as _json

    detail = exc.detail or {}
    try:
        db.rollback()
        log_export_result(
            db=db,
            provider_source="tencent_docs_real",
            sync_type="tencent_docs_export",
            message=str(exc),
            detail={
                "error": str(exc),
                "request_url": detail.get("request_url", ""),
                "code": detail.get("code"),
                "msg": detail.get("msg"),
                "book_id": detail.get("book_id", ""),
                "sheet_id": detail.get("sheet_id", ""),
                "range": detail.get("range", ""),
                "http_status": detail.get("http_status"),
                "raw_response": detail.get("raw_response", "")[:2000] if detail.get("raw_response") else None,
            },
            status_value="failed",
        )
        db.commit()
    except Exception:
        db.rollback()


def raise_not_implemented(exc: TencentDocsApiNotImplementedError) -> None:
    """将 Provider 占位错误转换为 HTTP 501。"""

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=str(exc),
    ) from exc


def raise_api_error(exc: TencentDocsApiError) -> None:
    """将腾讯 API 错误转换为 HTTP 502，并保留可诊断信息。"""

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=str(exc),
    ) from exc


def raise_endpoint_config_error(exc: TencentDocsEndpointConfigError) -> None:
    """将 endpoint 缺失错误转换为结构化 HTTP 501。"""

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "success": False,
            "message": str(exc),
            "diagnosis": exc.diagnosis,
        },
    ) from exc


@router.get(
    "/status",
    response_model=TencentDocsRealStatusResponse,
    summary="查询腾讯文档真实同步配置状态",
)
def get_tencent_docs_real_status(
    current_user: User = Depends(require_roles("manager", "admin", "superadmin")),
    db: Session = Depends(get_db),
) -> TencentDocsRealStatusResponse:
    """返回配置、token 与真实同步可用性状态，不返回任何密钥或 token 明文。"""

    _ = current_user
    return TencentDocsRealStatusResponse(**build_provider(db).get_status())


@router.get(
    "/oauth-url",
    response_model=OAuthUrlResponse,
    summary="生成腾讯文档 OAuth 授权地址",
)
def get_tencent_docs_oauth_url(
    state: str | None = Query(default=None, description="可选 state 参数"),
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> OAuthUrlResponse:
    """配置完整时生成 OAuth URL；配置不足时返回 400。"""

    _ = current_user
    try:
        oauth_url = build_provider(db).build_oauth_url(state=state)
    except TencentDocsConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OAuthUrlResponse(oauth_url=oauth_url)


@router.post(
    "/refresh-status",
    response_model=TencentDocsRealStatusResponse,
    summary="刷新腾讯文档授权状态",
)
def refresh_tencent_docs_status(
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> TencentDocsRealStatusResponse:
    """本阶段仅重新读取本地配置与 token 表状态，不调用真实腾讯接口。"""

    _ = current_user
    return TencentDocsRealStatusResponse(**build_provider(db).get_status())


@router.get(
    "/token-expiry",
    response_model=TencentDocsTokenExpiryResponse,
    summary="查询腾讯文档 Direct Token 过期提醒时间",
)
def get_tencent_docs_token_expiry(
    current_user: User = Depends(require_roles("manager", "admin", "superadmin")),
    db: Session = Depends(get_db),
) -> TencentDocsTokenExpiryResponse:
    """返回管理员手动维护的 Direct Token 过期提醒信息，不返回 token 明文。"""

    _ = current_user
    return TencentDocsTokenExpiryResponse(**get_token_expiry_info(db))


@router.put(
    "/token-expiry",
    response_model=TencentDocsTokenExpiryResponse,
    summary="更新腾讯文档 Direct Token 过期提醒时间",
)
def update_tencent_docs_token_expiry(
    payload: TencentDocsTokenExpiryRequest,
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> TencentDocsTokenExpiryResponse:
    """保存或清除 Direct Token 过期提醒时间；不会修改 .env 或 access_token。"""

    try:
        result = save_token_expiry_setting(
            db,
            payload.token_expires_at,
            updated_by=current_user.id,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return TencentDocsTokenExpiryResponse(**result)


class TencentDocsJobRequest(BaseModel):
    """后台同步 Job 创建请求。"""

    year: int = Field(default=settings.TENCENT_DOCS_DEFAULT_YEAR, ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    all_months: bool = Field(default=False)


class TencentDocsJobResponse(BaseModel):
    """后台同步 Job 状态响应。"""

    model_config = ConfigDict(extra="allow")

    job_id: str
    job_type: str
    mode: str
    year: int | None = None
    month: int | None = None
    status: str
    progress_total: int = 0
    progress_done: int = 0
    message: str | None = None
    result: dict | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


@router.post(
    "/import-jobs",
    response_model=TencentDocsJobResponse,
    summary="创建腾讯文档后台导入任务",
)
def create_tencent_docs_import_job(
    payload: TencentDocsJobRequest,
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> TencentDocsJobResponse:
    """创建后台导入任务并立即返回 job_id。前端通过 GET /jobs/{job_id} 轮询进度。"""

    _ = current_user
    try:
        result = tencent_docs_jobs.create_import_job(
            db,
            year=payload.year,
            month=payload.month,
            all_months=payload.all_months,
            operator_id=current_user.id,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="导入任务创建失败，请检查后端服务",
        )
    return TencentDocsJobResponse(**result)


@router.post(
    "/export-jobs",
    response_model=TencentDocsJobResponse,
    summary="创建腾讯文档后台同步任务",
)
def create_tencent_docs_export_job(
    payload: TencentDocsJobRequest,
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> TencentDocsJobResponse:
    """创建后台同步任务并立即返回 job_id。前端通过 GET /jobs/{job_id} 轮询进度。"""

    _ = current_user
    try:
        result = tencent_docs_jobs.create_export_job(
            db,
            year=payload.year,
            month=payload.month,
            all_months=payload.all_months,
            force_skip_write_cell_check=False,
            operator_id=current_user.id,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="同步任务创建失败，请检查后端服务",
        )
    return TencentDocsJobResponse(**result)


@router.get(
    "/jobs/{job_id}",
    response_model=TencentDocsJobResponse,
    summary="查询腾讯文档后台任务状态",
)
def get_tencent_docs_job_status(
    job_id: str,
    current_user: User = Depends(require_roles("manager", "admin", "superadmin")),
    db: Session = Depends(get_db),
) -> TencentDocsJobResponse:
    """查询后台导入/同步任务的状态、进度和结果。"""

    _ = current_user
    result = tencent_docs_jobs.get_job_status(db, job_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return TencentDocsJobResponse(**result)


@router.get(
    "/sheets",
    summary="调试腾讯文档 sheet 信息",
)
def debug_tencent_docs_sheets(
    current_user: User = Depends(require_roles("manager", "admin", "superadmin")),
    db: Session = Depends(get_db),
) -> dict:
    """返回腾讯文档 sheet 信息原始响应和解析出的 sheetID 候选，不返回任何 token 明文。"""

    _ = current_user
    try:
        return build_provider(db).get_sheets_debug_info()
    except TencentDocsConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TencentDocsEndpointConfigError as exc:
        raise_endpoint_config_error(exc)
    except TencentDocsApiError as exc:
        raise_api_error(exc)


@router.post(
    "/debug/import-dry-run",
    summary="预检腾讯文档矩阵导入解析结果",
)
def debug_tencent_docs_import_dry_run(
    year: int = Query(default=settings.TENCENT_DOCS_DEFAULT_YEAR, ge=2000, le=2100),
    month: int = Query(default=settings.TENCENT_DOCS_ACTIVE_MONTH, ge=1, le=12),
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> dict:
    """读取当前 sheet 矩阵范围并返回解析预览，不写入数据库。"""

    _ = current_user
    try:
        return build_provider(db).preview_import_matrix(year=year, month=month)
    except TencentDocsConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TencentDocsEndpointConfigError as exc:
        raise_endpoint_config_error(exc)
    except TencentDocsApiError as exc:
        raise_api_error(exc)


@router.get(
    "/debug/export-preview",
    summary="预览同步到腾讯文档的矩阵数据",
)
def debug_tencent_docs_export_preview(
    year: int = Query(default=settings.TENCENT_DOCS_DEFAULT_YEAR, ge=2000, le=2100),
    month: int = Query(default=settings.TENCENT_DOCS_ACTIVE_MONTH, ge=1, le=12),
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> dict:
    """根据本地库存流水生成 A1:BF37 矩阵预览，不调用腾讯写入接口。"""

    _ = current_user
    try:
        return build_provider(db).preview_export_matrix(db=db, year=year, month=month)
    except TencentDocsConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TencentDocsEndpointConfigError as exc:
        raise_endpoint_config_error(exc)
    except TencentDocsApiError as exc:
        raise_api_error(exc)


@router.post(
    "/debug/write-cell",
    summary="安全写入单元格测试（默认写 000001!A1:A1）",
)
def debug_tencent_docs_write_cell(
    year: int = Query(default=settings.TENCENT_DOCS_DEFAULT_YEAR, ge=2000, le=2100),
    month: int = Query(default=settings.TENCENT_DOCS_ACTIVE_MONTH, ge=1, le=12),
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> dict:
    """仅写一个配置的测试单元格，默认 000001!A1:A1。

    该接口只测试腾讯文档 V2 写入 API 连通性，不影响正式月份同步逻辑。
    """

    _ = current_user
    try:
        return build_provider(db).debug_write_cell(year=year, month=month)
    except TencentDocsConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TencentDocsEndpointConfigError as exc:
        raise_endpoint_config_error(exc)
    except TencentDocsApiError as exc:
        raise_api_error(exc)


@router.post(
    "/import",
    response_model=TencentDocsImportResponse,
    summary="从腾讯文档导入库存流水",
)
def import_from_tencent_docs(
    year: int = Query(default=settings.TENCENT_DOCS_DEFAULT_YEAR, ge=2000, le=2100),
    month: int = Query(default=settings.TENCENT_DOCS_ACTIVE_MONTH, ge=1, le=12),
    all_months: bool = Query(default=False, description="导入全年 1-12 月"),
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> TencentDocsImportResponse:
    """从腾讯文档读取历史模板宽表，转换后复用 ImportService 导入库存流水。

    - 单月模式：指定 year/month，后端自动解析对应 sheetID
    - 全年模式：all_months=true，依次处理 1-12 月
    """

    try:
        provider = build_provider(db)
        if all_months:
            import json as _json
            all_result = provider.import_all_months(db=db, operator_id=current_user.id, year=year)
            message = (
                f"腾讯文档全年导入完成：{all_result['status']}，"
                f"新增 {all_result['total_inserted']} 条，"
                f"跳过 {all_result['total_skipped']} 条，"
                f"失败 {all_result['total_failed']} 条"
            )
            sync_log = log_import_result(
                db=db,
                provider_source=provider.source,
                sync_type="tencent_docs_import",
                result=SyncImportResult(
                    created=all_result["total_inserted"],
                    skipped=all_result["total_skipped"],
                    failed=all_result["total_failed"],
                    errors=[],
                ),
                message_prefix="腾讯文档全年导入",
            )
            db.commit()
            db.refresh(sync_log)
            return TencentDocsImportResponse(
                success=all_result["status"] != "failed",
                message=message,
                created=all_result["total_inserted"],
                skipped=all_result["total_skipped"],
                failed=all_result["total_failed"],
                created_count=all_result["total_inserted"],
                skipped_count=all_result["total_skipped"],
                failed_count=all_result["total_failed"],
                errors=[],
                log_id=sync_log.id,
                all_months_result=all_result,
            )

        result = provider.import_records(db=db, operator_id=current_user.id, year=year, month=month)
        sync_log = log_import_result(
            db=db,
            provider_source=provider.source,
            sync_type="tencent_docs_import",
            result=result,
            message_prefix="腾讯文档导入",
        )
        db.commit()
        db.refresh(sync_log)
    except TencentDocsConfigError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TencentDocsEndpointConfigError as exc:
        db.rollback()
        raise_endpoint_config_error(exc)
    except TencentDocsApiError as exc:
        db.rollback()
        raise_api_error(exc)
    except TencentDocsApiNotImplementedError as exc:
        db.rollback()
        raise_not_implemented(exc)
    return TencentDocsImportResponse(
        success=True,
        message=sync_log.message or "腾讯文档导入完成",
        created=result.created if not all_months else 0,
        skipped=result.skipped if not all_months else 0,
        failed=result.failed if not all_months else 0,
        created_count=result.created if not all_months else 0,
        skipped_count=result.skipped if not all_months else 0,
        failed_count=result.failed if not all_months else 0,
        errors=[error.to_dict() for error in result.errors] if not all_months else [],
        log_id=sync_log.id,
        **getattr(result, "extra_detail", {}),
    )


@router.post(
    "/export",
    response_model=TencentDocsExportResponse,
    summary="同步本地数据到腾讯文档",
)
def export_to_tencent_docs(
    year: int = Query(default=settings.TENCENT_DOCS_DEFAULT_YEAR, ge=2000, le=2100),
    month: int = Query(default=settings.TENCENT_DOCS_ACTIVE_MONTH, ge=1, le=12),
    all_months: bool = Query(default=False, description="同步全年 1-12 月"),
    force_skip_write_cell_check: bool = Query(default=False, description="跳过 write-cell 预检"),
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> TencentDocsExportResponse:
    """把本地库存流水以增量 patch 方式写回腾讯文档。

    - 单月模式：指定 year/month，后端自动解析对应 sheetID
    - 全年模式：all_months=true，依次处理 1-12 月

    写入前会执行硬校验：sheetID 确认、数据量检查、冲突检查、write-cell 测试。
    """

    try:
        provider = build_provider(db)

        if all_months:
            all_result = provider.export_all_months(
                db=db, year=year, force_skip_write_cell_check=force_skip_write_cell_check,
            )
            message = (
                f"腾讯文档全年同步完成：{all_result['status']}，"
                f"写入 {all_result['total_written_patch_count']} 个小范围，"
                f"跳过重复 {all_result['total_skipped_duplicate_count']} 个，"
                f"失败 {all_result['total_failed_patch_count']} 个"
            )
            sync_log = log_export_result(
                db=db,
                provider_source=provider.source,
                sync_type="tencent_docs_export",
                message=message,
                detail=all_result,
                status_value=all_result["status"],
            )
            db.commit()
            db.refresh(sync_log)
            return TencentDocsExportResponse(
                success=all_result["status"] != "failed",
                message=message,
                written_sheets=sum(1 for m in all_result["per_month_results"] if m.get("written_patch_count", 0) > 0),
                total_rows=all_result["total_written_patch_count"],
                log_id=sync_log.id,
                all_months_result=all_result,
            )

        export_result = provider.export_records(
            db=db, year=year, month=month,
            force_skip_write_cell_check=force_skip_write_cell_check,
        )
        result_status = export_result.get("status", "")
        if result_status == "conflict":
            log_export_result(
                db=db,
                provider_source=provider.source,
                sync_type="tencent_docs_export",
                message=export_result.get("message", "冲突导致导出取消"),
                detail=export_result,
                status_value="failed",
            )
            db.commit()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=export_result)
        if result_status in ("no_data", "no_matched_records", "no_new_data"):
            message = export_result.get("message", "没有需要同步到腾讯文档的新数据")
            sync_log = log_export_result(
                db=db,
                provider_source=provider.source,
                sync_type="tencent_docs_export",
                message=message,
                detail=export_result,
                status_value=result_status,
            )
            db.commit()
            db.refresh(sync_log)
            return TencentDocsExportResponse(
                success=False,
                message=message,
                written_sheets=export_result.get("written_sheets", 0),
                total_rows=export_result.get("total_rows", 0),
                log_id=sync_log.id,
                **{
                    key: value
                    for key, value in export_result.items()
                    if key
                    not in {
                        "success",
                        "message",
                        "written_sheets",
                        "total_rows",
                        "values",
                        "write_values",
                    }
                },
            )
        if result_status in (
            "validation_failed",
            "invalid_matrix",
            "read_failed",
        ):
            log_export_result(
                db=db,
                provider_source=provider.source,
                sync_type="tencent_docs_export",
                message=export_result.get("message", "导出条件不满足"),
                detail=export_result,
                status_value=result_status,
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=export_result,
            )
        message = export_result.get("message") or (
            f"腾讯文档导出完成，写回 {export_result.get('written_sheets', 0)} 个 sheet，"
            f"共 {export_result.get('total_rows', 0)} 行"
        )
        sync_log = log_export_result(
            db=db,
            provider_source=provider.source,
            sync_type="tencent_docs_export",
            message=message,
            detail=export_result,
            status_value=result_status or "success",
        )
        db.commit()
        db.refresh(sync_log)
    except TencentDocsConfigError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TencentDocsEndpointConfigError as exc:
        db.rollback()
        raise_endpoint_config_error(exc)
    except TencentDocsApiError as exc:
        _write_failed_export_log(db, exc)
        raise_api_error(exc)
    except TencentDocsApiNotImplementedError as exc:
        db.rollback()
        raise_not_implemented(exc)
    return TencentDocsExportResponse(
        success=bool(export_result.get("success", True)),
        message=message,
        written_sheets=export_result.get("written_sheets", 0),
        total_rows=export_result.get("total_rows", 0),
        log_id=sync_log.id,
        **{
            key: value
            for key, value in export_result.items()
            if key
            not in {
                "success",
                "message",
                "written_sheets",
                "total_rows",
                "values",
                "write_values",
            }
        },
    )
