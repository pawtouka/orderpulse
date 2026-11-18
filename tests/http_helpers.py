from fastapi.testclient import TestClient
from httpx import Response

HEADER = "order_id,created_at,country,amount_usd,status\n"
VALID_ORDER = "ORD-1,2025-01-01,US,10.01,paid\n"


def upload(client: TestClient, content: str | bytes) -> Response:
    return client.post("/orders/import", files={"file": ("orders.csv", content, "text/csv")})
