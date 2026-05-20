"""用户认证基础工具函数。

本模块只提供密码哈希、密码校验、JWT 生成和解析能力，不定义 FastAPI 路由。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.exc import PasslibHashWarning

from config import settings


ALGORITHM = "HS256"


def _patch_bcrypt_compatibility() -> None:
    """兼容 passlib 1.7.x 与 bcrypt 5.x 的本地开发环境。

    passlib 1.7.x 会读取 bcrypt.__about__.__version__，而 bcrypt 5.x 已移除该属性；
    同时 bcrypt 5.x 对超过 72 字节的内部检测密码会直接报错。这里做最小兼容处理，
    仍然让实际密码哈希和校验走 passlib 的 CryptContext。
    """

    if not hasattr(bcrypt, "__about__"):
        bcrypt.__about__ = SimpleNamespace(  # type: ignore[attr-defined]
            __version__=getattr(bcrypt, "__version__", "unknown")
        )

    original_hashpw = bcrypt.hashpw

    def compatible_hashpw(password: bytes, salt: bytes) -> bytes:
        if isinstance(password, (bytes, bytearray)) and len(password) > 72:
            password = bytes(password[:72])
        return original_hashpw(password, salt)

    bcrypt.hashpw = compatible_hashpw


_patch_bcrypt_compatibility()


# passlib[bcrypt] 密码上下文，后续用户模块统一使用这里的函数处理密码。
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    """生成密码哈希。"""

    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码和密码哈希是否匹配。"""

    try:
        return bool(pwd_context.verify(plain_password, hashed_password))
    except (ValueError, PasslibHashWarning):
        return False


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """创建 JWT access token。"""

    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """解析 JWT access token，解析失败或过期时返回 None。"""

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
        )
    except JWTError:
        return None

    return payload
