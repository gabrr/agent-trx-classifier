import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from config import ApiConfig, database_config


def create_app(
    *,
    auth_service=None,
    job_service=None,
    internal_auth_provider=None,
    db_sessions=None,
    job_listener=None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from db.engine import create_database_engine
        from db.listener import JobUpdateListener
        from db.session import session_factory

        settings = database_config() if db_sessions is None else None

        app.state.auth_service = auth_service
        app.state.job_service = job_service
        app.state.internal_auth_provider = internal_auth_provider
        app.state.db_sessions = db_sessions
        app.state.job_listener = job_listener

        app.state.db_engine = None
        listener = None
        try:
            if settings and settings.runtime_url:
                app.state.db_engine = create_database_engine(settings.runtime_url)

                app.state.db_sessions = session_factory(app.state.db_engine)

                listener = JobUpdateListener(
                    settings.runtime_url, app.state.db_sessions
                )

                listener.start()

                app.state.job_listener = listener

            yield
        finally:
            for name in ("auth_service", "internal_auth_provider"):
                component = getattr(app.state, name, None)

                close = getattr(component, "close", None)

                if close:
                    await asyncio.to_thread(close)

            if listener:
                await asyncio.to_thread(listener.close)

            if app.state.db_engine:
                await asyncio.to_thread(app.state.db_engine.dispose)

    api_settings = ApiConfig()

    app = FastAPI(
        title="TRX Classifier",
        lifespan=lifespan,
        docs_url="/docs" if api_settings.enable_docs else None,
        redoc_url="/redoc" if api_settings.enable_docs else None,
        openapi_url="/openapi.json" if api_settings.enable_docs else None,
    )

    from .authentication import router as authentication_router
    from .internal import router as internal_router
    from .jobs import router as jobs_router

    app.include_router(authentication_router)

    app.include_router(jobs_router)

    app.include_router(internal_router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict:
        from sqlalchemy import text

        engine = app.state.db_engine
        if engine is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        try:
            with engine.begin() as connection:
                connection.execute(text("SET LOCAL statement_timeout = '2000ms'"))

                connection.execute(text("SELECT 1"))

        except Exception:
            raise HTTPException(
                status_code=503, detail="Database unavailable"
            ) from None

        return {"status": "ready"}

    return app
