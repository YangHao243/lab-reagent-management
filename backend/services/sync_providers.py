"""同步 Provider 抽象与实现。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from models import SyncLog, TencentDocsToken
from services.excel_inventory_sync import export_inventory_excel, import_excel_inventory
from services.sync_core import (
    ExportService,
    ImportService,
    NormalizedInventoryRecord,
    SyncImportResult,
    SyncLogService,
)


def get_token_file_path() -> Path:
    """返回本地腾讯文档 token 文件路径。"""

    token_file = Path(settings.TENCENT_DOC_TOKEN_FILE)
    if not token_file.is_absolute():
        token_file = Path(__file__).resolve().parent.parent / token_file
    return token_file


class TencentDocsConfigError(RuntimeError):
    """腾讯文档真实同步配置错误。"""


class TencentDocsApiNotImplementedError(NotImplementedError):
    """腾讯文档真实 OpenAPI 尚未实现。"""


def get_tencent_docs_config() -> dict[str, Any]:
    """读取真实腾讯文档同步配置，TENCENT_DOCS_* 优先，旧字段兜底。"""

    raw_mode = (settings.TENCENT_DOCS_MODE or "").strip().lower()
    mode = raw_mode if raw_mode in {"real", "mock", "local"} else "local"
    return {
        "mode": mode,
        "client_id": settings.TENCENT_DOCS_CLIENT_ID.strip()
        or settings.TENCENT_DOC_CLIENT_ID.strip(),
        "client_secret": settings.TENCENT_DOCS_CLIENT_SECRET.strip()
        or settings.TENCENT_DOC_CLIENT_SECRET.strip(),
        "redirect_uri": settings.TENCENT_DOCS_REDIRECT_URI.strip()
        or settings.TENCENT_DOC_REDIRECT_URI.strip(),
        "doc_id": settings.TENCENT_DOCS_FILE_ID.strip() or settings.TENCENT_DOC_DOC_ID.strip(),
        "default_year": settings.TENCENT_DOCS_DEFAULT_YEAR,
    }


def build_sync_status() -> dict[str, Any]:
    """构建统一同步状态。"""

    real_status = RealTencentDocsProvider().get_status()
    has_client_id = bool(real_status["client_id_configured"])
    has_client_secret = bool(real_status["client_secret_configured"])
    has_redirect_uri = bool(real_status["redirect_uri_configured"])
    has_doc_id = bool(real_status["doc_id_configured"])
    token_saved = bool(real_status["token_saved"])
    tencent_docs_enabled = bool(real_status["ready_for_sync"])
    mode = real_status["mode"] if real_status["mode"] == "real" else "local"

    return {
        "mode": mode,
        "mock_enabled": settings.SYNC_MOCK_ENABLED,
        "excel_enabled": True,
        "tencent_docs_enabled": tencent_docs_enabled,
        "client_id_configured": has_client_id,
        "client_secret_configured": has_client_secret,
        "redirect_uri_configured": has_redirect_uri,
        "doc_id_configured": has_doc_id,
        "token_saved": token_saved,
        # 兼容旧前端字段。
        "has_client_id": has_client_id,
        "has_client_secret": has_client_secret,
        "has_redirect_uri": has_redirect_uri,
        "has_doc_id": has_doc_id,
        "has_sheet_id": bool(settings.TENCENT_DOC_SHEET_ID.strip()),
        "has_token": token_saved,
        "doc_id": real_status["doc_id"],
        "token_valid": real_status["token_valid"],
        "token_expires_at": real_status["token_expires_at"],
        "open_id_saved": real_status["open_id_saved"],
        "ready_for_oauth": real_status["ready_for_oauth"],
        "ready_for_sync": real_status["ready_for_sync"],
        "description": (
            "当前为真实腾讯文档 API 模式"
            if tencent_docs_enabled
            else "当前为模拟/本地同步模式，可测试导入导出流程；不会访问真实腾讯文档。"
        ),
    }


class SyncProvider(ABC):
    """同步 Provider 基类。"""

    source: str

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """返回 Provider 状态。"""

    @abstractmethod
    def validate_config(self) -> None:
        """校验 Provider 配置。"""

    @abstractmethod
    def import_records(self, db: Session, operator_id: int | None = None, **kwargs: Any) -> SyncImportResult:
        """导入标准化库存流水。"""

    @abstractmethod
    def export_records(self, db: Session, year: int = 2026, **kwargs: Any) -> Any:
        """导出数据。"""


class ExcelSyncProvider(SyncProvider):
    """Excel/CSV 本地同步 Provider。"""

    source = "excel"

    def get_status(self) -> dict[str, Any]:
        return {"excel_enabled": True}

    def validate_config(self) -> None:
        return None

    def import_records(
        self,
        db: Session,
        operator_id: int | None = None,
        **kwargs: Any,
    ) -> SyncImportResult:
        file_name = str(kwargs["file_name"])
        content = kwargs["content"]
        return import_excel_inventory(
            db=db,
            file_name=file_name,
            content=content,
            operator_id=operator_id,
        )

    def export_records(self, db: Session, year: int = 2026, **kwargs: Any) -> Path:
        _ = kwargs
        return export_inventory_excel(db, year=year)


class MockTencentDocsProvider(SyncProvider):
    """模拟腾讯文档 Provider，用于本地联调同步流程。"""

    source = "tencent_docs_mock"

    def get_status(self) -> dict[str, Any]:
        return {"mock_enabled": settings.SYNC_MOCK_ENABLED}

    def validate_config(self) -> None:
        if not settings.SYNC_MOCK_ENABLED:
            raise RuntimeError("Mock 同步已关闭")

    def import_records(
        self,
        db: Session,
        operator_id: int | None = None,
        **kwargs: Any,
    ) -> SyncImportResult:
        _ = kwargs
        self.validate_config()
        records = self.build_mock_records()
        return ImportService(db=db, operator_id=operator_id).import_records(records)

    def export_records(self, db: Session, year: int = 2026, **kwargs: Any) -> list[dict[str, Any]]:
        _ = kwargs
        self.validate_config()
        return ExportService(db=db).export_rows(year=year)

    def build_mock_records(self) -> list[NormalizedInventoryRecord]:
        """构造接近真实腾讯文档结构的 mock 库存流水。"""

        return [
            NormalizedInventoryRecord(
                year=2026,
                month=1,
                event_date=date(2026, 1, 5),
                reagent_name="丙酮（MOS）",
                operation_text="入库",
                operation_type="in",
                quantity=5,
                operator="Mock张三",
                remark="Mock 腾讯文档导入",
                source=self.source,
                source_sheet="2026.1",
                source_row=4,
                source_col=2,
            ),
            NormalizedInventoryRecord(
                year=2026,
                month=1,
                event_date=date(2026, 1, 6),
                reagent_name="丙酮（MOS）",
                operation_text="领取",
                operation_type="out",
                quantity=1,
                operator="Mock李四",
                remark="Mock 腾讯文档导入",
                source=self.source,
                source_sheet="2026.1",
                source_row=5,
                source_col=2,
            ),
            NormalizedInventoryRecord(
                year=2026,
                month=1,
                event_date=date(2026, 1, 7),
                reagent_name="无水乙醇（MOS）",
                operation_text="入库",
                operation_type="in",
                quantity=3,
                operator="Mock王五",
                remark="Mock 腾讯文档导入",
                source=self.source,
                source_sheet="2026.1",
                source_row=6,
                source_col=5,
            ),
        ]


class RealTencentDocsProvider(SyncProvider):
    """真实腾讯文档 Provider 骨架。

    本阶段只负责配置读取、状态判断和接口占位，不发起真实网络请求。
    """

    source = "tencent_docs_real"

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def _latest_token(self) -> TencentDocsToken | None:
        """读取最近一条腾讯文档 token。无数据库会话时返回 None。"""

        if self.db is None:
            return None

        stmt = (
            select(TencentDocsToken)
            .where(TencentDocsToken.provider == "tencent_docs")
            .order_by(TencentDocsToken.id.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _missing_oauth_fields(self) -> list[str]:
        config = get_tencent_docs_config()
        missing_fields: list[str] = []
        if not config["client_id"]:
            missing_fields.append("TENCENT_DOCS_CLIENT_ID")
        if not config["client_secret"]:
            missing_fields.append("TENCENT_DOCS_CLIENT_SECRET")
        if not config["redirect_uri"]:
            missing_fields.append("TENCENT_DOCS_REDIRECT_URI")
        return missing_fields

    def _not_implemented(self) -> None:
        raise TencentDocsApiNotImplementedError("腾讯文档 API 尚未配置或尚未实现")

    def get_status(self) -> dict[str, Any]:
        config = get_tencent_docs_config()
        token = self._latest_token()
        token_saved = bool(token and token.access_token)
        token_expires_at = token.expires_at if token else None
        token_valid = bool(token_saved and token_expires_at and token_expires_at > datetime.utcnow())
        open_id_saved = bool(token and token.open_id)
        ready_for_oauth = all(
            [config["client_id"], config["client_secret"], config["redirect_uri"]]
        )

        return {
            "mode": config["mode"],
            "client_id_configured": bool(config["client_id"]),
            "client_secret_configured": bool(config["client_secret"]),
            "redirect_uri_configured": bool(config["redirect_uri"]),
            "doc_id_configured": bool(config["doc_id"]),
            "doc_id": config["doc_id"] or None,
            "default_year": config["default_year"],
            "token_saved": token_saved,
            "token_valid": token_valid,
            "token_expires_at": token_expires_at.isoformat() if token_expires_at else None,
            "open_id_saved": open_id_saved,
            "ready_for_oauth": ready_for_oauth,
            "ready_for_sync": bool(ready_for_oauth and token_saved and token_valid),
        }

    def validate_config(self) -> None:
        missing_fields = self._missing_oauth_fields()
        config = get_tencent_docs_config()
        if not config["doc_id"]:
            missing_fields.append("TENCENT_DOCS_FILE_ID")
        if missing_fields:
            raise TencentDocsConfigError(
                "缺少腾讯文档真实同步配置：" + "、".join(missing_fields)
            )

    def build_oauth_url(self, state: str | None = None) -> str:
        """生成 OAuth 授权 URL；配置不足时抛出清晰错误。"""

        missing_fields = self._missing_oauth_fields()
        if missing_fields:
            raise TencentDocsConfigError(
                "缺少腾讯文档 OAuth 配置：" + "、".join(missing_fields)
            )

        config = get_tencent_docs_config()
        params = {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "response_type": "code",
            "scope": settings.TENCENT_DOC_SCOPE,
        }
        if state:
            params["state"] = state
        return f"{settings.TENCENT_DOC_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"

    def handle_oauth_callback(self, code: str, state: str | None = None) -> None:
        _ = code, state
        self._not_implemented()

    def refresh_token_if_needed(self) -> None:
        self._not_implemented()

    def list_sheets(self) -> list[dict[str, Any]]:
        self._not_implemented()

    def read_sheet_range(self, sheet_id: str, range_name: str) -> list[list[Any]]:
        _ = sheet_id, range_name
        self._not_implemented()

    def write_sheet_range(self, sheet_id: str, range_name: str, values: list[list[Any]]) -> None:
        _ = sheet_id, range_name, values
        self._not_implemented()

    def import_records(self, db: Session, operator_id: int | None = None, **kwargs: Any) -> SyncImportResult:
        _ = db, operator_id, kwargs
        self._not_implemented()

    def export_records(self, db: Session, year: int = 2026, **kwargs: Any) -> Any:
        _ = db, year, kwargs
        self._not_implemented()


def log_import_result(
    db: Session,
    provider_source: str,
    sync_type: str,
    result: SyncImportResult,
    message_prefix: str,
) -> SyncLog:
    """统一记录导入结果日志。"""

    message = (
        f"{message_prefix}完成，新增 {result.created} 条，"
        f"跳过 {result.skipped} 条，失败 {result.failed} 条"
    )
    return SyncLogService(db).create_log(
        source=provider_source,
        sync_type=sync_type,
        status_value="success" if result.failed == 0 else "partial_success",
        message=message,
        detail=result.to_detail_json(),
    )


def log_export_result(
    db: Session,
    provider_source: str,
    sync_type: str,
    message: str,
    detail: dict[str, Any] | None = None,
) -> SyncLog:
    """统一记录导出结果日志。"""

    return SyncLogService(db).create_log(
        source=provider_source,
        sync_type=sync_type,
        status_value="success",
        message=message,
        detail=detail,
    )
