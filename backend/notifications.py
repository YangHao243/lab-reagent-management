"""通知提醒基础工具模块。

本模块只提供可被其他业务模块调用的通知函数；导入本模块不会自动发送消息。
"""

from typing import Any

import requests

from config import settings


def send_wechat_work_text(content: str) -> bool:
    """发送企业微信群机器人文本消息。

    未配置 WECHAT_WORK_WEBHOOK 时直接返回 False，避免本地开发报错。
    """

    webhook = settings.WECHAT_WORK_WEBHOOK.strip()
    if not webhook:
        return False

    payload = {
        "msgtype": "text",
        "text": {
            "content": content,
        },
    }

    try:
        response = requests.post(webhook, json=payload, timeout=10)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
    except (requests.RequestException, ValueError):
        return False

    # 企业微信机器人成功时通常返回 {"errcode": 0, "errmsg": "ok"}。
    return result.get("errcode") == 0


def format_low_stock_message(reagent: Any) -> str:
    """格式化低库存提醒文本。"""

    return (
        "【低库存提醒】\n"
        f"试剂名称：{reagent.name_cn}\n"
        f"当前库存：{reagent.current_quantity} {reagent.unit}\n"
        f"报警阈值：{reagent.warning_threshold} {reagent.unit}\n"
        f"存放位置：{reagent.location or '未填写'}"
    )


def format_expiring_message(reagent: Any) -> str:
    """格式化即将过期提醒文本。"""

    return (
        "【试剂即将过期提醒】\n"
        f"试剂名称：{reagent.name_cn}\n"
        f"有效期：{reagent.expiry_date or '未填写'}\n"
        f"当前库存：{reagent.current_quantity} {reagent.unit}\n"
        f"存放位置：{reagent.location or '未填写'}"
    )
