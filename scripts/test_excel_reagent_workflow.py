"""基于 19 种预置试剂的本地联调冒烟测试脚本。

运行前请先启动后端服务，并确保已经执行过预置试剂初始化：
    cd backend
    python seed_excel_reagents.py
    python -m uvicorn main:app --reload --port 8010
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import Any

import requests


DEFAULT_API_BASE_URL = "http://127.0.0.1:8010"
DEFAULT_USERNAME = "superadmin"
DEFAULT_PASSWORD = "Admin@123456"
TIMEOUT_SECONDS = 10
MIN_PRESET_REAGENT_COUNT = 19


class WorkflowTestError(RuntimeError):
    """业务链路冒烟测试失败。"""


def build_url(api_base_url: str, path: str) -> str:
    """拼接后端 API 基础地址和接口路径。"""

    return f"{api_base_url.rstrip('/')}{path}"


def summarize_json(data: Any) -> str:
    """把接口返回压缩成适合命令行查看的摘要。"""

    if isinstance(data, list):
        sample = data[0] if data else None
        if isinstance(sample, dict):
            name = sample.get("name_cn") or sample.get("label") or sample.get("reagent_name")
            return f"list(len={len(data)}, first={name!r})"
        return f"list(len={len(data)})"

    if isinstance(data, dict):
        summary_keys = [
            "status",
            "id",
            "reagent_id",
            "name_cn",
            "reagent_name",
            "current_quantity",
            "before_quantity",
            "after_quantity",
            "low_stock",
            "reagent_total",
            "total_reagents",
            "low_stock_count",
            "year",
            "month",
        ]
        parts = [f"{key}={data[key]!r}" for key in summary_keys if key in data]
        if "days" in data and isinstance(data["days"], list):
            parts.append(f"days={len(data['days'])}")
        if "months" in data and isinstance(data["months"], list):
            parts.append(f"months={len(data['months'])}")
        return ", ".join(parts) or f"dict(keys={list(data.keys())[:8]})"

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
    """执行单个 HTTP 步骤，打印状态码和摘要，失败时抛出异常。"""

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
        f"{method.upper():<4} {path:<34} status={response.status_code:<3} "
        f"summary={summarize_json(response_data)}"
    )

    if response.status_code not in expected_statuses:
        raise WorkflowTestError(
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
        raise WorkflowTestError("登录响应中缺少 access_token")
    session.headers.update({"Authorization": f"Bearer {token}"})


def as_number(value: Any, field_name: str) -> float:
    """把接口返回的库存数量转为数字，方便比较库存变化。"""

    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise WorkflowTestError(f"{field_name} 不是有效数字：{value!r}") from exc


def find_ethanol_reagent(reagents: list[dict[str, Any]]) -> dict[str, Any]:
    """从搜索结果中确认能找到无水乙醇（MOS），并返回第一个匹配项。"""

    for reagent in reagents:
        name = str(reagent.get("name_cn") or reagent.get("label") or "")
        standard_name = str(reagent.get("standard_name") or "")
        if "无水乙醇" in name or "无水乙醇" in standard_name:
            return reagent

    raise WorkflowTestError("keyword=乙醇 的搜索结果中未找到无水乙醇（MOS）")


def run_workflow_test(api_base_url: str, username: str, password: str) -> None:
    """按预置试剂核心业务链路执行本地联调测试。"""

    session = requests.Session()
    today = date.today()

    request_step(session, "GET", api_base_url, "/health")
    authenticate_session(session, api_base_url, username, password)

    options = request_step(session, "GET", api_base_url, "/reagents/options")
    if not isinstance(options, list):
        raise WorkflowTestError("/reagents/options 返回值不是列表")
    if len(options) < MIN_PRESET_REAGENT_COUNT:
        raise WorkflowTestError(
            f"预置试剂数量不足：当前 {len(options)}，期望至少 {MIN_PRESET_REAGENT_COUNT}"
        )

    ethanol_results = request_step(
        session,
        "GET",
        api_base_url,
        "/reagents/options",
        params={"keyword": "乙醇", "limit": 100},
    )
    if not isinstance(ethanol_results, list):
        raise WorkflowTestError("乙醇搜索结果不是列表")

    selected_reagent = find_ethanol_reagent(ethanol_results)
    reagent_id = selected_reagent.get("id") or selected_reagent.get("value")
    if not reagent_id:
        raise WorkflowTestError("选中的试剂缺少 id/value")

    print(f"选择试剂：id={reagent_id}, name={selected_reagent.get('name_cn') or selected_reagent.get('label')!r}")

    stock_before = request_step(
        session,
        "GET",
        api_base_url,
        f"/inventory/stock/{reagent_id}",
    )
    before_quantity = as_number(stock_before.get("current_quantity"), "入库前库存")

    in_result = request_step(
        session,
        "POST",
        api_base_url,
        "/inventory/in",
        json={
            "reagent_id": reagent_id,
            "quantity": 10,
            "reason": "领料入库",
            "remark": "scripts/test_excel_reagent_workflow.py",
        },
    )
    if as_number(in_result.get("after_quantity"), "入库后库存") != before_quantity + 10:
        raise WorkflowTestError("入库后库存变化不符合预期")

    out_result = request_step(
        session,
        "POST",
        api_base_url,
        "/inventory/out",
        json={
            "reagent_id": reagent_id,
            "quantity": 2,
            "reason": "实验领用",
            "remark": "scripts/test_excel_reagent_workflow.py",
        },
    )
    if as_number(out_result.get("after_quantity"), "出库后库存") != before_quantity + 8:
        raise WorkflowTestError("出库后库存变化不符合预期")

    stock_after = request_step(
        session,
        "GET",
        api_base_url,
        f"/inventory/stock/{reagent_id}",
    )
    final_quantity = as_number(stock_after.get("current_quantity"), "最终库存")
    if final_quantity != before_quantity + 8:
        raise WorkflowTestError(
            f"库存余量接口返回不符合预期：期望 {before_quantity + 8}，实际 {final_quantity}"
        )

    low_stock = request_step(session, "GET", api_base_url, "/alerts/low-stock")
    if not isinstance(low_stock, list):
        raise WorkflowTestError("/alerts/low-stock 返回值不是列表")

    request_step(session, "GET", api_base_url, "/reports/summary")
    request_step(
        session,
        "GET",
        api_base_url,
        "/reports/monthly",
        params={"year": today.year, "month": today.month},
    )
    request_step(
        session,
        "GET",
        api_base_url,
        "/reports/inventory-calendar",
        params={"year": today.year, "month": today.month},
    )

    print("\n预置试剂核心业务链路冒烟测试通过。")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""

    parser = argparse.ArgumentParser(description="19种预置试剂核心业务链路冒烟测试")
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
    """脚本入口，任一关键步骤失败时返回非 0 状态码。"""

    args = parse_args()
    try:
        run_workflow_test(args.api_base_url, args.username, args.password)
    except requests.RequestException as exc:
        print(f"\n冒烟测试失败：无法请求后端服务，原因：{exc}", file=sys.stderr)
        return 1
    except WorkflowTestError as exc:
        print(f"\n冒烟测试失败：{exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
