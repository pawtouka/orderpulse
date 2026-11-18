from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from orderpulse.database import make_engine
from orderpulse.models import Base
from orderpulse.routers import analytics, orders


def create_app(database_url: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(database_url)
        try:
            Base.metadata.create_all(engine)
            app.state.engine = engine
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="OrderPulse",
        description="Import e-commerce orders and analyze paid sales.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(orders.router)
    app.include_router(analytics.router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
