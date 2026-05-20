"""FastAPI 鉴权与角色权限依赖。"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import decode_access_token
from database import get_db
from models import User


security = HTTPBearer(auto_error=False)


def unauthorized() -> HTTPException:
    """统一返回未登录或 token 失效错误。"""

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或登录已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )


def forbidden() -> HTTPException:
    """统一返回无权限错误。"""

    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="当前用户无权限执行该操作",
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """解析 Bearer token，并返回当前启用用户。"""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise unauthorized()

    user: User | None = None
    user_id = payload.get("user_id")
    if user_id is not None:
        try:
            user = db.get(User, int(user_id))
        except (TypeError, ValueError):
            user = None

    if user is None:
        username = payload.get("sub") or payload.get("username")
        if username:
            stmt = select(User).where(User.username == str(username))
            user = db.execute(stmt).scalar_one_or_none()

    if user is None or not user.is_active:
        raise unauthorized()

    return user


def require_roles(*roles: str) -> Callable[[User], User]:
    """创建角色权限依赖，用法：Depends(require_roles("admin", "superadmin"))。"""

    allowed_roles = set(roles)

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise forbidden()
        return current_user

    return dependency
