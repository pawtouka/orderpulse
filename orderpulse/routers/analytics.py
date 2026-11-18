from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from orderpulse import analytics
from orderpulse.database import get_session
from orderpulse.schemas import AnalyticsFilters, CountryRevenue, DailyRevenue, Summary

router = APIRouter(prefix="/analytics", tags=["analytics"])
Filters = Annotated[AnalyticsFilters, Query()]
DatabaseSession = Annotated[Session, Depends(get_session)]


@router.get("/summary")
def summary(filters: Filters, session: DatabaseSession) -> Summary:
    """Return total paid revenue, paid order count, and average order value."""
    return analytics.summarize(session, filters)


@router.get("/by-country")
def by_country(filters: Filters, session: DatabaseSession) -> list[CountryRevenue]:
    """Group paid revenue and order counts by country."""
    return analytics.by_country(session, filters)


@router.get("/daily")
def daily(filters: Filters, session: DatabaseSession) -> list[DailyRevenue]:
    """Group paid revenue by UTC calendar date."""
    return analytics.daily(session, filters)
