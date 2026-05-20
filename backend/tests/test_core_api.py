"""后端核心接口基础测试。

测试使用独立 SQLite 命名内存库，不会读写正式的 backend/lab_reagent.db。
"""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]

# 必须在导入 main/database 之前设置测试数据库地址，确保 SQLAlchemy engine 指向测试库。
os.environ["DATABASE_URL"] = "sqlite:///file:lab_reagent_pytest?mode=memory&cache=shared&uri=true"
sys.path.insert(0, str(BACKEND_DIR))

from auth import hash_password  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
import models  # noqa: E402,F401
from main import app  # noqa: E402
from models import User  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    """为每个测试创建干净的数据表。"""

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.add(
            User(
                username="superadmin",
                full_name="测试超级管理员",
                password_hash=hash_password("Admin@123456"),
                role="superadmin",
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()
    return TestClient(app)


def auth_headers(client: TestClient) -> dict[str, str]:
    """登录测试管理员并返回 Authorization header。"""

    response = client.post(
        "/users/login",
        json={"username": "superadmin", "password": "Admin@123456"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health(client: TestClient) -> None:
    """健康检查接口应正常返回服务状态。"""

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_reagent_inventory_and_alert_flow(client: TestClient) -> None:
    """验证试剂新增、列表查询、入库、出库和低库存查询的核心闭环。"""

    headers = auth_headers(client)
    reagent_payload = {
        "name_cn": "pytest测试丙酮",
        "name_en": "Acetone",
        "cas_no": "PYTEST-67-64-1",
        "category": "有机溶剂",
        "specification": "500ml",
        "unit": "瓶",
        "current_quantity": 2,
        "warning_threshold": 5,
        "location": "测试试剂柜A",
        "supplier": "pytest供应商",
        "hazard_level": "易燃",
        "remark": "pytest自动化测试数据",
    }

    create_response = client.post("/reagents", json=reagent_payload, headers=headers)
    assert create_response.status_code == 201
    created_reagent = create_response.json()
    reagent_id = created_reagent["id"]
    assert created_reagent["name_cn"] == reagent_payload["name_cn"]

    list_response = client.get("/reagents", params={"keyword": "pytest测试丙酮"}, headers=headers)
    assert list_response.status_code == 200
    reagents = list_response.json()
    assert any(item["id"] == reagent_id for item in reagents)

    in_response = client.post(
        "/inventory/in",
        json={
            "reagent_id": reagent_id,
            "quantity": 3,
            "reason": "领料入库",
            "remark": "接口测试入库",
        },
        headers=headers,
    )
    assert in_response.status_code == 200
    in_record = in_response.json()
    assert in_record["operation_type"] == "in"
    assert in_record["quantity_change"] == 3
    assert in_record["after_quantity"] == 5

    out_response = client.post(
        "/inventory/out",
        json={
            "reagent_id": reagent_id,
            "quantity": 2,
            "reason": "实验领用",
            "remark": "接口测试出库",
        },
        headers=headers,
    )
    assert out_response.status_code == 200
    out_record = out_response.json()
    assert out_record["operation_type"] == "out"
    assert out_record["quantity_change"] == -2
    assert out_record["after_quantity"] == 3

    records_response = client.get("/inventory/records", params={"reagent_id": reagent_id}, headers=headers)
    assert records_response.status_code == 200
    records = records_response.json()
    assert len(records) == 2
    assert {record["operation_type"] for record in records} == {"in", "out"}

    low_stock_response = client.get("/alerts/low-stock", headers=headers)
    assert low_stock_response.status_code == 200
    low_stock_reagents = low_stock_response.json()
    assert any(item["id"] == reagent_id for item in low_stock_reagents)


def test_auth_required_and_role_forbidden(client: TestClient) -> None:
    """未登录应返回 401，低权限用户访问用户管理应返回 403。"""

    no_token_response = client.get("/reagents")
    assert no_token_response.status_code == 401

    admin_headers = auth_headers(client)
    create_member_response = client.post(
        "/users/register",
        json={
            "username": "member-user",
            "password": "Member@123456",
            "full_name": "普通成员",
            "role": "member",
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert create_member_response.status_code == 201

    member_login_response = client.post(
        "/users/login",
        json={"username": "member-user", "password": "Member@123456"},
    )
    assert member_login_response.status_code == 200
    member_token = member_login_response.json()["access_token"]

    forbidden_response = client.get(
        "/users/",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert forbidden_response.status_code == 403
