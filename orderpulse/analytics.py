from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from orderpulse.models import Order
from orderpulse.schemas import AnalyticsFilters, CountryRevenue, DailyRevenue, Summary


def paid_filters(filters: AnalyticsFilters) -> list[ColumnElement[bool]]:
    clauses = [Order.status == "paid"]
    if filters.country is not None:
        clauses.append(Order.country == filters.country)
    if filters.date_from is not None:
        clauses.append(Order.created_at >= datetime.combine(filters.date_from, time.min))
    if filters.date_to is not None:
        clauses.append(Order.created_at <= datetime.combine(filters.date_to, time.max))
    return clauses


def format_usd(cents: int) -> str:
    dollars, remainder = divmod(cents, 100)
    return f"{dollars}.{remainder:02d}"


def summarize(session: Session, filters: AnalyticsFilters) -> Summary:
    total, count = session.execute(
        select(func.coalesce(func.sum(Order.amount_cents), 0), func.count(Order.order_id)).where(
            *paid_filters(filters)
        )
    ).one()

    average_cents = 0
    if count:
        average_cents, remainder = divmod(total, count)
        if remainder * 2 >= count:
            average_cents += 1

    return Summary(
        total_revenue_usd=format_usd(total),
        paid_orders=count,
        average_order_value_usd=format_usd(average_cents),
    )


def by_country(session: Session, filters: AnalyticsFilters) -> list[CountryRevenue]:
    revenue = func.sum(Order.amount_cents)
    rows = session.execute(
        select(Order.country, revenue, func.count(Order.order_id))
        .where(*paid_filters(filters))
        .group_by(Order.country)
        .order_by(revenue.desc(), Order.country)
    )
    return [
        CountryRevenue(country=country, total_revenue_usd=format_usd(total), paid_orders=count)
        for country, total, count in rows
    ]


def daily(session: Session, filters: AnalyticsFilters) -> list[DailyRevenue]:
    # SQLite's date function can round fractional seconds across midnight.
    day = func.substr(Order.created_at, 1, 10)
    rows = session.execute(
        select(day, func.sum(Order.amount_cents))
        .where(*paid_filters(filters))
        .group_by(day)
        .order_by(day)
    )
    return [
        DailyRevenue(date=date.fromisoformat(calendar_day), total_revenue_usd=format_usd(total))
        for calendar_day, total in rows
    ]
