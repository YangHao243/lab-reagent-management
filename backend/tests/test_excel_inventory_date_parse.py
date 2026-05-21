"""Excel 库存宽表日期解析测试。

这些测试只验证本地解析函数，不连接线上数据库，也不读取 .env 中的生产连接。
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
os.environ["DATABASE_URL"] = "sqlite:///file:excel_date_parse_pytest?mode=memory&cache=shared&uri=true"
sys.path.insert(0, str(BACKEND_DIR))

from services.excel_inventory_sync import (  # noqa: E402
    parse_row_date,
    parse_sheet_year_month,
    row_has_operation,
)


def test_parse_sheet_year_month_supports_common_separators() -> None:
    """sheet 名支持 2026.5、2026.05、2026-5、2026_5。"""

    assert parse_sheet_year_month("2026.5") == (2026, 5)
    assert parse_sheet_year_month("2026.05") == (2026, 5)
    assert parse_sheet_year_month("2026-5") == (2026, 5)
    assert parse_sheet_year_month("2026_5") == (2026, 5)


def test_parse_numeric_day_from_column_a() -> None:
    """sheet=2026.5 且 A9=6 时，应得到 2026-05-06。"""

    assert parse_row_date("2026.5", 9, 6) == date(2026, 5, 6)
    assert parse_row_date("2026.5", 9, 7.0) == date(2026, 5, 7)


def test_parse_string_day_from_column_a() -> None:
    """sheet=2026.5 且 A10='7'/'07' 时，应得到 2026-05-07。"""

    assert parse_row_date("2026.5", 10, "7") == date(2026, 5, 7)
    assert parse_row_date("2026.5", 10, "07") == date(2026, 5, 7)


def test_parse_first_day_of_april() -> None:
    """sheet=2026.4 且 A4=1 时，应得到 2026-04-01。"""

    assert parse_row_date("2026.4", 4, 1) == date(2026, 4, 1)


def test_parse_datetime_cell_must_match_sheet_month() -> None:
    """A 列是真实日期时使用日期本身，并校验 sheet 年月一致。"""

    assert parse_row_date("2026.5", 9, datetime(2026, 5, 6)) == date(2026, 5, 6)
    with pytest.raises(ValueError, match="不一致"):
        parse_row_date("2026.5", 9, datetime(2026, 4, 6))


def test_invalid_day_is_rejected() -> None:
    """sheet=2026.2 且 A 列 day=30 时应跳过，解析函数抛出明确错误。"""

    with pytest.raises(ValueError, match="日期超出当月范围"):
        parse_row_date("2026.2", 4, 30)


def test_blank_date_without_operation_can_be_skipped_without_warning() -> None:
    """A 列为空且该行没有任何操作记录时，可静默跳过。"""

    dataframe = pd.DataFrame(
        [
            [None, None, None, None],
            [None, "丙酮（MOS）", None, None],
            ["日期", "操作", "数量", "操作人"],
            [None, None, None, None],
        ]
    )

    assert row_has_operation(dataframe, 3, [("丙酮（MOS）", 1)]) is False


def test_blank_date_with_operation_is_rejected() -> None:
    """A 列为空但该行有操作记录时，应被识别并跳过导入。"""

    dataframe = pd.DataFrame(
        [
            [None, None, None, None],
            [None, "丙酮（MOS）", None, None],
            ["日期", "操作", "数量", "操作人"],
            [None, "入库", 40, "程浩航"],
        ]
    )

    assert row_has_operation(dataframe, 3, [("丙酮（MOS）", 1)]) is True
    with pytest.raises(ValueError, match="A列日期不能为空"):
        parse_row_date("2026.5", 9, None)
