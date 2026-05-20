"""腾讯文档真实同步配置骨架接口。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from dependencies import require_roles
from models import User
from services.sync_providers import (
    RealTencentDocsProvider,
    TencentDocsApiNotImplementedError,
    TencentDocsConfigError,
)


router = APIRouter(prefix="/api/tencent-docs", tags=["tencent-docs-real"])


class TencentDocsRealStatusResponse(BaseModel):
    """腾讯文档真实同步配置状态。"""

    mode: Literal["real", "mock", "local"] = Field(..., description="当前同步模式")
    client_id_configured: bool = Field(..., description="是否配置 Client ID")
    client_secret_configured: bool = Field(..., description="是否配置 Client Secret")
    redirect_uri_configured: bool = Field(..., description="是否配置 OAuth Redirect URI")
    doc_id_configured: bool = Field(..., description="是否配置腾讯文档 ID")
    doc_id: str | None = Field(default=None, description="腾讯文档 ID")
    default_year: int = Field(default=2026, description="默认同步年份")
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


def build_provider(db: Session | None = None) -> RealTencentDocsProvider:
    """创建真实腾讯文档 Provider。"""

    return RealTencentDocsProvider(db=db)


def raise_not_implemented(exc: TencentDocsApiNotImplementedError) -> None:
    """将 Provider 占位错误转换为 HTTP 501。"""

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=str(exc),
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


@router.post(
    "/import",
    response_model=PlaceholderResponse,
    summary="从腾讯文档导入库存流水",
)
def import_from_tencent_docs(
    year: int = Query(default=settings.TENCENT_DOCS_DEFAULT_YEAR, ge=2000, le=2100),
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> PlaceholderResponse:
    """真实导入占位；后续接入 OpenAPI 后实现。"""

    try:
        build_provider(db).import_records(db=db, operator_id=current_user.id, year=year)
    except TencentDocsApiNotImplementedError as exc:
        raise_not_implemented(exc)
    return PlaceholderResponse(detail="腾讯文档导入已完成")


@router.post(
    "/export",
    response_model=PlaceholderResponse,
    summary="同步本地数据到腾讯文档",
)
def export_to_tencent_docs(
    year: int = Query(default=settings.TENCENT_DOCS_DEFAULT_YEAR, ge=2000, le=2100),
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> PlaceholderResponse:
    """真实导出占位；后续接入 OpenAPI 后实现。"""

    _ = current_user
    try:
        build_provider(db).export_records(db=db, year=year)
    except TencentDocsApiNotImplementedError as exc:
        raise_not_implemented(exc)
    return PlaceholderResponse(detail="腾讯文档同步已完成")

