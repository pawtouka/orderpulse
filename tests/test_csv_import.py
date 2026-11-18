from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.http_helpers import HEADER, VALID_ORDER, upload


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


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("", id="empty-file"),
        pytest.param("order_id,country,country,amount_usd,status\n", id="duplicate-column"),
        pytest.param(HEADER.rstrip() + ",note\n", id="extra-column"),
        pytest.param("order_id,created_at,country,status\n", id="missing-column"),
    ],
)
def test_rejects_missing_or_invalid_header(client: TestClient, content: str) -> None:
    response = upload(client, content)
    assert response.status_code == 422
    assert response.json()["detail"]["line"] == 1


def test_header_without_orders_is_a_noop(client: TestClient) -> None:
    assert upload(client, HEADER + VALID_ORDER).status_code == 200
    response = upload(client, HEADER)
    assert response.status_code == 200
    assert response.json() == {"imported": 0, "skipped": 0}
    assert client.get("/analytics/summary").json()["paid_orders"] == 1


def test_import_accepts_bom_reordered_columns_and_maximum_amount(client: TestClient) -> None:
    content = (
        "\ufeffstatus,amount_usd,country,created_at,order_id\r\npaid,9999999.99,us,2025-01-01,A\r\n"
    )
    response = upload(client, content.encode("utf-8"))
    assert response.status_code == 200
    assert response.json() == {"imported": 1, "skipped": 0}
    assert client.get("/analytics/by-country").json() == [
        {"country": "US", "paid_orders": 1, "total_revenue_usd": "9999999.99"}
    ]


def test_rejects_non_utf8_csv(client: TestClient) -> None:
    response = upload(client, HEADER.encode() + b"\xff")
    assert response.status_code == 422
    assert response.json() == {"detail": {"message": "CSV must be UTF-8 encoded"}}


def test_file_size_limit_is_reported_before_csv_validation(client: TestClient) -> None:
    response = upload(client, b" " * (5 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert response.json() == {"detail": "CSV files may be at most 5 MiB"}


def test_import_skips_duplicate_across_insert_batches(client: TestClient) -> None:
    orders = "".join(f"B-{index},2025-01-01,US,0.01,paid\n" for index in range(501))
    response = upload(client, HEADER + orders + "B-0,2025-01-01,US,999.99,paid\n")
    assert response.status_code == 200
    assert response.json() == {"imported": 501, "skipped": 1}
    assert client.get("/analytics/summary").json()["total_revenue_usd"] == "5.01"


def test_invalid_existing_id_rolls_back_entire_upload(client: TestClient) -> None:
    assert upload(client, HEADER + VALID_ORDER).status_code == 200
    orders = "".join(f"B-{index},2025-01-01,US,0.01,paid\n" for index in range(501))
    response = upload(client, HEADER + orders + "ORD-1,2025-01-01,US,-1.00,paid\n")
    assert response.status_code == 422
    assert response.json()["detail"]["line"] == 503
    assert response.json()["detail"]["field"] == "amount_usd"
    assert client.get("/analytics/summary").json() == {
        "paid_orders": 1,
        "total_revenue_usd": "10.01",
        "average_order_value_usd": "10.01",
    }
