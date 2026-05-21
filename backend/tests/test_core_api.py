"""后端核心接口基础测试。

测试使用独立 SQLite 命名内存库，不会读写正式的 backend/lab_reagent.db。
"""

import os
import sys
from datetime import datetime
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
from models import InventoryRecord, Reagent, User  # noqa: E402


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


def create_test_reagent(client: TestClient, headers: dict[str, str], name: str) -> int:
    """创建一个库存从 0 开始的测试试剂。"""

    response = client.post(
        "/reagents/",
        json={
            "name_cn": name,
            "name_en": name,
            "cas_no": f"TEST-{name}",
            "category": "测试分类",
            "specification": "测试规格",
            "unit": "瓶",
            "current_quantity": 0,
            "warning_threshold": 1,
            "location": "测试位置",
            "hazard_level": "测试",
            "remark": "库存重算测试",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def stock_in(
    client: TestClient,
    headers: dict[str, str],
    reagent_id: int,
    quantity: int,
) -> dict:
    """执行一次测试入库。"""

    response = client.post(
        "/inventory/in",
        json={
            "reagent_id": reagent_id,
            "quantity": quantity,
            "operator_name": "测试员",
            "reason": "领料入库",
            "remark": "pytest 入库",
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def stock_out(
    client: TestClient,
    headers: dict[str, str],
    reagent_id: int,
    quantity: int,
) -> dict:
    """执行一次测试出库。"""

    response = client.post(
        "/inventory/out",
        json={
            "reagent_id": reagent_id,
            "quantity": quantity,
            "operator_name": "测试员",
            "reason": "实验领用",
            "remark": "pytest 出库",
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def get_stock(client: TestClient, headers: dict[str, str], reagent_id: int) -> float:
    """查询指定试剂当前库存。"""

    response = client.get(f"/inventory/stock/{reagent_id}", headers=headers)
    assert response.status_code == 200
    return response.json()["current_quantity"]


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
            "operator_name": "测试员",
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
            "operator_name": "测试员",
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


def test_delete_out_record_restores_stock(client: TestClient) -> None:
    """入库 100 -> 出库 20 -> 删除出库，库存应恢复为 100。"""

    headers = auth_headers(client)
    reagent_id = create_test_reagent(client, headers, "删除出库恢复库存")
    stock_in(client, headers, reagent_id, 100)
    out_record = stock_out(client, headers, reagent_id, 20)

    response = client.delete(f"/inventory/records/{out_record['id']}", headers=headers)

    assert response.status_code == 200
    assert get_stock(client, headers, reagent_id) == 100


def test_delete_first_out_record_recomputes_following_records(client: TestClient) -> None:
    """删除第一条出库后，后续出库 before/after 应重新计算。"""

    headers = auth_headers(client)
    reagent_id = create_test_reagent(client, headers, "删除第一条出库重算")
    stock_in(client, headers, reagent_id, 100)
    first_out = stock_out(client, headers, reagent_id, 20)
    second_out = stock_out(client, headers, reagent_id, 30)

    response = client.delete(f"/inventory/records/{first_out['id']}", headers=headers)

    assert response.status_code == 200
    assert get_stock(client, headers, reagent_id) == 70

    db = SessionLocal()
    try:
        second_record = db.get(InventoryRecord, second_out["id"])
        assert second_record is not None
        assert second_record.before_quantity == 100
        assert second_record.after_quantity == 70
    finally:
        db.close()


def test_delete_in_record_allows_following_out_to_go_negative(
    client: TestClient,
) -> None:
    """删除历史入库导致剩余出库为负时，现在允许删除并保留负库存。"""

    headers = auth_headers(client)
    reagent_id = create_test_reagent(client, headers, "删除入库允许负库存")
    in_record = stock_in(client, headers, reagent_id, 100)

    db = SessionLocal()
    try:
        reagent = db.get(Reagent, reagent_id)
        assert reagent is not None
        out_record = InventoryRecord(
            reagent_id=reagent_id,
            operation_type="out",
            quantity_change=-150,
            before_quantity=100,
            after_quantity=-50,
            operator_name="测试员",
            reason="实验领用",
            created_at=datetime(2026, 1, 2, 9, 0, 0),
        )
        reagent.current_quantity = -50
        db.add(out_record)
        db.commit()
        db.refresh(out_record)
        out_record_id = out_record.id
    finally:
        db.close()

    response = client.delete(f"/inventory/records/{in_record['id']}", headers=headers)

    assert response.status_code == 200
    assert get_stock(client, headers, reagent_id) == -150

    db = SessionLocal()
    try:
        remaining_in = db.get(InventoryRecord, in_record["id"])
        remaining_out = db.get(InventoryRecord, out_record_id)
        assert remaining_in is None
        assert remaining_out is not None
        assert remaining_out.before_quantity == 0
        assert remaining_out.after_quantity == -150
    finally:
        db.close()


def test_batch_delete_same_reagent_out_records(client: TestClient) -> None:
    """批量删除同一试剂的两条出库记录后，库存应回到入库后的数量。"""

    headers = auth_headers(client)
    reagent_id = create_test_reagent(client, headers, "批量删除同试剂出库")
    stock_in(client, headers, reagent_id, 100)
    first_out = stock_out(client, headers, reagent_id, 20)
    second_out = stock_out(client, headers, reagent_id, 30)

    response = client.post(
        "/inventory/records/batch-delete",
        json={"record_ids": [first_out["id"], second_out["id"]]},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["deleted_count"] == 2
    assert data["affected_reagent_ids"] == [reagent_id]
    assert get_stock(client, headers, reagent_id) == 100


def test_batch_delete_multiple_reagents(client: TestClient) -> None:
    """批量删除涉及多个试剂时，应分别重算各自库存。"""

    headers = auth_headers(client)
    reagent_a = create_test_reagent(client, headers, "批量删除试剂A")
    reagent_b = create_test_reagent(client, headers, "批量删除试剂B")
    stock_in(client, headers, reagent_a, 100)
    stock_in(client, headers, reagent_b, 50)
    out_a = stock_out(client, headers, reagent_a, 20)
    out_b = stock_out(client, headers, reagent_b, 10)

    response = client.post(
        "/inventory/records/batch-delete",
        json={"record_ids": [out_a["id"], out_b["id"]]},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["deleted_count"] == 2
    assert sorted(data["affected_reagent_ids"]) == sorted([reagent_a, reagent_b])
    assert get_stock(client, headers, reagent_a) == 100
    assert get_stock(client, headers, reagent_b) == 50


def test_batch_delete_forbidden_for_member(client: TestClient) -> None:
    """非超级管理员批量删除库存流水应返回 403，数据不变。"""

    headers = auth_headers(client)
    reagent_id = create_test_reagent(client, headers, "成员禁止批量删除")
    stock_in(client, headers, reagent_id, 100)
    out_record = stock_out(client, headers, reagent_id, 20)

    create_member_response = client.post(
        "/users/register",
        json={
            "username": "batch-member",
            "password": "Member@123456",
            "full_name": "普通成员",
            "role": "member",
            "is_active": True,
        },
        headers=headers,
    )
    assert create_member_response.status_code == 201
    member_login_response = client.post(
        "/users/login",
        json={"username": "batch-member", "password": "Member@123456"},
    )
    assert member_login_response.status_code == 200
    member_headers = {
        "Authorization": f"Bearer {member_login_response.json()['access_token']}"
    }

    response = client.post(
        "/inventory/records/batch-delete",
        json={"record_ids": [out_record["id"]]},
        headers=member_headers,
    )

    assert response.status_code == 403
    assert get_stock(client, headers, reagent_id) == 80


def test_batch_delete_empty_record_ids_returns_400(client: TestClient) -> None:
    """批量删除空列表应返回 400。"""

    headers = auth_headers(client)
    response = client.post(
        "/inventory/records/batch-delete",
        json={"record_ids": []},
        headers=headers,
    )

    assert response.status_code == 400


def test_delete_out_between_in_records_recomputes_stock(client: TestClient) -> None:
    """入库 100 -> 出库 20 -> 入库 10，删除出库后库存应为 110。"""

    headers = auth_headers(client)
    reagent_id = create_test_reagent(client, headers, "删除中间出库重算")
    stock_in(client, headers, reagent_id, 100)
    out_record = stock_out(client, headers, reagent_id, 20)
    stock_in(client, headers, reagent_id, 10)

    response = client.delete(f"/inventory/records/{out_record['id']}", headers=headers)

    assert response.status_code == 200
    assert get_stock(client, headers, reagent_id) == 110


def test_recompute_is_stable_when_records_have_same_created_at(
    client: TestClient,
) -> None:
    """多条相同 created_at 流水应按 id 二级排序稳定重算。"""

    headers = auth_headers(client)
    reagent_id = create_test_reagent(client, headers, "相同时间稳定排序")
    in_record = stock_in(client, headers, reagent_id, 100)
    first_out = stock_out(client, headers, reagent_id, 20)
    second_out = stock_out(client, headers, reagent_id, 30)

    same_time = datetime(2026, 1, 1, 9, 0, 0)
    db = SessionLocal()
    try:
        for record_id in [in_record["id"], first_out["id"], second_out["id"]]:
            record = db.get(InventoryRecord, record_id)
            assert record is not None
            record.created_at = same_time
        db.commit()
    finally:
        db.close()

    response = client.delete(f"/inventory/records/{first_out['id']}", headers=headers)

    assert response.status_code == 200
    assert get_stock(client, headers, reagent_id) == 70


def test_signed_quantity_keeps_negative_outbound_quantity() -> None:
    """历史出库数量已经为负数时，不应重复取负。"""

    from inventory import get_signed_quantity

    assert get_signed_quantity("out", -20) == -20
    assert get_signed_quantity("出库", -20) == -20


def test_signed_quantity_converts_positive_outbound_quantity() -> None:
    """历史出库/领取数量为正数时，应按操作类型转为负数。"""

    from inventory import get_signed_quantity

    assert get_signed_quantity("out", 20) == -20
    assert get_signed_quantity("领取", 20) == -20
    assert get_signed_quantity("in", -10) == 10
