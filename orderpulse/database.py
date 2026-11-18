import os
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def make_engine(database_url: str | None = None) -> Engine:
    url = make_url(
        database_url or os.environ.get("ORDERPULSE_DATABASE_URL", "sqlite:///./orderpulse.db")
    )
    connect_args = {"check_same_thread": False, "timeout": 10}
    if url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:"):
        # Startup and synchronous routes run on different threads.
        return create_engine(url, connect_args=connect_args, poolclass=StaticPool)
    return create_engine(url, connect_args=connect_args)


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session
