"""腾讯文档同步占位框架。

当前阶段只实现 mock 导入、mock 导出和同步日志查询，不接入真实腾讯文档 API。
"""

from __future__ import annotations

import json
from datetime import date
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode, urljoin

import pandas as pd
import requests
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from dependencies import require_roles
from models import Reagent, SyncLog, User
from services.excel_inventory_sync import (
    ensure_excel_sync_schema,
    export_inventory_excel,
    import_excel_inventory,
)
from sync_api import (
    SyncExportResponse as UnifiedSyncExportResponse,
    SyncImportResponse as UnifiedSyncImportResponse,
    SyncStatusResponse as UnifiedSyncStatusResponse,
    get_status_payload,
    list_sync_logs_data,
    run_excel_export,
    run_excel_import,
    run_mock_export,
    run_mock_import,
)
from utils.timezone import now_beijing


router = APIRouter(prefix="/tencent-docs", tags=["tencent-docs"])


MOCK_REAGENT_ROWS: list[dict[str, Any]] = [
    {
        "name_cn": "氢氧化钠",
        "name_en": "Sodium Hydroxide",
        "cas_no": "1310-73-2",
        "category": "无机碱",
        "specification": "500g",
        "unit": "瓶",
        "current_quantity": 6.0,
        "warning_threshold": 2.0,
        "location": "碱柜 E1",
        "supplier": "模拟腾讯文档",
        "hazard_level": "腐蚀",
        "remark": "mock import",
    },
    {
        "name_cn": "过氧化氢",
        "name_en": "Hydrogen Peroxide",
        "cas_no": "7722-84-1",
        "category": "氧化剂",
        "specification": "500ml",
        "unit": "瓶",
        "current_quantity": 4.0,
        "warning_threshold": 1.0,
        "location": "氧化剂柜 F1",
        "supplier": "模拟腾讯文档",
        "hazard_level": "氧化性",
        "remark": "mock import",
    },
    {
        "name_cn": "氨水",
        "name_en": "Ammonia Solution",
        "cas_no": "1336-21-6",
        "category": "无机碱",
        "specification": "500ml",
        "unit": "瓶",
        "current_quantity": 5.0,
        "warning_threshold": 2.0,
        "location": "碱柜 E2",
        "supplier": "模拟腾讯文档",
        "hazard_level": "刺激性",
        "remark": "mock import",
    },
]


# Excel/CSV 中文列名到 Reagent 字段的映射。
FILE_COLUMN_MAPPING: dict[str, str] = {
    "试剂中文名": "name_cn",
    "试剂英文名": "name_en",
    "CAS号": "cas_no",
    "分类": "category",
    "规格": "specification",
    "单位": "unit",
    "当前数量": "current_quantity",
    "预警阈值": "warning_threshold",
    "存放位置": "location",
    "供应商": "supplier",
    "危险等级": "hazard_level",
    "有效期": "expiry_date",
    "备注": "remark",
}

FILE_EXPORT_COLUMNS: dict[str, str] = {
    "name_cn": "试剂中文名",
    "name_en": "试剂英文名",
    "cas_no": "CAS号",
    "category": "分类",
    "specification": "规格",
    "unit": "单位",
    "current_quantity": "当前数量",
    "warning_threshold": "预警阈值",
    "location": "存放位置",
    "supplier": "供应商",
    "hazard_level": "危险等级",
    "expiry_date": "有效期",
    "remark": "备注",
}


class TencentDocsStatusResponse(BaseModel):
    """腾讯文档同步配置状态。"""

    has_client_id: bool = Field(..., description="是否配置 client_id")
    has_client_secret: bool = Field(..., description="是否配置 client_secret")
    has_redirect_uri: bool = Field(..., description="是否配置 redirect_uri")
    has_doc_id: bool = Field(..., description="是否配置腾讯文档 ID")
    has_sheet_id: bool = Field(..., description="是否配置工作表 ID")
    has_token: bool = Field(..., description="是否已有本地 token")
    mode: Literal["mock", "local", "api"] = Field(..., description="当前同步模式")
    description: str = Field(..., description="当前同步模式说明")


class OAuthUrlResponse(BaseModel):
    """OAuth 授权地址响应。"""

    oauth_url: str = Field(..., description="用户授权跳转地址")


class TokenResponse(BaseModel):
    """OAuth token 响应。"""

    token_saved: bool = Field(..., description="是否已保存 token")
    expires_in: int | None = Field(default=None, description="访问令牌有效期秒数")
    has_refresh_token: bool = Field(..., description="是否包含 refresh_token")


class MockImportResponse(BaseModel):
    """mock 导入响应。"""

    imported_count: int = Field(..., description="新增导入数量")
    skipped_count: int = Field(..., description="已存在并跳过数量")
    log_id: int = Field(..., description="同步日志 ID")


class MockExportResponse(BaseModel):
    """mock 导出响应。"""

    total_count: int = Field(..., description="导出行数")
    rows: list[dict[str, Any]] = Field(..., description="模拟导出行数据")
    log_id: int = Field(..., description="同步日志 ID")


class FileImportResponse(BaseModel):
    """Excel/CSV 文件导入响应。"""

    success: bool = Field(default=True, description="是否完成导入流程")
    message: str = Field(default="文件导入完成", description="导入结果摘要")
    created: int = Field(default=0, description="新增库存流水数量")
    skipped: int = Field(default=0, description="跳过数量")
    failed: int = Field(default=0, description="失败数量")
    errors: list[dict[str, Any]] = Field(default_factory=list, description="错误明细")
    log_id: int = Field(..., description="同步日志 ID")
    created_count: int = Field(default=0, description="兼容字段：新增数量")
    updated_count: int = Field(default=0, description="兼容字段：更新数量")
    failed_count: int = Field(default=0, description="兼容字段：失败数量")
    created_reagents: int = Field(default=0, description="新增试剂数量")
    updated_reagents: int = Field(default=0, description="更新试剂数量")


class ApiExportResponse(BaseModel):
    """真实 Open API 导出响应。"""

    exported_count: int = Field(..., description="成功写回数量")
    failed_count: int = Field(..., description="失败数量")
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
    created_at: datetime = Field(..., description="创建时间")


def get_token_file_path() -> Path:
    """返回本地 token JSON 文件路径。"""

    token_file = Path(settings.TENCENT_DOC_TOKEN_FILE)
    if not token_file.is_absolute():
        token_file = Path(__file__).resolve().parent / token_file
    return token_file


def load_token_data() -> dict[str, Any] | None:
    """读取本地保存的腾讯文档 token。"""

    token_file = get_token_file_path()
    if not token_file.exists():
        return None

    try:
        return json.loads(token_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_token_data(token_data: dict[str, Any]) -> None:
    """保存腾讯文档 token 到本地 JSON 文件。

    第一阶段先用文件保存，后续可以独立迁移为数据库表。
    """

    token_data["saved_at"] = now_beijing().isoformat()
    token_file = get_token_file_path()
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(
        json.dumps(token_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def require_oauth_config() -> None:
    """检查 OAuth 必填配置，缺少时返回明确错误。"""

    missing_fields = []
    if not settings.TENCENT_DOC_CLIENT_ID.strip():
        missing_fields.append("TENCENT_DOC_CLIENT_ID")
    if not settings.TENCENT_DOC_CLIENT_SECRET.strip():
        missing_fields.append("TENCENT_DOC_CLIENT_SECRET")
    if not settings.TENCENT_DOC_REDIRECT_URI.strip():
        missing_fields.append("TENCENT_DOC_REDIRECT_URI")

    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"缺少腾讯文档 OAuth 配置：{', '.join(missing_fields)}",
        )


def require_api_config(readonly: bool = False) -> None:
    """检查真实 Open API 调用所需配置。"""

    missing_fields = []
    if not settings.TENCENT_DOC_DOC_ID.strip():
        missing_fields.append("TENCENT_DOC_DOC_ID")
    if not settings.TENCENT_DOC_SHEET_ID.strip():
        missing_fields.append("TENCENT_DOC_SHEET_ID")
    if not settings.TENCENT_DOC_READ_PATH.strip():
        missing_fields.append("TENCENT_DOC_READ_PATH")
    if not readonly and not settings.TENCENT_DOC_UPDATE_PATH.strip():
        missing_fields.append("TENCENT_DOC_UPDATE_PATH")

    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"缺少腾讯文档 Open API 配置：{', '.join(missing_fields)}",
        )


def build_oauth_url(state: str | None = None) -> str:
    """构造腾讯文档 OAuth2 授权地址。"""

    require_oauth_config()
    params = {
        "client_id": settings.TENCENT_DOC_CLIENT_ID,
        "redirect_uri": settings.TENCENT_DOC_REDIRECT_URI,
        "response_type": "code",
        "scope": settings.TENCENT_DOC_SCOPE,
    }
    if state:
        params["state"] = state

    return f"{settings.TENCENT_DOC_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> dict[str, Any]:
    """使用 OAuth2 code 换取 access_token。"""

    require_oauth_config()
    params = {
        "client_id": settings.TENCENT_DOC_CLIENT_ID,
        "client_secret": settings.TENCENT_DOC_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.TENCENT_DOC_REDIRECT_URI,
    }

    try:
        response = requests.get(
            settings.TENCENT_DOC_OAUTH_TOKEN_URL,
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        token_data: dict[str, Any] = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"腾讯文档 token 换取失败：{exc}",
        ) from exc

    if "access_token" not in token_data:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"腾讯文档 token 响应缺少 access_token：{token_data}",
        )

    save_token_data(token_data)
    return token_data


def refresh_access_token(refresh_token: str | None = None) -> dict[str, Any]:
    """使用 refresh_token 刷新 access_token。"""

    require_oauth_config()
    token_data = load_token_data() or {}
    refresh_token_value = refresh_token or token_data.get("refresh_token")
    if not refresh_token_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 refresh_token，请先完成 OAuth 授权",
        )

    params = {
        "client_id": settings.TENCENT_DOC_CLIENT_ID,
        "client_secret": settings.TENCENT_DOC_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token_value,
    }

    try:
        response = requests.get(
            settings.TENCENT_DOC_OAUTH_TOKEN_URL,
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        new_token_data: dict[str, Any] = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"腾讯文档 token 刷新失败：{exc}",
        ) from exc

    if "access_token" not in new_token_data:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"腾讯文档刷新响应缺少 access_token：{new_token_data}",
        )

    if "refresh_token" not in new_token_data:
        new_token_data["refresh_token"] = refresh_token_value

    save_token_data(new_token_data)
    return new_token_data


def get_current_token_data() -> dict[str, Any]:
    """读取当前 token，缺少时返回明确错误。"""

    token_data = load_token_data()
    if not token_data or not token_data.get("access_token"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未找到腾讯文档 access_token，请先完成 OAuth 授权",
        )
    return token_data


def tencent_openapi_request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """调用腾讯文档官方 Open API。

    这里不爬取网页，也不解析 HTML；只按 Open API 的 token 和 header 方式调用。
    具体表格读写 path 通过 .env 配置，便于跟随官方接口版本调整。
    """

    token_data = get_current_token_data()
    access_token = token_data["access_token"]
    open_id = token_data.get("open_id") or token_data.get("user_id") or token_data.get("openid")
    if not open_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="token 文件缺少 open_id/user_id，无法调用腾讯文档 Open API",
        )

    url = urljoin(settings.TENCENT_DOC_API_BASE_URL.rstrip("/") + "/", path.lstrip("/"))
    headers = {
        "Access-Token": access_token,
        "Client-Id": settings.TENCENT_DOC_CLIENT_ID,
        "Open-Id": str(open_id),
        "Content-Type": "application/json",
    }

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_body,
            timeout=20,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"腾讯文档 Open API 调用失败：{exc}",
        ) from exc

    return result


def extract_rows_from_api_response(response_data: Any) -> list[Any]:
    """从 Open API 响应中尽量提取表格行数据。"""

    if isinstance(response_data, list):
        return response_data

    if not isinstance(response_data, dict):
        return []

    for key in ("rows", "values", "records"):
        value = response_data.get(key)
        if isinstance(value, list):
            return value

    data = response_data.get("data")
    if data is not None:
        return extract_rows_from_api_response(data)

    return []


def normalize_api_rows(rows: list[Any]) -> list[dict[str, Any]]:
    """把 Open API 返回的行数据转换为本地 Reagent 字段。"""

    if not rows:
        return []

    normalized_rows: list[dict[str, Any]] = []
    if all(isinstance(row, dict) for row in rows):
        for row in rows:
            row_dict = dict(row)
            if any(column in row_dict for column in FILE_COLUMN_MAPPING):
                normalized_rows.append(normalize_reagent_row(row_dict))
            else:
                normalized_rows.append(row_dict)
        return normalized_rows

    if all(isinstance(row, list) for row in rows):
        headers = [str(header).strip() for header in rows[0]]
        for values in rows[1:]:
            raw_row = dict(zip(headers, values))
            normalized_rows.append(normalize_reagent_row(raw_row))
        return normalized_rows

    return normalized_rows


def fetch_tencent_doc_rows() -> list[dict[str, Any]]:
    """从真实腾讯文档 Open API 读取表格行数据。"""

    require_api_config(readonly=True)
    response_data = tencent_openapi_request(
        method="GET",
        path=settings.TENCENT_DOC_READ_PATH,
        params={
            "doc_id": settings.TENCENT_DOC_DOC_ID,
            "sheet_id": settings.TENCENT_DOC_SHEET_ID,
            "range": settings.TENCENT_DOC_SHEET_RANGE,
        },
    )
    return normalize_api_rows(extract_rows_from_api_response(response_data))


def update_tencent_doc_row(row: dict[str, Any]) -> dict[str, Any]:
    """通过真实腾讯文档 Open API 写回单行表格数据。"""

    require_api_config(readonly=False)
    return tencent_openapi_request(
        method="POST",
        path=settings.TENCENT_DOC_UPDATE_PATH,
        json_body={
            "doc_id": settings.TENCENT_DOC_DOC_ID,
            "sheet_id": settings.TENCENT_DOC_SHEET_ID,
            "range": settings.TENCENT_DOC_SHEET_RANGE,
            "row": row,
        },
    )

    raise NotImplementedError("真实腾讯文档写入 API 尚未接入")


def create_sync_log(
    db: Session,
    sync_type: str,
    status_value: str,
    message: str,
    source: str = "tencent_docs_mock",
    detail_json: str | None = None,
) -> SyncLog:
    """写入同步日志，但不主动提交事务。"""

    sync_log = SyncLog(
        source=source,
        sync_type=sync_type,
        status=status_value,
        message=message,
        detail_json=detail_json,
    )
    db.add(sync_log)
    db.flush()
    return sync_log


def write_failed_sync_log_safely(
    db: Session,
    sync_type: str,
    message: str,
    source: str = "tencent_docs_api",
) -> None:
    """尽量记录失败同步日志，日志写入失败时不覆盖原始错误。"""

    try:
        db.rollback()
        create_sync_log(
            db=db,
            sync_type=sync_type,
            status_value="failed",
            message=message,
            source=source,
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()


def import_rows_to_local_db(
    db: Session,
    rows: list[dict[str, Any]],
) -> tuple[int, int]:
    """把行数据导入本地 Reagent 表，同名试剂已存在则跳过。"""

    imported_count = 0
    skipped_count = 0

    for row in rows:
        name_cn = str(row.get("name_cn", "")).strip()
        if not name_cn:
            skipped_count += 1
            continue

        existing_reagent = db.execute(
            select(Reagent).where(Reagent.name_cn == name_cn)
        ).scalar_one_or_none()
        if existing_reagent is not None:
            skipped_count += 1
            continue

        db.add(Reagent(**row))
        imported_count += 1

    return imported_count, skipped_count


def export_local_db_to_rows(db: Session) -> list[dict[str, Any]]:
    """把本地 Reagent 表转换为模拟腾讯文档行数据。"""

    stmt = select(Reagent).order_by(Reagent.id.asc())
    reagents = db.execute(stmt).scalars().all()
    return [
        {
            "id": reagent.id,
            "name_cn": reagent.name_cn,
            "name_en": reagent.name_en,
            "cas_no": reagent.cas_no,
            "category": reagent.category,
            "specification": reagent.specification,
            "unit": reagent.unit,
            "current_quantity": reagent.current_quantity,
            "warning_threshold": reagent.warning_threshold,
            "location": reagent.location,
            "supplier": reagent.supplier,
            "hazard_level": reagent.hazard_level,
            "expiry_date": reagent.expiry_date.isoformat() if reagent.expiry_date else None,
            "remark": reagent.remark,
        }
        for reagent in reagents
    ]


def is_blank(value: Any) -> bool:
    """判断单元格是否为空。"""

    return value is None or pd.isna(value) or str(value).strip() == ""


def clean_text(value: Any) -> str | None:
    """把 Excel/CSV 单元格转换为字符串，空值返回 None。"""

    if is_blank(value):
        return None
    return str(value).strip()


def clean_float(value: Any) -> float:
    """把数量类单元格转换为 float，空值按 0 处理。"""

    if is_blank(value):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("数量字段必须是数字") from exc


def clean_date(value: Any) -> date | None:
    """把有效期单元格转换为 date，空值返回 None。"""

    if is_blank(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError("有效期格式不正确")
    return parsed.date()


def normalize_reagent_row(raw_row: dict[str, Any]) -> dict[str, Any]:
    """将中文列名行数据映射为 Reagent 字段。"""

    reagent_data: dict[str, Any] = {}
    for column_name, field_name in FILE_COLUMN_MAPPING.items():
        if column_name not in raw_row:
            continue

        value = raw_row[column_name]
        if field_name in {"current_quantity", "warning_threshold"}:
            reagent_data[field_name] = clean_float(value)
        elif field_name == "expiry_date":
            reagent_data[field_name] = clean_date(value)
        else:
            reagent_data[field_name] = clean_text(value)

    if not reagent_data.get("name_cn"):
        raise ValueError("试剂中文名不能为空")

    reagent_data.setdefault("unit", "瓶")
    reagent_data.setdefault("current_quantity", 0.0)
    reagent_data.setdefault("warning_threshold", 10.0)
    return reagent_data


def read_reagent_rows_from_file(file_name: str, content: bytes) -> tuple[list[dict[str, Any]], int]:
    """读取上传的 Excel/CSV 文件，并转换为 Reagent 字段行数据。"""

    suffix = Path(file_name).suffix.lower()
    if suffix == ".xlsx":
        dataframe = pd.read_excel(BytesIO(content), engine="openpyxl")
    elif suffix == ".csv":
        dataframe = pd.read_csv(BytesIO(content), encoding="utf-8-sig")
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 .xlsx 或 .csv 文件",
        )

    rows: list[dict[str, Any]] = []
    failed_count = 0
    for raw_row in dataframe.to_dict(orient="records"):
        try:
            rows.append(normalize_reagent_row(raw_row))
        except ValueError:
            failed_count += 1
    return rows, failed_count


def upsert_reagent_rows(
    db: Session,
    rows: list[dict[str, Any]],
) -> tuple[int, int, int]:
    """按 CAS 号优先、中文名兜底，将行数据新增或更新到 Reagent 表。"""

    created_count = 0
    updated_count = 0
    failed_count = 0

    for row in rows:
        try:
            cas_no = clean_text(row.get("cas_no"))
            name_cn = clean_text(row.get("name_cn"))
            if cas_no:
                stmt = select(Reagent).where(Reagent.cas_no == cas_no)
            else:
                stmt = select(Reagent).where(Reagent.name_cn == name_cn)

            reagent = db.execute(stmt).scalar_one_or_none()
            if reagent is None:
                db.add(Reagent(**row))
                created_count += 1
                continue

            for field_name, value in row.items():
                setattr(reagent, field_name, value)
            updated_count += 1
        except Exception:
            failed_count += 1

    return created_count, updated_count, failed_count


def export_local_db_to_file_rows(db: Session) -> list[dict[str, Any]]:
    """将本地 Reagent 表转换为带中文列名的导出行。"""

    rows = export_local_db_to_rows(db)
    export_rows: list[dict[str, Any]] = []
    for row in rows:
        export_rows.append(
            {
                column_name: row.get(field_name)
                for field_name, column_name in FILE_EXPORT_COLUMNS.items()
            }
        )
    return export_rows


@router.get(
    "/status",
    response_model=UnifiedSyncStatusResponse,
    summary="查询腾讯文档同步配置状态",
)
def get_tencent_docs_status(
    current_user: User = Depends(require_roles("manager", "admin", "superadmin")),
) -> UnifiedSyncStatusResponse:
    """返回腾讯文档相关配置是否已填写。"""

    _ = current_user
    return UnifiedSyncStatusResponse(**get_status_payload())


@router.get(
    "/oauth/url",
    response_model=OAuthUrlResponse,
    summary="生成腾讯文档 OAuth 授权地址",
)
def get_oauth_url(
    state: str | None = Query(default=None, description="可选 state 参数"),
    current_user: User = Depends(require_roles("admin", "superadmin")),
) -> OAuthUrlResponse:
    """生成 OAuth2 授权地址，由用户在浏览器中完成授权。"""

    _ = current_user
    return OAuthUrlResponse(oauth_url=build_oauth_url(state=state))


@router.post(
    "/oauth/token",
    response_model=TokenResponse,
    summary="使用 code 换取腾讯文档 token",
)
def create_oauth_token(
    code: str = Query(..., description="OAuth 回调获得的 code"),
    current_user: User = Depends(require_roles("admin", "superadmin")),
) -> TokenResponse:
    """使用授权 code 换取 token，并保存到本地 JSON 文件。"""

    _ = current_user
    token_data = exchange_code_for_token(code)
    return TokenResponse(
        token_saved=True,
        expires_in=token_data.get("expires_in"),
        has_refresh_token=bool(token_data.get("refresh_token")),
    )


@router.post(
    "/oauth/refresh",
    response_model=TokenResponse,
    summary="刷新腾讯文档 access_token",
)
def refresh_oauth_token(
    refresh_token: str | None = Query(default=None, description="可选 refresh_token，默认读取本地 token 文件"),
    current_user: User = Depends(require_roles("admin", "superadmin")),
) -> TokenResponse:
    """刷新 access_token，并覆盖保存到本地 JSON 文件。"""

    _ = current_user
    token_data = refresh_access_token(refresh_token=refresh_token)
    return TokenResponse(
        token_saved=True,
        expires_in=token_data.get("expires_in"),
        has_refresh_token=bool(token_data.get("refresh_token")),
    )


@router.post(
    "/mock/import",
    response_model=UnifiedSyncImportResponse,
    summary="mock 导入腾讯文档数据",
)
def mock_import_from_tencent_docs(
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> UnifiedSyncImportResponse:
    """使用本地模拟数据导入几个试剂到数据库。"""

    return run_mock_import(db=db, current_user=current_user)


@router.post(
    "/mock/export",
    response_model=UnifiedSyncExportResponse,
    summary="mock 导出本地库存数据",
)
def mock_export_to_tencent_docs(
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> UnifiedSyncExportResponse:
    """读取当前本地 Reagent 表，并返回模拟导出数据。"""

    _ = current_user
    return run_mock_export(db=db)


@router.post(
    "/api/import",
    response_model=FileImportResponse,
    summary="从真实腾讯文档 Open API 导入试剂数据",
)
def api_import_from_tencent_docs(
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> FileImportResponse:
    """从腾讯文档 Open API 读取表格行，并新增或更新到本地数据库。"""

    _ = current_user
    try:
        rows = fetch_tencent_doc_rows()
        created_count, updated_count, failed_count = upsert_reagent_rows(db, rows)
        sync_log = create_sync_log(
            db=db,
            sync_type="api_import",
            status_value="success",
            message=(
                f"真实 API 导入完成：新增 {created_count} 条，"
                f"更新 {updated_count} 条，失败 {failed_count} 条"
            ),
            source="tencent_docs_api",
        )
        db.commit()
        db.refresh(sync_log)
    except HTTPException as exc:
        write_failed_sync_log_safely(db, "api_import", str(exc.detail))
        raise
    except SQLAlchemyError as exc:
        write_failed_sync_log_safely(db, "api_import", "真实 API 导入写入数据库失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="真实 API 导入写入数据库失败",
        ) from exc
    except Exception as exc:
        write_failed_sync_log_safely(db, "api_import", f"真实 API 导入失败：{exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"真实 API 导入失败：{exc}",
        ) from exc

    return FileImportResponse(
        created_count=created_count,
        updated_count=updated_count,
        failed_count=failed_count,
        log_id=sync_log.id,
    )


@router.post(
    "/api/export",
    response_model=ApiExportResponse,
    summary="通过真实腾讯文档 Open API 写回本地试剂数据",
)
def api_export_to_tencent_docs(
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> ApiExportResponse:
    """读取本地 Reagent 表，并逐行调用腾讯文档 Open API 写回。"""

    _ = current_user
    exported_count = 0
    failed_count = 0

    try:
        require_api_config(readonly=False)
        rows = export_local_db_to_rows(db)
        for row in rows:
            try:
                update_tencent_doc_row(row)
                exported_count += 1
            except HTTPException:
                failed_count += 1

        sync_log = create_sync_log(
            db=db,
            sync_type="api_export",
            status_value="success" if failed_count == 0 else "partial_success",
            message=f"真实 API 导出完成：成功 {exported_count} 条，失败 {failed_count} 条",
            source="tencent_docs_api",
        )
        db.commit()
        db.refresh(sync_log)
    except HTTPException as exc:
        write_failed_sync_log_safely(db, "api_export", str(exc.detail))
        raise
    except SQLAlchemyError as exc:
        write_failed_sync_log_safely(db, "api_export", "真实 API 导出写入同步日志失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="真实 API 导出写入同步日志失败",
        ) from exc
    except Exception as exc:
        write_failed_sync_log_safely(db, "api_export", f"真实 API 导出失败：{exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"真实 API 导出失败：{exc}",
        ) from exc

    return ApiExportResponse(
        exported_count=exported_count,
        failed_count=failed_count,
        log_id=sync_log.id,
    )


@router.post(
    "/import-file",
    response_model=UnifiedSyncImportResponse,
    summary="从 Excel/CSV 导入本地库存数据",
)
async def import_file_to_local_db(
    file: UploadFile = File(..., description="支持 .xlsx / .xls / .csv 文件"),
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> UnifiedSyncImportResponse:
    """上传 Excel/CSV 文件。

    xlsx 按历史库存宽表导入库存流水；csv 按试剂主数据表导入。
    """

    return await run_excel_import(db=db, current_user=current_user, file=file)


@router.get(
    "/export-file",
    summary="导出本地试剂数据为 Excel",
)
def export_file_from_local_db(
    year: int = Query(default=2026, ge=2000, le=2100, description="导出年份"),
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> FileResponse:
    """将本地库存流水导出为接近历史模板样式的 xlsx 文件。"""

    _ = current_user
    return run_excel_export(db=db, year=year)


@router.get(
    "/logs",
    response_model=list[SyncLogResponse],
    summary="查询同步日志",
)
def list_sync_logs(
    skip: int = Query(default=0, ge=0, description="跳过记录数"),
    limit: int = Query(default=100, ge=1, le=500, description="返回记录数上限"),
    current_user: User = Depends(require_roles("manager", "admin", "superadmin")),
    db: Session = Depends(get_db),
) -> list[SyncLog]:
    """查询同步日志，结果按 ID 倒序排列。"""

    _ = current_user
    return list_sync_logs_data(db=db, skip=skip, limit=limit)
