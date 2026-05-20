"""本地后端核心流程冒烟测试脚本。

运行前请先启动后端服务，例如：
    cd backend
    python -m uvicorn main:app --reload --port 8010
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

import requests


DEFAULT_API_BASE_URL = "http://127.0.0.1:8010"
DEFAULT_USERNAME = "superadmin"
DEFAULT_PASSWORD = "Admin@123456"
TIMEOUT_SECONDS = 10


class SmokeTestError(RuntimeError):
    """冒烟测试失败异常。"""


def build_url(api_base_url: str, path: str) -> str:
    """拼接 API 基础地址和接口路径。"""

    return f"{api_base_url.rstrip('/')}{path}"


def summarize_json(data: Any) -> str:
    """将接口返回简化成便于终端阅读的摘要。"""

    if isinstance(data, list):
        return f"list(len={len(data)})"

    if isinstance(data, dict):
        summary_keys = [
            "id",
            "status",
            "name_cn",
            "operation_type",
            "before_quantity",
            "after_quantity",
            "total_reagents",
            "low_stock_count",
        ]
        parts = [f"{key}={data[key]!r}" for key in summary_keys if key in data]
        return ", ".join(parts) or f"dict(keys={list(data.keys())[:6]})"

    return repr(data)


def request_step(
    session: requests.Session,
    method: str,
    api_base_url: str,
    path: str,
    *,
    expected_status: int | tuple[int, ...] = 200,
    **kwargs: Any,
) -> Any:
    """执行单个 HTTP 步骤，并在失败时抛出异常让脚本非 0 退出。"""

    url = build_url(api_base_url, path)
    response = session.request(method, url, timeout=TIMEOUT_SECONDS, **kwargs)

    expected_statuses = (
        (expected_status,) if isinstance(expected_status, int) else expected_status
    )

    try:
        response_data = response.json()
    except ValueError:
        response_data = response.text

    print(
        f"{method.upper():<4} {path:<28} status={response.status_code:<3} "
        f"summary={summarize_json(response_data)}"
    )

    if response.status_code not in expected_statuses:
        raise SmokeTestError(
            f"{method.upper()} {path} 失败：期望状态码 {expected_statuses}，"
            f"实际 {response.status_code}，响应 {response_data!r}"
        )

    return response_data


def authenticate_session(
    session: requests.Session,
    api_base_url: str,
    username: str,
    password: str,
) -> None:
    """登录后端并把 JWT 写入当前 session 请求头。"""

    login_response = request_step(
        session,
        "POST",
        api_base_url,
        "/users/login",
        json={"username": username, "password": password},
    )
    token = login_response.get("access_token") if isinstance(login_response, dict) else None
    if not token:
        raise SmokeTestError("登录响应中缺少 access_token")
    session.headers.update({"Authorization": f"Bearer {token}"})


def run_smoke_test(api_base_url: str, username: str, password: str) -> None:
    """按核心业务顺序执行本地冒烟测试。"""

    session = requests.Session()
    unique_suffix = int(time.time())

    request_step(session, "GET", api_base_url, "/health")
    authenticate_session(session, api_base_url, username, password)

    reagent_payload = {
        "name_cn": f"本地冒烟测试试剂-{unique_suffix}",
        "name_en": "Local Smoke Test Reagent",
        "cas_no": f"SMOKE-{unique_suffix}",
        "category": "自动化测试",
        "specification": "100ml",
        "unit": "瓶",
        "current_quantity": 1,
        "warning_threshold": 5,
        "location": "本地冒烟测试柜",
        "supplier": "本地测试供应商",
        "hazard_level": "测试",
        "remark": "local_smoke_test.py 自动创建，可按需清理",
    }

    created_reagent = request_step(
        session,
        "POST",
        api_base_url,
        "/reagents",
        expected_status=201,
        json=reagent_payload,
    )
    reagent_id = created_reagent.get("id")
    if not reagent_id:
        raise SmokeTestError("新增试剂响应中缺少 id")

    reagent_list = request_step(
        session,
        "GET",
        api_base_url,
        "/reagents",
        params={"keyword": reagent_payload["cas_no"]},
    )
    if not any(item.get("id") == reagent_id for item in reagent_list):
        raise SmokeTestError("试剂列表中未找到刚创建的测试试剂")

    request_step(
        session,
        "POST",
        api_base_url,
        "/inventory/in",
        json={
            "reagent_id": reagent_id,
            "quantity": 6,
            "reason": "领料入库",
            "remark": "local_smoke_test.py",
        },
    )

    request_step(
        session,
        "POST",
        api_base_url,
        "/inventory/out",
        json={
            "reagent_id": reagent_id,
            "quantity": 4,
            "reason": "实验领用",
            "remark": "local_smoke_test.py",
        },
    )

    records = request_step(
        session,
        "GET",
        api_base_url,
        "/inventory/records",
        params={"reagent_id": reagent_id},
    )
    if len(records) < 2:
        raise SmokeTestError("库存流水数量不足，入库/出库记录可能未写入")

    low_stock = request_step(session, "GET", api_base_url, "/alerts/low-stock")
    if not isinstance(low_stock, list):
        raise SmokeTestError("低库存接口返回格式不是列表")

    request_step(session, "GET", api_base_url, "/reports/summary")

    print("\n冒烟测试通过：本地后端核心流程可用。")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""

    parser = argparse.ArgumentParser(description="本地后端核心流程冒烟测试")
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help=f"后端 API 基础地址，默认 {DEFAULT_API_BASE_URL}",
    )
    parser.add_argument(
        "--username",
        default=DEFAULT_USERNAME,
        help=f"登录用户名，默认 {DEFAULT_USERNAME}",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help="登录密码，默认使用本地初始化超级管理员密码",
    )
    return parser.parse_args()


def main() -> int:
    """脚本入口，失败时返回非 0 状态码。"""

    args = parse_args()
    try:
        run_smoke_test(args.api_base_url, args.username, args.password)
    except requests.RequestException as exc:
        print(f"\n冒烟测试失败：无法请求后端服务，原因：{exc}", file=sys.stderr)
        return 1
    except SmokeTestError as exc:
        print(f"\n冒烟测试失败：{exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
