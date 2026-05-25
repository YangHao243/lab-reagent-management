"""Tencent Docs Direct Token expiry metadata helpers.

Direct Token 模式下，后端无法从 access_token 本身解析真实过期时间。
这里仅保存和计算管理员手动维护的过期提醒时间，不保存 token 明文。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from models import SystemSetting
from utils.timezone import now_beijing


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
TOKEN_EXPIRY_KEY = "tencent_docs_token_expires_at"
TOKEN_EXPIRY_WARNING_DAYS = 7


def parse_token_expiry(value: str) -> datetime:
    """Parse token expiry input and normalize it to aware Asia/Shanghai time."""

    text = (value or "").strip()
    if not text:
        raise ValueError("token_expires_at 不能为空")
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("token_expires_at 时间格式无效") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING_TZ)
    return parsed.astimezone(BEIJING_TZ).replace(microsecond=0)


def format_token_expiry(value: datetime) -> str:
    """Return an ISO string with +08:00 offset for frontend display and storage."""

    return value.astimezone(BEIJING_TZ).replace(microsecond=0).isoformat()


def format_remaining_text(seconds: int | None) -> str:
    """Format remaining seconds as a compact Chinese duration."""

    if seconds is None:
        return "-"
    if seconds <= 0:
        return "已过期"
    days, remainder = divmod(seconds, 24 * 60 * 60)
    hours, remainder = divmod(remainder, 60 * 60)
    minutes, _ = divmod(remainder, 60)
    if days:
        return f"{days}天{hours}小时"
    if hours:
        return f"{hours}小时{minutes}分钟"
    return f"{minutes}分钟"


def get_token_expiry_setting(db: Session) -> tuple[str | None, str]:
    """Read expiry metadata from DB first, then environment fallback."""

    setting = db.execute(
        select(SystemSetting).where(SystemSetting.key == TOKEN_EXPIRY_KEY)
    ).scalar_one_or_none()
    if setting and setting.value and setting.value.strip():
        return setting.value.strip(), "database"
    env_value = (settings.TENCENT_DOCS_TOKEN_EXPIRES_AT or "").strip()
    if env_value:
        return env_value, "env"
    return None, "none"


def get_token_expiry_info(db: Session) -> dict[str, Any]:
    """Return normalized expiry metadata and status for Tencent Docs token."""

    raw_value, source = get_token_expiry_setting(db)
    if not raw_value:
        return {
            "token_expires_at": None,
            "source": "none",
            "status": "unknown",
            "remaining_seconds": None,
            "remaining_text": "-",
            "warning_threshold_days": TOKEN_EXPIRY_WARNING_DAYS,
            "expiring_soon": False,
        }
    try:
        expires_at = parse_token_expiry(raw_value)
    except ValueError:
        return {
            "token_expires_at": raw_value,
            "source": source,
            "status": "unknown",
            "remaining_seconds": None,
            "remaining_text": "时间格式无效",
            "warning_threshold_days": TOKEN_EXPIRY_WARNING_DAYS,
            "expiring_soon": False,
        }

    now = now_beijing().replace(tzinfo=BEIJING_TZ)
    remaining_seconds = int((expires_at - now).total_seconds())
    warning_seconds = TOKEN_EXPIRY_WARNING_DAYS * 24 * 60 * 60
    if remaining_seconds <= 0:
        status_value = "expired"
    elif remaining_seconds <= warning_seconds:
        status_value = "expiring_soon"
    else:
        status_value = "valid"

    return {
        "token_expires_at": format_token_expiry(expires_at),
        "source": source,
        "status": status_value,
        "remaining_seconds": remaining_seconds,
        "remaining_text": format_remaining_text(remaining_seconds),
        "warning_threshold_days": TOKEN_EXPIRY_WARNING_DAYS,
        "expiring_soon": status_value == "expiring_soon",
    }


def save_token_expiry_setting(
    db: Session,
    token_expires_at: str | None,
    updated_by: int | None = None,
) -> dict[str, Any]:
    """Save or clear the manually maintained token expiry metadata."""

    setting = db.execute(
        select(SystemSetting).where(SystemSetting.key == TOKEN_EXPIRY_KEY)
    ).scalar_one_or_none()
    if token_expires_at is None or not str(token_expires_at).strip():
        if setting:
            db.delete(setting)
            db.flush()
        return get_token_expiry_info(db)

    parsed = parse_token_expiry(str(token_expires_at))
    normalized_value = format_token_expiry(parsed)
    if setting is None:
        setting = SystemSetting(
            key=TOKEN_EXPIRY_KEY,
            value=normalized_value,
            updated_by=updated_by,
        )
        db.add(setting)
    else:
        setting.value = normalized_value
        setting.updated_by = updated_by
    db.flush()
    return get_token_expiry_info(db)
