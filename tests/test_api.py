from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

HEADER = "order_id,created_at,country,amount_usd,status\n"
VALID_ORDER = "ORD-1,2025-01-01,US,10.01,paid\n"


def upload(client: TestClient, content: str | bytes) -> Response:
    return client.post("/orders/import", files={"file": ("orders.csv", content, "text/csv")})


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


def test_import_accepts_sample_data(client: TestClient) -> None:
    sample = Path(__file__).resolve().parents[1] / "data" / "sample_orders.csv"
    response = upload(client, sample.read_bytes())
    assert response.status_code == 200
    assert response.json() == {"imported": 36, "skipped": 0}
    assert client.get("/analytics/summary").json() == {
        "total_revenue_usd": "2135.67",
        "paid_orders": 26,
        "average_order_value_usd": "82.14",
    }


def test_reimport_and_repeated_ids_are_skipped(client: TestClient) -> None:
    different_amount = VALID_ORDER.replace("10.01", "90.00")
    first = upload(client, HEADER + VALID_ORDER + different_amount)
    second = upload(client, HEADER + different_amount)
    assert first.json() == {"imported": 1, "skipped": 1}
    assert second.json() == {"imported": 0, "skipped": 1}
    assert client.get("/analytics/summary").json()["total_revenue_usd"] == "10.01"


@pytest.mark.parametrize(
    ("content", "line"),
    [
        ("id,created_at,country,amount_usd,status\n" + VALID_ORDER, 1),
        (HEADER + VALID_ORDER + 'ORD-2,"2025-01-01,US,10.00,paid\n', 3),
        (HEADER + VALID_ORDER + "ORD-2,2025-01-02,US,10.00\n", 3),
    ],
)
def test_malformed_csv_is_rejected_without_partial_import(
    client: TestClient, content: str, line: int
) -> None:
    response = upload(client, content)
    assert response.status_code == 422
    assert response.json()["detail"]["line"] == line
    assert client.get("/analytics/summary").json()["paid_orders"] == 0


@pytest.mark.parametrize("amount", ["-10", "0.001", "NaN", "Infinity", "99999999", "1e2"])
def test_invalid_money_is_rejected(client: TestClient, amount: str) -> None:
    response = upload(client, HEADER + VALID_ORDER + f"ORD-2,2025-01-01,US,{amount},paid\n")
    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "amount_usd"
    assert client.get("/analytics/summary").json()["paid_orders"] == 0


@pytest.mark.parametrize(
    ("original", "replacement", "field"),
    [
        ("2025-01-01", "2025-02-30", "created_at"),
        (",US,", ",USA,", "country"),
        (",paid", ",shipped", "status"),
        ("ORD-1", " ", "order_id"),
    ],
)
def test_invalid_record_fields(
    client: TestClient, original: str, replacement: str, field: str
) -> None:
    response = upload(client, HEADER + VALID_ORDER.replace(original, replacement))
    assert response.status_code == 422
    assert response.json()["detail"]["field"] == field


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


def test_health_and_swagger(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert "Swagger UI" in client.get("/docs").text
    schema = client.get("/openapi.json").json()
    assert (
        "multipart/form-data" in schema["paths"]["/orders/import"]["post"]["requestBody"]["content"]
    )
