import pytest
from fastapi.testclient import TestClient

from orderpulse.main import create_app
from tests.http_helpers import HEADER, VALID_ORDER, upload


def test_health_and_swagger(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "Swagger UI" in client.get("/docs").text
    schema = client.get("/openapi.json").json()
    assert (
        "multipart/form-data" in schema["paths"]["/orders/import"]["post"]["requestBody"]["content"]
    )


@pytest.mark.parametrize(
    "path", ["/analytics/summary", "/analytics/by-country", "/analytics/daily"]
)
def test_invalid_query_parameters_use_the_validation_error_schema(
    client: TestClient, path: str
) -> None:
    response = client.get(path, params={"date_from": "2025-02-30"})
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert len(errors) == 1
    assert errors[0]["loc"] == ["query", "date_from"]
    assert errors[0]["msg"]


def test_upload_requires_multipart_file(client: TestClient) -> None:
    response = client.post("/orders/import", json={"file": HEADER + VALID_ORDER})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "file"]


def test_success_response_schemas(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    responses = {
        ("/orders/import", "post"): {"$ref": "#/components/schemas/ImportResult"},
        ("/analytics/summary", "get"): {"$ref": "#/components/schemas/Summary"},
        ("/analytics/by-country", "get"): {
            "type": "array",
            "items": {"$ref": "#/components/schemas/CountryRevenue"},
        },
        ("/analytics/daily", "get"): {
            "type": "array",
            "items": {"$ref": "#/components/schemas/DailyRevenue"},
        },
    }
    for (path, method), expected in responses.items():
        body = schema["paths"][path][method]["responses"]["200"]["content"]["application/json"]
        for key, value in expected.items():
            assert body["schema"][key] == value

    models = schema["components"]["schemas"]
    summary = models["Summary"]
    assert set(summary["required"]) == {
        "total_revenue_usd",
        "paid_orders",
        "average_order_value_usd",
    }
    assert summary["properties"]["total_revenue_usd"]["type"] == "string"
    assert summary["properties"]["average_order_value_usd"]["type"] == "string"
    assert summary["properties"]["paid_orders"]["type"] == "integer"
    assert models["DailyRevenue"]["properties"]["date"]["format"] == "date"


def test_in_memory_database_is_shared_between_startup_and_requests() -> None:
    with TestClient(create_app("sqlite:///:memory:")) as client:
        response = upload(client, HEADER + VALID_ORDER)
        assert response.status_code == 200
        assert response.json() == {"imported": 1, "skipped": 0}
        assert client.get("/analytics/summary").json()["total_revenue_usd"] == "10.01"
