import csv
from io import StringIO
from itertools import batched
from typing import BinaryIO

from pydantic import ValidationError
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from orderpulse.models import Order
from orderpulse.schemas import ImportResult, OrderRow

COLUMNS = ("order_id", "created_at", "country", "amount_usd", "status")
MAX_CSV_BYTES = 5 * 1024 * 1024


class CsvValidationError(ValueError):
    def __init__(self, message: str, *, line: int | None = None, field: str | None = None):
        super().__init__(message)
        self.line = line
        self.field = field


class CsvTooLargeError(ValueError):
    pass


def parse_orders(file: BinaryIO) -> list[OrderRow]:
    content = file.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise CsvTooLargeError("CSV files may be at most 5 MiB")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvValidationError("CSV must be UTF-8 encoded") from exc

    reader = csv.reader(StringIO(decoded, newline=""), strict=True)
    orders: list[OrderRow] = []

    try:
        header = next(reader, [])
        if len(header) != len(COLUMNS) or set(header) != set(COLUMNS):
            raise CsvValidationError(f"expected columns {', '.join(COLUMNS)}", line=1)

        for record in reader:
            if len(record) != len(header):
                raise CsvValidationError(f"expected {len(header)} fields", line=reader.line_num)
            try:
                orders.append(OrderRow.model_validate(dict(zip(header, record, strict=True))))
            except ValidationError as exc:
                error = exc.errors()[0]
                raise CsvValidationError(
                    error["msg"], line=reader.line_num, field=str(error["loc"][0])
                ) from exc
    except csv.Error as exc:
        raise CsvValidationError(f"invalid CSV syntax ({exc})", line=reader.line_num) from exc

    return orders


def import_orders(file: BinaryIO, session: Session) -> ImportResult:
    orders = parse_orders(file)
    statement = insert(Order.__table__).on_conflict_do_nothing(index_elements=["order_id"])
    imported = 0

    with session.begin():
        for batch in batched(orders, 500):
            records = [
                {
                    "order_id": row.order_id,
                    "created_at": row.created_at,
                    "country": row.country,
                    "amount_cents": int(row.amount_usd * 100),
                    "status": row.status,
                }
                for row in batch
            ]
            imported += session.execute(statement, records).rowcount

    return ImportResult(imported=imported, skipped=len(orders) - imported)
