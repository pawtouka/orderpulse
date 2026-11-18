import os
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or os.environ.get("ORDERPULSE_DATABASE_URL", "sqlite:///./orderpulse.db")
    return create_engine(url, connect_args={"check_same_thread": False, "timeout": 10})


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session
