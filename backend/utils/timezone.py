"""系统统一时间工具。

数据库当前使用 naive DateTime 字段，因此这里返回去掉 tzinfo 的北京时间，
避免 SQLAlchemy/PostgreSQL 在 aware/naive datetime 混用时产生兼容问题。
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo


BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def now_beijing() -> datetime:
    """返回北京时间的 naive datetime。"""

    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def today_beijing() -> date:
    """返回北京时间日期。"""

    return now_beijing().date()
