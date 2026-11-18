from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orderpulse.main import create_app


@pytest.fixture(autouse=True)
def test_database_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite:///{tmp_path / 'orders.db'}"
    monkeypatch.setenv("ORDERPULSE_DATABASE_URL", url)
    return url


@pytest.fixture
def client(test_database_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(test_database_url)) as test_client:
        yield test_client
