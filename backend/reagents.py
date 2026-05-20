"""试剂信息管理 API。"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models import Reagent, User
from schemas import ReagentCreate, ReagentOptionResponse, ReagentResponse, ReagentUpdate


router = APIRouter(prefix="/reagents", tags=["reagents"])


def get_reagent_or_404(db: Session, reagent_id: int) -> Reagent:
    """按 ID 获取试剂，不存在时抛出 404。"""

    reagent = db.get(Reagent, reagent_id)
    if reagent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="试剂不存在",
        )
    return reagent


@router.post(
    "/",
    response_model=ReagentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="新增试剂",
)
def create_reagent(
    reagent_in: ReagentCreate,
    current_user: User = Depends(require_roles("manager", "admin", "superadmin")),
    db: Session = Depends(get_db),
) -> Reagent:
    """新增一条试剂基础信息。"""

    _ = current_user
    reagent = Reagent(**reagent_in.model_dump())
    db.add(reagent)

    try:
        db.commit()
        db.refresh(reagent)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="新增试剂失败",
        ) from exc

    return reagent


@router.get(
    "/",
    response_model=list[ReagentResponse],
    summary="查询试剂列表",
)
def list_reagents(
    keyword: str | None = Query(
        default=None,
        description="按中文名、英文名、CAS 号模糊搜索",
    ),
    category: str | None = Query(
        default=None,
        description="按试剂分类筛选",
    ),
    low_stock: bool = Query(
        default=False,
        description="是否只查看低库存试剂",
    ),
    skip: int = Query(
        default=0,
        ge=0,
        description="跳过记录数",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="返回记录数上限",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Reagent]:
    """查询试剂列表，结果按 ID 倒序排列。"""

    _ = current_user
    stmt = select(Reagent)

    if keyword:
        like_keyword = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                Reagent.name_cn.ilike(like_keyword),
                Reagent.name_en.ilike(like_keyword),
                Reagent.cas_no.ilike(like_keyword),
            )
        )

    if category:
        stmt = stmt.where(Reagent.category == category.strip())

    if low_stock:
        stmt = stmt.where(Reagent.current_quantity <= Reagent.warning_threshold)

    stmt = stmt.order_by(Reagent.id.asc()).offset(skip).limit(limit)
    return list(db.execute(stmt).scalars().all())


@router.get(
    "/categories/list",
    response_model=list[str],
    summary="查询试剂分类列表",
)
def list_categories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[str]:
    """返回当前数据库中已有的非空试剂分类。"""

    _ = current_user
    stmt = (
        select(distinct(Reagent.category))
        .where(Reagent.category.is_not(None), Reagent.category != "")
        .order_by(Reagent.category.asc())
    )
    return list(db.execute(stmt).scalars().all())


@router.get(
    "/options",
    response_model=list[ReagentOptionResponse],
    summary="查询试剂选择器选项",
)
def list_reagent_options(
    keyword: str | None = Query(
        default=None,
        description="按中文名、标准名、别名、CAS 号模糊搜索",
    ),
    category: str | None = Query(
        default=None,
        description="按试剂分类筛选",
    ),
    include_inactive: bool = Query(
        default=False,
        description="是否包含停用试剂；当前 Reagent 模型暂无 is_active 字段，暂时忽略",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="返回选项数量上限",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ReagentOptionResponse]:
    """返回适合前端下拉选择器使用的试剂选项。

    keyword 为空时默认返回系统预置试剂；keyword 非空时按多个名称字段模糊搜索。
    """

    _ = current_user
    _ = include_inactive
    stmt = select(Reagent)
    cleaned_keyword = keyword.strip() if keyword else ""

    if cleaned_keyword:
        like_keyword = f"%{cleaned_keyword}%"
        stmt = stmt.where(
            or_(
                Reagent.name_cn.ilike(like_keyword),
                Reagent.standard_name.ilike(like_keyword),
                Reagent.alias_name.ilike(like_keyword),
                Reagent.cas_no.ilike(like_keyword),
            )
        )
    else:
        stmt = stmt.where(Reagent.is_preset.is_(True))

    if category:
        stmt = stmt.where(Reagent.category == category.strip())

    stmt = stmt.order_by(Reagent.display_order.asc(), Reagent.id.asc()).limit(limit)
    reagents = db.execute(stmt).scalars().all()

    return [
        ReagentOptionResponse(
            id=reagent.id,
            label=reagent.name_cn,
            value=reagent.id,
            name_cn=reagent.name_cn,
            standard_name=reagent.standard_name,
            category=reagent.category,
            current_quantity=reagent.current_quantity,
            unit=reagent.unit,
            warning_threshold=reagent.warning_threshold,
            location=reagent.location,
            hazard_level=reagent.hazard_level,
        )
        for reagent in reagents
    ]


@router.get(
    "/{reagent_id}",
    response_model=ReagentResponse,
    summary="查询试剂详情",
)
def get_reagent(
    reagent_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Reagent:
    """按 ID 查询试剂详情。"""

    _ = current_user
    return get_reagent_or_404(db, reagent_id)


@router.put(
    "/{reagent_id}",
    response_model=ReagentResponse,
    summary="更新试剂信息",
)
def update_reagent(
    reagent_id: int,
    reagent_in: ReagentUpdate,
    current_user: User = Depends(require_roles("manager", "admin", "superadmin")),
    db: Session = Depends(get_db),
) -> Reagent:
    """更新试剂基础信息，不处理入库、出库、库存校正。"""

    _ = current_user
    reagent = get_reagent_or_404(db, reagent_id)
    update_data = reagent_in.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(reagent, field, value)

    try:
        db.commit()
        db.refresh(reagent)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新试剂失败",
        ) from exc

    return reagent


@router.delete(
    "/{reagent_id}",
    summary="删除试剂",
)
def delete_reagent(
    reagent_id: int,
    current_user: User = Depends(require_roles("admin", "superadmin")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """删除指定试剂，删除前先检查记录是否存在。"""

    _ = current_user
    reagent = get_reagent_or_404(db, reagent_id)
    db.delete(reagent)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除试剂失败",
        ) from exc

    return {
        "message": "试剂删除成功",
        "reagent_id": reagent_id,
    }
