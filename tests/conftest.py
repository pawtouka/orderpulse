from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orderpulse.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(f"sqlite:///{tmp_path / 'orders.db'}")) as test_client:
        yield test_client
