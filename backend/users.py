"""用户管理与登录 API。"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from auth import create_access_token, hash_password, verify_password
from database import get_db
from dependencies import forbidden, get_current_user, require_roles
from models import User
from schemas import UserCreate, UserLogin, UserLoginResponse, UserResponse, UserUpdate


router = APIRouter(prefix="/users", tags=["users"])

ALLOWED_ROLES = {"member", "admin", "manager", "superadmin"}


def validate_role(role: str) -> None:
    """校验用户角色是否合法。"""

    if role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"角色不合法，可选值：{', '.join(sorted(ALLOWED_ROLES))}",
        )


def get_user_by_username(db: Session, username: str) -> User | None:
    """按用户名查询用户。"""

    stmt = select(User).where(User.username == username)
    return db.execute(stmt).scalar_one_or_none()


def get_user_or_404(db: Session, user_id: int) -> User:
    """按 ID 查询用户，不存在时返回 404。"""

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    return user


def assert_admin_can_manage_user(current_user: User, target_user: User) -> None:
    """限制 admin 修改或禁用 superadmin，superadmin 不受此限制。"""

    if target_user.role == "superadmin" and current_user.role != "superadmin":
        raise forbidden()


def assert_admin_can_assign_role(current_user: User, target_role: str | None) -> None:
    """限制 admin 创建或提升 superadmin。"""

    if target_role == "superadmin" and current_user.role != "superadmin":
        raise forbidden()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建用户",
)
def register_user(
    user_in: UserCreate,
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> User:
    """创建新用户，用户名不允许重复。"""

    validate_role(user_in.role)
    assert_admin_can_assign_role(current_user, user_in.role)

    existing_user = get_user_by_username(db, user_in.username)
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    user = User(
        username=user_in.username,
        full_name=user_in.full_name,
        password_hash=hash_password(user_in.password),
        role=user_in.role,
        email=user_in.email,
        phone=user_in.phone,
        wechat_openid=user_in.wechat_openid,
        is_active=user_in.is_active,
    )
    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户信息已存在，请检查用户名、邮箱或微信 OpenID",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="创建用户失败",
        ) from exc

    return user


@router.post(
    "/login",
    response_model=UserLoginResponse,
    summary="账号密码登录",
)
def login_user(
    login_in: UserLogin,
    db: Session = Depends(get_db),
) -> UserLoginResponse:
    """使用用户名和密码登录，返回 JWT token 和用户信息。"""

    user = get_user_by_username(db, login_in.username)
    if user is None or not verify_password(login_in.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "role": user.role,
        }
    )
    return UserLoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="查询当前登录用户",
)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    """返回当前登录用户信息，不包含 password_hash。"""

    return current_user


@router.get(
    "/",
    response_model=list[UserResponse],
    summary="查询用户列表",
)
def list_users(
    skip: int = Query(default=0, ge=0, description="跳过记录数"),
    limit: int = Query(default=100, ge=1, le=500, description="返回记录数上限"),
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> list[User]:
    """查询用户列表，按 ID 倒序返回。"""

    _ = current_user
    stmt = select(User).order_by(User.id.desc()).offset(skip).limit(limit)
    return list(db.execute(stmt).scalars().all())


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="查询用户详情",
)
def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """按 ID 查询用户详情。"""

    user = get_user_or_404(db, user_id)
    if current_user.role not in {"admin", "superadmin"} and current_user.id != user.id:
        raise forbidden()
    return user


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="更新用户信息和角色",
)
def update_user(
    user_id: int,
    user_in: UserUpdate,
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> User:
    """更新用户基础信息和角色，暂不处理密码修改。"""

    user = get_user_or_404(db, user_id)
    assert_admin_can_manage_user(current_user, user)
    update_data = user_in.model_dump(exclude_unset=True)

    if "role" in update_data and update_data["role"] is not None:
        validate_role(update_data["role"])
        assert_admin_can_assign_role(current_user, update_data["role"])

    if user.id == current_user.id and update_data.get("is_active") is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能禁用当前登录用户",
        )

    for field_name, value in update_data.items():
        setattr(user, field_name, value)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户信息已存在，请检查邮箱或微信 OpenID",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新用户失败",
        ) from exc

    return user


@router.delete(
    "/{user_id}",
    response_model=UserResponse,
    summary="禁用用户",
)
def disable_user(
    user_id: int,
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> User:
    """禁用用户，不做物理删除。"""

    user = get_user_or_404(db, user_id)
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能禁用当前登录用户",
        )
    assert_admin_can_manage_user(current_user, user)
    user.is_active = False

    try:
        db.commit()
        db.refresh(user)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="禁用用户失败",
        ) from exc

    return user
