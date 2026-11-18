import pytest
from fastapi.testclient import TestClient

from tests.http_helpers import HEADER, VALID_ORDER, upload


@pytest.fixture
def populated(client: TestClient) -> TestClient:
    records = (
        "ORD-1,2025-01-01,US,10.01,paid\n"
        "ORD-2,2025-01-02T00:30:00+01:00,CA,20.02,paid\n"
        "ORD-3,2025-01-02,US,0.01,paid\n"
        "ORD-4,2025-01-02,US,99.00,pending\n"
        "ORD-5,2025-01-03,DE,99.00,refunded\n"
        "ORD-6,2025-01-03,DE,99.00,cancelled\n"
    )
    response = upload(client, HEADER + records)
    assert response.status_code == 200
    assert response.json() == {"imported": 6, "skipped": 0}
    return client


def test_summary_uses_exact_cents_and_rounds_average(populated: TestClient) -> None:
    response = populated.get("/analytics/summary")
    assert response.status_code == 200
    assert response.json() == {
        "total_revenue_usd": "30.04",
        "paid_orders": 3,
        "average_order_value_usd": "10.01",
    }


def test_average_rounds_half_cent_up(client: TestClient) -> None:
    assert upload(client, HEADER + VALID_ORDER + "ORD-2,2025-01-01,US,10.02,paid\n").is_success
    assert client.get("/analytics/summary").json()["average_order_value_usd"] == "10.02"


def test_country_totals_are_sorted_and_exclude_nonpaid_orders(populated: TestClient) -> None:
    assert populated.get("/analytics/by-country").json() == [
        {"country": "CA", "total_revenue_usd": "20.02", "paid_orders": 1},
        {"country": "US", "total_revenue_usd": "10.02", "paid_orders": 2},
    ]


def test_country_filter_is_case_insensitive(populated: TestClient) -> None:
    params = {"country": "us"}
    assert populated.get("/analytics/summary", params=params).json() == {
        "total_revenue_usd": "10.02",
        "paid_orders": 2,
        "average_order_value_usd": "5.01",
    }
    assert populated.get("/analytics/by-country", params=params).json() == [
        {"country": "US", "total_revenue_usd": "10.02", "paid_orders": 2},
    ]


def test_daily_groups_by_utc_and_includes_date_boundaries(populated: TestClient) -> None:
    assert populated.get("/analytics/daily").json() == [
        {"date": "2025-01-01", "total_revenue_usd": "30.03"},
        {"date": "2025-01-02", "total_revenue_usd": "0.01"},
    ]
    params = {"date_from": "2025-01-02", "date_to": "2025-01-02", "country": "US"}
    assert populated.get("/analytics/daily", params=params).json() == [
        {"date": "2025-01-02", "total_revenue_usd": "0.01"},
    ]
    assert populated.get("/analytics/summary", params=params).json()["paid_orders"] == 1


def test_daily_preserves_the_last_microsecond_of_the_day(client: TestClient) -> None:
    record = "ORD-1,2025-01-01T23:59:59.999999Z,US,1.00,paid\n"
    assert upload(client, HEADER + record).is_success
    assert client.get("/analytics/daily?date_to=2025-01-01").json() == [
        {"date": "2025-01-01", "total_revenue_usd": "1.00"}
    ]


def test_empty_results_and_invalid_filters(client: TestClient) -> None:
    assert client.get("/analytics/summary").json() == {
        "total_revenue_usd": "0.00",
        "paid_orders": 0,
        "average_order_value_usd": "0.00",
    }
    assert client.get("/analytics/by-country").json() == []
    assert client.get("/analytics/daily").json() == []
    assert client.get("/analytics/daily?date_from=2025-02-01&date_to=2025-01-01").status_code == 422
    assert client.get("/analytics/summary?date_from=1735689600").status_code == 422
    assert client.get("/analytics/by-country?country=USA").status_code == 422


@pytest.mark.parametrize("params", [{"country": "DE"}, {"date_from": "2025-01-04"}])
def test_no_matching_paid_orders(populated: TestClient, params: dict[str, str]) -> None:
    summary = populated.get("/analytics/summary", params=params)
    assert summary.status_code == 200
    assert summary.json() == {
        "total_revenue_usd": "0.00",
        "paid_orders": 0,
        "average_order_value_usd": "0.00",
    }
    for route in ("by-country", "daily"):
        response = populated.get(f"/analytics/{route}", params=params)
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.parametrize(
    ("params", "countries"),
    [
        ({"date_to": "2025-01-01"}, [("CA", "20.02"), ("US", "10.01")]),
        ({"date_from": "2025-01-02"}, [("US", "0.01")]),
    ],
)
def test_country_aggregation_accepts_one_sided_date_filters(
    populated: TestClient, params: dict[str, str], countries: list[tuple[str, str]]
) -> None:
    response = populated.get("/analytics/by-country", params=params)
    assert response.status_code == 200
    assert response.json() == [
        {"country": country, "total_revenue_usd": total, "paid_orders": 1}
        for country, total in countries
    ]


def test_country_revenue_ties_sort_alphabetically(client: TestClient) -> None:
    orders = VALID_ORDER + "ORD-2,2025-01-01,CA,10.01,paid\n"
    assert upload(client, HEADER + orders).status_code == 200
    response = client.get("/analytics/by-country")
    assert response.status_code == 200
    assert [row["country"] for row in response.json()] == ["CA", "US"]
