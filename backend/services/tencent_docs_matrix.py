"""Tencent Docs reagent matrix template helpers.

The Tencent document used by this project mirrors the historical
``2026年化学试剂库存管理.xlsx`` workbook:

* A column stores day numbers.
* Row 2 stores reagent names; every reagent occupies 3 columns.
* Row 3 stores sub fields: 操作 / 数量 / 操作人.
* Rows 4-34 store daily records.
* Row 35 stores inventory summary.

This module intentionally keeps matrix parsing/export separate from the
generic CSV/row-table sync path.
"""

from __future__ import annotations

import calendar
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from models import InventoryRecord, Reagent
from services.excel_inventory_sync import clean_quantity, clean_text, is_blank, parse_excel_row_date
from services.sync_core import NormalizedInventoryRecord, SyncErrorItem, get_signed_quantity


MATRIX_TEMPLATE_TYPE = "reagent_matrix"
MATRIX_SOURCE = "tencent_docs_matrix"
MATRIX_READ_RANGE = "A1:BF37"
MATRIX_RANGE = MATRIX_READ_RANGE  # kept for backward compatibility
MATRIX_WRITE_RANGE = "B4:BF34"
MATRIX_ROW_COUNT = 37
MATRIX_REAGENT_COUNT = 19
MATRIX_COLUMN_COUNT = 1 + MATRIX_REAGENT_COUNT * 3
WRITE_ROW_COUNT = 31    # rows 4-34, data rows only
WRITE_COL_COUNT = MATRIX_REAGENT_COUNT * 3  # 57 columns, no A column
HEADER_REAGENT_ROW = 1
HEADER_SUBFIELD_ROW = 2
DATA_START_ROW = 3
DATA_END_ROW = 33
INVENTORY_ROW = 34

OPERATION_MAPPING = {
    "入库": "in",
    "in": "in",
    "stock_in": "in",
    "领取": "out",
    "出库": "out",
    "领用": "out",
    "out": "out",
    "stock_out": "out",
}

OPERATION_LABELS = {
    "in": "入库",
    "out": "领取",
}


@dataclass
class MatrixParseResult:
    """Parsed Tencent Docs matrix result."""

    detected_template_type: str = MATRIX_TEMPLATE_TYPE
    year: int = 0
    month: int = 0
    raw_rows_count: int = 0
    reagent_names: list[str] = field(default_factory=list)
    records: list[NormalizedInventoryRecord] = field(default_factory=list)
    invalid_records: list[SyncErrorItem] = field(default_factory=list)
    raw_values_preview: list[list[Any]] = field(default_factory=list)
    parsed_values_shape: tuple[int, int] | None = None
    matrix_row_1_preview: list[Any] = field(default_factory=list)
    matrix_row_2_preview: list[Any] = field(default_factory=list)
    matrix_row_3_preview: list[Any] = field(default_factory=list)
    detected_reagent_columns: list[dict[str, Any]] = field(default_factory=list)

    @property
    def reagent_count(self) -> int:
        return len(self.reagent_names)

    @property
    def parsed_records_count(self) -> int:
        return len(self.records)

    def invalid_records_preview(self, limit: int = 20) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.invalid_records[:limit]]

    def parsed_records_preview(self, limit: int = 10) -> list[dict[str, Any]]:
        preview: list[dict[str, Any]] = []
        for record in self.records[:limit]:
            preview.append(
                {
                    "date": record.operation_time.isoformat(sep=" ") if record.operation_time else None,
                    "reagent_name": record.reagent_name,
                    "operation_type": record.operation_type,
                    "operation_text": record.operation_text,
                    "quantity": record.quantity,
                    "operator": record.operator,
                    "source_sheet": record.source_sheet,
                    "source_row": record.source_row,
                    "source_col": record.source_col,
                }
            )
        return preview

    def to_debug_response(self) -> dict[str, Any]:
        return {
            "detected_template_type": self.detected_template_type,
            "year": self.year,
            "month": self.month,
            "raw_rows_count": self.raw_rows_count,
            "reagent_count": self.reagent_count,
            "reagent_names": self.reagent_names,
            "parsed_records_preview": self.parsed_records_preview(),
            "parsed_records_count": self.parsed_records_count,
            "invalid_records": [item.to_dict() for item in self.invalid_records],
            "invalid_records_preview": self.invalid_records_preview(),
            "raw_values_preview": self.raw_values_preview,
            "parsed_values_shape": list(self.parsed_values_shape) if self.parsed_values_shape else None,
            "matrix_row_1_preview": self.matrix_row_1_preview,
            "matrix_row_2_preview": self.matrix_row_2_preview,
            "matrix_row_3_preview": self.matrix_row_3_preview,
            "detected_reagent_columns": self.detected_reagent_columns,
        }


def pad_matrix_values(values: list[list[Any]]) -> list[list[Any]]:
    """Pad matrix values so fixed row/column access is safe."""

    padded: list[list[Any]] = []
    for row in values[:MATRIX_ROW_COUNT]:
        row_values = list(row)[:MATRIX_COLUMN_COUNT]
        row_values.extend([""] * (MATRIX_COLUMN_COUNT - len(row_values)))
        padded.append(row_values)
    while len(padded) < MATRIX_ROW_COUNT:
        padded.append([""] * MATRIX_COLUMN_COUNT)
    return padded


def extract_matrix_reagent_groups(values: list[list[Any]]) -> list[tuple[str, int]]:
    """Read reagent names from row 2, starting at column B, every 3 columns."""

    rows = pad_matrix_values(values)
    groups: list[tuple[str, int]] = []
    header_row = rows[HEADER_REAGENT_ROW]
    for column_index in range(1, MATRIX_COLUMN_COUNT, 3):
        reagent_name = clean_text(header_row[column_index])
        if not reagent_name:
            continue
        groups.append((reagent_name, column_index))
        if len(groups) >= MATRIX_REAGENT_COUNT:
            break
    return groups


def matrix_row_has_operation(row: list[Any], groups: list[tuple[str, int]]) -> bool:
    for _, column_index in groups:
        if (
            clean_text(row[column_index])
            or not is_blank(row[column_index + 1])
            or clean_text(row[column_index + 2])
        ):
            return True
    return False


def build_matrix_source_hash(
    *,
    year: int,
    month: int,
    day: int,
    reagent_name: str,
    operation_type: str,
    quantity: float,
    operator: str,
) -> str:
    """Build a stable matrix source hash based on business facts, not cell position."""

    raw = "|".join(
        [
            MATRIX_SOURCE,
            str(year),
            str(month),
            str(day),
            reagent_name.strip(),
            operation_type,
            f"{get_signed_quantity(operation_type, quantity):g}",
            (operator or "-").strip() or "-",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_reagent_matrix(
    values: list[list[Any]],
    *,
    year: int,
    month: int,
    sheet_name: str | None = None,
) -> MatrixParseResult:
    """Parse Tencent Docs reagent matrix values into normalized inventory records."""

    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")

    matrix = pad_matrix_values(values)
    source_sheet = sheet_name or f"{year}.{month}"
    groups = extract_matrix_reagent_groups(matrix)
    result = MatrixParseResult(
        year=year,
        month=month,
        raw_rows_count=len(values),
        reagent_names=[name for name, _ in groups],
        raw_values_preview=[row[: min(12, len(row))] for row in matrix[:8]],
        parsed_values_shape=(len(matrix), len(matrix[0]) if matrix else 0),
        matrix_row_1_preview=matrix[0][: min(16, len(matrix[0]))] if len(matrix) > 0 else [],
        matrix_row_2_preview=matrix[1][: min(16, len(matrix[1]))] if len(matrix) > 1 else [],
        matrix_row_3_preview=matrix[2][: min(16, len(matrix[2]))] if len(matrix) > 2 else [],
        detected_reagent_columns=[
            {"reagent_name": name, "column_index": idx} for name, idx in groups
        ],
    )

    for row_index in range(DATA_START_ROW, DATA_END_ROW + 1):
        excel_row_number = row_index + 1
        row = matrix[row_index]
        try:
            operation_time = parse_excel_row_date(f"{year}.{month}", excel_row_number, row[0])
        except ValueError as exc:
            if matrix_row_has_operation(row, groups):
                result.invalid_records.append(
                    SyncErrorItem(source_sheet, excel_row_number, None, str(exc))
                )
            continue

        day = operation_time.day
        for reagent_name, column_index in groups:
            operation_text = clean_text(row[column_index])
            quantity_cell = row[column_index + 1]
            operator_text = clean_text(row[column_index + 2]) or "-"

            if not operation_text and is_blank(quantity_cell) and operator_text == "-":
                continue

            if not operation_text or is_blank(quantity_cell):
                result.invalid_records.append(
                    SyncErrorItem(
                        source_sheet,
                        excel_row_number,
                        reagent_name,
                        "操作和数量必须同时填写",
                    )
                )
                continue

            operation_type = OPERATION_MAPPING.get(operation_text) or OPERATION_MAPPING.get(
                operation_text.lower()
            )
            if operation_type is None:
                result.invalid_records.append(
                    SyncErrorItem(
                        source_sheet,
                        excel_row_number,
                        reagent_name,
                        "操作必须为入库、领取或出库",
                    )
                )
                continue

            try:
                quantity = clean_quantity(quantity_cell)
            except ValueError as exc:
                result.invalid_records.append(
                    SyncErrorItem(source_sheet, excel_row_number, reagent_name, str(exc))
                )
                continue

            result.records.append(
                NormalizedInventoryRecord(
                    year=year,
                    month=month,
                    event_date=operation_time.date(),
                    reagent_name=reagent_name,
                    operation_text=operation_text,
                    operation_type=operation_type,
                    quantity=quantity,
                    operator=operator_text,
                    remark=f"Tencent Docs matrix import: {source_sheet}!R{excel_row_number}C{column_index + 1}",
                    source=MATRIX_SOURCE,
                    source_sheet=source_sheet,
                    source_row=excel_row_number,
                    source_col=column_index + 1,
                    source_hash=build_matrix_source_hash(
                        year=year,
                        month=month,
                        day=day,
                        reagent_name=reagent_name,
                        operation_type=operation_type,
                        quantity=quantity,
                        operator=operator_text,
                    ),
                    operation_time=operation_time,
                )
            )

    return result


def get_template_reagents(db: Session) -> list[Reagent]:
    """Return the 19 reagents used by the matrix template."""

    return list(
        db.execute(
            select(Reagent)
            .order_by(Reagent.display_order.asc(), Reagent.id.asc())
            .limit(MATRIX_REAGENT_COUNT)
        ).scalars()
    )


def get_record_event_datetime(record: InventoryRecord) -> datetime:
    if record.created_at:
        return record.created_at.replace(microsecond=0)
    if record.event_date:
        return datetime.combine(record.event_date, datetime.min.time()).replace(hour=10)
    return datetime.min.replace(year=1900)


def sanitize_matrix_value(value: Any) -> Any:
    """Convert cell value to a Tencent Docs API-safe type.

    - None → ""
    - datetime / date → isoformat string
    - Decimal → float
    - dict / list / object → string representation
    - Everything else passed through (str, int, float, bool)
    """

    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    try:
        from decimal import Decimal
        if isinstance(value, Decimal):
            return float(value)
    except ImportError:
        pass
    if isinstance(value, (dict, list, tuple, set)):
        return str(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def sanitize_matrix(values: list[list[Any]]) -> list[list[Any]]:
    """Sanitize all cells in a 2-D matrix."""

    return [[sanitize_matrix_value(cell) for cell in row] for row in values]


def extract_write_matrix(full_matrix: list[list[Any]]) -> list[list[Any]]:
    """Extract B4:BF34 (31 rows × 57 cols) from the full A1:BF37 matrix.

    Drops:
      - Column A (index 0) — day numbers
      - Rows 0-2 (0-indexed) — header rows 1-3
      - Rows 34-36 (0-indexed) — inventory + notes rows 35-37
    """

    write_rows = full_matrix[DATA_START_ROW:DATA_END_ROW + 1]
    return [row[1:WRITE_COL_COUNT + 1] for row in write_rows]


def build_empty_write_matrix() -> list[list[str]]:
    """Build the B4:BF34 write-only matrix: 31 days x 19 reagents x 3 fields."""

    return [["" for _ in range(WRITE_COL_COUNT)] for _ in range(WRITE_ROW_COUNT)]


def pad_write_matrix(values: list[list[Any]] | None) -> list[list[Any]]:
    """Pad Tencent Docs B4:BF34 values to an exact 31 x 57 matrix."""

    padded: list[list[Any]] = []
    source_values = values or []
    for row in source_values[:WRITE_ROW_COUNT]:
        row_values = list(row)[:WRITE_COL_COUNT]
        row_values.extend([""] * (WRITE_COL_COUNT - len(row_values)))
        padded.append(row_values)
    while len(padded) < WRITE_ROW_COUNT:
        padded.append([""] * WRITE_COL_COUNT)
    return padded


def format_quantity_text(value: Any) -> str:
    """Format quantity for the matrix cell, always using an absolute display value."""

    try:
        number = abs(float(value or 0))
    except (TypeError, ValueError):
        return str(value or "").strip()
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def split_matrix_cell(value: Any) -> list[str]:
    """Split a comma-joined matrix cell and trim empty parts."""

    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,，、\r\n]+", text) if part.strip()]


MatrixTuple = tuple[str, str, str]


def parse_matrix_triplets(operation_cell: Any, quantity_cell: Any, operator_cell: Any) -> list[MatrixTuple]:
    """Parse operation/quantity/operator cells into aligned triplets.

    Existing Tencent Docs content is kept as much as possible. If the operator
    slot is blank while operation or quantity exists, use "-".
    """

    operations = split_matrix_cell(operation_cell)
    quantities = split_matrix_cell(quantity_cell)
    operators = split_matrix_cell(operator_cell)
    max_length = max(len(operations), len(quantities), len(operators), 0)
    triplets: list[MatrixTuple] = []
    for index in range(max_length):
        operation = operations[index] if index < len(operations) else ""
        quantity = quantities[index] if index < len(quantities) else ""
        operator = operators[index] if index < len(operators) else ""
        if not operation and not quantity and not operator:
            continue
        triplets.append((operation, quantity, operator or "-"))
    return triplets


def serialize_matrix_triplets(triplets: list[MatrixTuple]) -> tuple[str, str, str]:
    """Serialize triplets back to the three Tencent Docs cells."""

    if not triplets:
        return "", "", ""
    operations = ",".join(item[0] for item in triplets)
    quantities = ",".join(item[1] for item in triplets)
    operators = ",".join((item[2] or "-") for item in triplets)
    return operations, quantities, operators


def normalize_matrix_triplet(operation: str, quantity: str, operator: str) -> MatrixTuple:
    """Normalize one matrix triplet for stable comparison and writing."""

    return (operation.strip(), quantity.strip(), (operator or "-").strip() or "-")


def merge_matrix_triplets(existing: list[MatrixTuple], new: list[MatrixTuple]) -> tuple[list[MatrixTuple], list[MatrixTuple], int]:
    """Append non-duplicate new triplets while preserving existing content order."""

    merged: list[MatrixTuple] = [normalize_matrix_triplet(*item) for item in existing]
    seen: set[MatrixTuple] = set(merged)
    appended: list[MatrixTuple] = []
    skipped_count = 0
    for operation, quantity, operator in new:
        key = (operation.strip(), quantity.strip(), (operator or "-").strip() or "-")
        if key in seen:
            skipped_count += 1
            continue
        seen.add(key)
        merged.append(key)
        appended.append(key)
    return merged, appended, skipped_count


def merge_write_matrix_with_existing(
    *,
    existing_values: list[list[Any]],
    new_values: list[list[Any]],
    reagent_names: list[str] | None = None,
) -> dict[str, Any]:
    """Merge current Tencent Docs B4:BF34 content with DB-generated triplets."""

    existing_matrix = pad_write_matrix(existing_values)
    new_matrix = pad_write_matrix(new_values)
    merged_matrix = [list(row) for row in existing_matrix]
    reagent_name_list = reagent_names or []
    existing_cells_count = sum(
        1 for row in existing_matrix for cell in row if str(cell or "").strip()
    )
    merged_existing_cells_count = 0
    new_tuples_count = 0
    appended_tuples_count = 0
    skipped_duplicate_tuples_count = 0
    changed_cells_count = 0
    preview_changes: list[dict[str, Any]] = []

    for row_index in range(WRITE_ROW_COUNT):
        for column_index in range(0, WRITE_COL_COUNT, 3):
            before_cells = (
                str(existing_matrix[row_index][column_index] or ""),
                str(existing_matrix[row_index][column_index + 1] or ""),
                str(existing_matrix[row_index][column_index + 2] or ""),
            )
            existing_triplets = parse_matrix_triplets(
                existing_matrix[row_index][column_index],
                existing_matrix[row_index][column_index + 1],
                existing_matrix[row_index][column_index + 2],
            )
            new_triplets = parse_matrix_triplets(
                new_matrix[row_index][column_index],
                new_matrix[row_index][column_index + 1],
                new_matrix[row_index][column_index + 2],
            )
            if existing_triplets:
                merged_existing_cells_count += 1
            new_tuples_count += len(new_triplets)
            merged_triplets, appended_triplets, skipped_count = merge_matrix_triplets(
                existing_triplets,
                new_triplets,
            )
            appended_tuples_count += len(appended_triplets)
            skipped_duplicate_tuples_count += skipped_count
            operation_cell, quantity_cell, operator_cell = serialize_matrix_triplets(merged_triplets)
            merged_matrix[row_index][column_index] = operation_cell
            merged_matrix[row_index][column_index + 1] = quantity_cell
            merged_matrix[row_index][column_index + 2] = operator_cell
            after_cells = (operation_cell, quantity_cell, operator_cell)
            changed_cells_count += sum(
                1 for before, after in zip(before_cells, after_cells) if before != after
            )
            if appended_triplets and len(preview_changes) < 10:
                reagent_index = column_index // 3
                preview_changes.append(
                    {
                        "day": row_index + 1,
                        "reagent_name": (
                            reagent_name_list[reagent_index]
                            if reagent_index < len(reagent_name_list)
                            else f"#{reagent_index + 1}"
                        ),
                        "before": {
                            "operation": before_cells[0],
                            "quantity": before_cells[1],
                            "operator": before_cells[2],
                        },
                        "append": [
                            {
                                "operation": item[0],
                                "quantity": item[1],
                                "operator": item[2],
                            }
                            for item in appended_triplets
                        ],
                        "after": {
                            "operation": after_cells[0],
                            "quantity": after_cells[1],
                            "operator": after_cells[2],
                        },
                    }
                )

    sanitized_values, validation_errors = validate_write_matrix(merged_matrix)
    return {
        "write_values": sanitized_values,
        "validation_errors": validation_errors,
        "existing_cells_count": existing_cells_count,
        "merged_existing_cells_count": merged_existing_cells_count,
        "new_tuples_count": new_tuples_count,
        "appended_tuples_count": appended_tuples_count,
        "deduped_tuples_count": skipped_duplicate_tuples_count,
        "skipped_duplicate_tuples_count": skipped_duplicate_tuples_count,
        "changed_cells_count": changed_cells_count,
        "preview_changes": preview_changes,
        "actual_shape": f"{len(sanitized_values)}x{len(sanitized_values[0]) if sanitized_values else 0}",
    }


def excel_column_name(column_number: int) -> str:
    """Convert a 1-based spreadsheet column number to Excel letters."""

    if column_number < 1:
        raise ValueError("column_number must be >= 1")
    result = ""
    value = column_number
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def read_patch_cells(values: list[list[Any]] | None) -> tuple[str, str, str]:
    """Read a Tencent Docs 1x3 range response into operation/quantity/operator cells."""

    if not values:
        return "", "", ""
    first_row = list(values[0]) if values and values[0] is not None else []
    first_row.extend([""] * (3 - len(first_row)))
    return (
        str(first_row[0] or ""),
        str(first_row[1] or ""),
        str(first_row[2] or ""),
    )


def merge_patch_with_existing(
    patch: dict[str, Any],
    existing_values: list[list[Any]] | None,
) -> dict[str, Any]:
    """Merge one day+reagent patch with its current Tencent Docs 1x3 cells."""

    before_cells = read_patch_cells(existing_values)
    existing_triplets = parse_matrix_triplets(*before_cells)
    new_triplets = [
        normalize_matrix_triplet(item["operation"], item["quantity"], item["operator"])
        for item in patch.get("append", [])
    ]
    merged_triplets, appended_triplets, skipped_count = merge_matrix_triplets(
        existing_triplets,
        new_triplets,
    )
    after_cells = serialize_matrix_triplets(merged_triplets)
    changed_cells_count = sum(
        1 for before, after in zip(before_cells, after_cells) if before != after
    )
    merged_patch = dict(patch)
    merged_patch.update(
        {
            "before": {
                "operation": before_cells[0],
                "quantity": before_cells[1],
                "operator": before_cells[2],
            },
            "after": {
                "operation": after_cells[0],
                "quantity": after_cells[1],
                "operator": after_cells[2],
            },
            "appended_tuples_count": len(appended_triplets),
            "skipped_duplicate_count": skipped_count,
            "changed_cells_count": changed_cells_count,
            "will_write": bool(appended_triplets and changed_cells_count),
            "values": [[after_cells[0], after_cells[1], after_cells[2]]],
        }
    )
    return merged_patch


def validate_patch_values(values: list[list[Any]]) -> tuple[list[list[Any]], list[str]]:
    """Validate a single 1x3 patch payload before calling Tencent Docs."""

    if len(values) != 1 or len(values[0]) != 3:
        return values, [f"patch values must be 1x3, got {len(values)}x{len(values[0]) if values else 0}"]
    errors: list[str] = []
    sanitized_row: list[Any] = []
    for column_index, cell in enumerate(values[0]):
        if cell is None:
            sanitized_row.append("")
        elif isinstance(cell, datetime):
            sanitized_row.append(cell.isoformat(sep=" "))
        elif isinstance(cell, date):
            sanitized_row.append(cell.isoformat())
        else:
            try:
                from decimal import Decimal

                if isinstance(cell, Decimal):
                    sanitized_row.append(str(cell))
                    continue
            except ImportError:
                pass
            if isinstance(cell, (str, int, float, bool)):
                sanitized_row.append(cell)
            else:
                errors.append(
                    f"patch values[0][{column_index}] has unsupported type {type(cell).__name__}"
                )
                sanitized_row.append("")
    return [sanitized_row], errors


def build_reagent_matrix_patches_from_db(
    db: Session,
    *,
    year: int,
    month: int,
    sheet_id: str | None = None,
) -> dict[str, Any]:
    """Build incremental day+reagent 1x3 patches from local inventory records."""

    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")

    reagents = get_template_reagents(db)
    reagent_column_by_id = {
        reagent.id: index * 3 for index, reagent in enumerate(reagents)
    }
    reagent_names = [reagent.name_cn or reagent.standard_name or f"#{reagent.id}" for reagent in reagents]

    records = list(
        db.execute(
            select(InventoryRecord)
            .options(joinedload(InventoryRecord.reagent))
            .where(InventoryRecord.operation_type.in_(["in", "out"]))
            .order_by(InventoryRecord.created_at.asc(), InventoryRecord.id.asc())
        ).scalars()
    )

    month_records: list[InventoryRecord] = []
    for record in records:
        event_time = get_record_event_datetime(record)
        if event_time.year == year and event_time.month == month:
            month_records.append(record)

    grouped: dict[tuple[int, int], dict[str, Any]] = {}
    unmatched_records: list[dict[str, Any]] = []
    for record in month_records:
        event_time = get_record_event_datetime(record)
        if record.reagent_id not in reagent_column_by_id:
            unmatched_records.append(
                {
                    "record_id": record.id,
                    "reagent_id": record.reagent_id,
                    "reagent_name": record.reagent.name_cn if record.reagent else None,
                    "reason": "试剂不在 19 种矩阵模板列中",
                }
            )
            continue
        if not 1 <= event_time.day <= WRITE_ROW_COUNT:
            unmatched_records.append(
                {
                    "record_id": record.id,
                    "reagent_id": record.reagent_id,
                    "reagent_name": record.reagent.name_cn if record.reagent else None,
                    "reason": f"日期 {event_time.date()} 不在 1-31 日写入区域内",
                }
            )
            continue

        reagent_index = reagent_column_by_id[record.reagent_id] // 3
        row_number = event_time.day + 3
        op_column_number = 2 + reagent_index * 3
        range_name = (
            f"{excel_column_name(op_column_number)}{row_number}:"
            f"{excel_column_name(op_column_number + 2)}{row_number}"
        )
        operation_type = "in" if record.operation_type == "in" else "out"
        triplet = {
            "operation": OPERATION_LABELS[operation_type],
            "quantity": format_quantity_text(record.quantity_change),
            "operator": (record.operator_name or "-").strip() or "-",
        }
        key = (event_time.day, record.reagent_id)
        patch = grouped.setdefault(
            key,
            {
                "day": event_time.day,
                "reagent_id": record.reagent_id,
                "reagent_name": (
                    record.reagent.name_cn
                    if record.reagent and record.reagent.name_cn
                    else reagent_names[reagent_index]
                ),
                "range": range_name,
                "full_range": f"{sheet_id}!{range_name}" if sheet_id else range_name,
                "append": [],
                "record_ids": [],
            },
        )
        patch["append"].append(triplet)
        patch["record_ids"].append(record.id)

    patches = list(grouped.values())
    new_tuples_count = sum(len(patch["append"]) for patch in patches)
    return {
        "detected_template_type": MATRIX_TEMPLATE_TYPE,
        "year": year,
        "month": month,
        "data_area_range": MATRIX_WRITE_RANGE,
        "write_range": "incremental_patches",
        "expected_shape": "patches",
        "values_shape": "patches",
        "db_records_count": len(month_records),
        "patch_count": len(patches),
        "new_tuples_count": new_tuples_count,
        "unmatched_records": unmatched_records,
        "reagent_count": len(reagents),
        "reagent_names": reagent_names,
        "patches": patches,
    }


def validate_write_matrix(values: list[list[Any]]) -> tuple[list[list[Any]], list[str]]:
    """Validate and sanitize the formal Tencent Docs write matrix.

    The formal PUT payload must be exactly 31 x 57 and contain only scalar
    values after safe conversion. Complex objects are rejected instead of being
    silently stringified.
    """

    errors: list[str] = []
    if len(values) != WRITE_ROW_COUNT:
        errors.append(f"write_values row count must be {WRITE_ROW_COUNT}, got {len(values)}")
    sanitized: list[list[Any]] = []
    for row_index, row in enumerate(values):
        if len(row) != WRITE_COL_COUNT:
            errors.append(
                f"write_values row {row_index + 1} column count must be {WRITE_COL_COUNT}, got {len(row)}"
            )
        sanitized_row: list[Any] = []
        for column_index, cell in enumerate(row):
            if cell is None:
                sanitized_row.append("")
            elif isinstance(cell, datetime):
                sanitized_row.append(cell.isoformat(sep=" "))
            elif isinstance(cell, date):
                sanitized_row.append(cell.isoformat())
            else:
                try:
                    from decimal import Decimal

                    if isinstance(cell, Decimal):
                        sanitized_row.append(str(cell))
                        continue
                except ImportError:
                    pass
                if isinstance(cell, (str, int, float, bool)):
                    sanitized_row.append(cell)
                else:
                    errors.append(
                        f"write_values[{row_index}][{column_index}] has unsupported type {type(cell).__name__}"
                    )
                    sanitized_row.append("")
        sanitized.append(sanitized_row)
    return sanitized, errors


def build_reagent_matrix_values_from_db(
    db: Session,
    *,
    year: int,
    month: int,
) -> dict[str, Any]:
    """Build the write-only B4:BF34 matrix from local inventory records."""

    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")

    reagents = get_template_reagents(db)
    reagent_column_by_id = {
        reagent.id: index * 3 for index, reagent in enumerate(reagents)
    }
    reagent_names = [reagent.name_cn or reagent.standard_name or f"#{reagent.id}" for reagent in reagents]
    write_values = build_empty_write_matrix()

    records = list(
        db.execute(
            select(InventoryRecord)
            .options(joinedload(InventoryRecord.reagent))
            .where(InventoryRecord.operation_type.in_(["in", "out"]))
            .order_by(InventoryRecord.created_at.asc(), InventoryRecord.id.asc())
        ).scalars()
    )

    month_records: list[InventoryRecord] = []
    for record in records:
        event_time = get_record_event_datetime(record)
        if event_time.year == year and event_time.month == month:
            month_records.append(record)

    triplets_by_cell: dict[tuple[int, int], list[MatrixTuple]] = {}
    unmatched_records: list[dict[str, Any]] = []
    for record in month_records:
        if record.reagent_id not in reagent_column_by_id:
            unmatched_records.append(
                {
                    "record_id": record.id,
                    "reagent_id": record.reagent_id,
                    "reagent_name": record.reagent.name_cn if record.reagent else None,
                    "reason": "试剂不在 19 种矩阵模板列中",
                }
            )
            continue

        event_time = get_record_event_datetime(record)
        row_index = event_time.day - 1
        column = reagent_column_by_id[record.reagent_id]
        if not 0 <= row_index < WRITE_ROW_COUNT:
            unmatched_records.append(
                {
                    "record_id": record.id,
                    "reagent_id": record.reagent_id,
                    "reagent_name": record.reagent.name_cn if record.reagent else None,
                    "reason": f"日期 {event_time.date()} 不在 1-31 日写入区域内",
                }
            )
            continue

        operation_type = "in" if record.operation_type == "in" else "out"
        operation_text = OPERATION_LABELS[operation_type]
        quantity_text = format_quantity_text(record.quantity_change)
        operator = (record.operator_name or "-").strip() or "-"
        triplets_by_cell.setdefault((row_index, column), []).append(
            (operation_text, quantity_text, operator)
        )

    new_tuples_count = 0
    for (row_index, column), triplets in triplets_by_cell.items():
        operation_cell, quantity_cell, operator_cell = serialize_matrix_triplets(triplets)
        write_values[row_index][column] = operation_cell
        write_values[row_index][column + 1] = quantity_cell
        write_values[row_index][column + 2] = operator_cell
        new_tuples_count += len(triplets)

    sanitized_write_values, validation_errors = validate_write_matrix(write_values)
    written_cells = sum(
        1
        for row in sanitized_write_values
        for cell in row
        if str(cell or "").strip()
    )

    return {
        "detected_template_type": MATRIX_TEMPLATE_TYPE,
        "year": year,
        "month": month,
        "read_range": MATRIX_READ_RANGE,
        "write_range": MATRIX_WRITE_RANGE,
        "write_values": sanitized_write_values,
        "values_row_count": len(sanitized_write_values),
        "values_col_count": len(sanitized_write_values[0]) if sanitized_write_values else 0,
        "first_row_length": len(sanitized_write_values[0]) if sanitized_write_values else 0,
        "last_row_length": len(sanitized_write_values[-1]) if sanitized_write_values else 0,
        "expected_shape": f"{WRITE_ROW_COUNT}x{WRITE_COL_COUNT}",
        "actual_shape": f"{len(sanitized_write_values)}x{len(sanitized_write_values[0]) if sanitized_write_values else 0}",
        "values_preview": [row[: min(16, len(row))] for row in sanitized_write_values[:5]],
        "db_records_count": len(month_records),
        "matrix_written_cells": written_cells,
        "new_tuples_count": new_tuples_count,
        "deduped_tuples_count": 0,
        "merged_existing_cells_count": 0,
        "validation_errors": validation_errors,
        "unmatched_records": unmatched_records,
        "reagent_count": len(reagents),
        "reagent_names": reagent_names,
        "will_call_tencent_api": bool(len(month_records) and written_cells and not validation_errors),
    }
