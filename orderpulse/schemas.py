import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Status = Literal["paid", "pending", "cancelled", "refunded"]


def normalize_country(value: object) -> object:
    if isinstance(value, str):
        country = value.strip()
        if re.fullmatch(r"[A-Za-z]{2}", country):
            return country.upper()
        raise ValueError("use a two-letter country code")
    return value


CountryCode = Annotated[
    str, StringConstraints(pattern=r"^[A-Z]{2}$"), BeforeValidator(normalize_country)
]
Money = Annotated[str, StringConstraints(pattern=r"^[0-9]+\.[0-9]{2}$")]


class OrderRow(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    order_id: str = Field(min_length=1, max_length=128)
    created_at: datetime
    country: CountryCode
    amount_usd: Decimal = Field(ge=0, max_digits=9, decimal_places=2)
    status: Status

    @field_validator("created_at", mode="before")
    @classmethod
    def parse_iso_timestamp(cls, value: str) -> datetime:
        value = value.strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}(?:$|[T ])", value):
            raise ValueError("use an ISO date or timestamp")
        try:
            timestamp = datetime.fromisoformat(value)
            if timestamp.tzinfo is not None:
                timestamp = timestamp.astimezone(UTC)
        except (ValueError, OverflowError) as exc:
            raise ValueError("use a valid ISO date or timestamp") from exc
        return timestamp.replace(tzinfo=None)

    @field_validator("amount_usd", mode="before")
    @classmethod
    def validate_amount_format(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", value):
            raise ValueError("use a nonnegative amount with at most two decimal places")
        return value


class ImportResult(BaseModel):
    imported: int
    skipped: int


class AnalyticsFilters(BaseModel):
    country: CountryCode | None = None
    date_from: date | None = None
    date_to: date | None = None

    @field_validator("date_from", "date_to", mode="before")
    @classmethod
    def validate_date_format(cls, value: str | date | None) -> str | date | None:
        if isinstance(value, str) and not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("use a date in YYYY-MM-DD format")
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise ValueError("date_from must be on or before date_to")
        return self


class Summary(BaseModel):
    total_revenue_usd: Money
    paid_orders: int
    average_order_value_usd: Money


class CountryRevenue(BaseModel):
    country: str
    total_revenue_usd: Money
    paid_orders: int


class DailyRevenue(BaseModel):
    date: date
    total_revenue_usd: Money
