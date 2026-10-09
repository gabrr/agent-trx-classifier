import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from langgraph.graph.state import CompiledStateGraph

from config import AgentConfig, database_config
from tools.event_stream import workflow_events
from tools.statement_file import StatementFileInput

from .dependencies import current_user
from .streaming import stream_events


def create_app(
    workflow: CompiledStateGraph | None = None,
    *,
    auth_service=None,
    job_service=None,
    internal_auth_provider=None,
    db_sessions=None,
    job_listener=None,
    allow_direct_classify=False,
) -> FastAPI:
    config = AgentConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from db.engine import create_database_engine
        from db.listener import JobUpdateListener
        from db.session import session_factory

        settings = database_config() if db_sessions is None else None

        app.state.workflow = workflow
        app.state.run_lock = asyncio.Lock()

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

    app = FastAPI(title="TRX Classifier", lifespan=lifespan)

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

    @app.post("/classify", dependencies=[Depends(current_user)])
    async def classify(file: Annotated[UploadFile, File()]):
        if not allow_direct_classify:
            await file.close()

            raise HTTPException(410, "Submit processing through /api/jobs")

        try:
            document = await file.read(config.max_file_bytes + 1)

        finally:
            await file.close()

        filename = file.filename or "statement.pdf"

        try:
            statement_file = StatementFileInput.from_bytes(
                document, filename=filename, config=config
            )

        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        if app.state.run_lock.locked():
            raise HTTPException(
                status_code=409, detail="A classification is already running."
            )

        await app.state.run_lock.acquire()

        async def response_stream():
            try:
                if app.state.workflow is None:
                    from workflows.trx_classifier.workflow import build_workflow

                    app.state.workflow = await asyncio.to_thread(build_workflow)

                parts = app.state.workflow.astream(
                    {"file": statement_file},
                    config={"run_name": "trx_classifier"},
                    stream_mode=["custom", "updates"],
                    version="v2",
                )

                events = workflow_events(parts)

                async for chunk in stream_events(events):
                    yield chunk

            finally:
                app.state.run_lock.release()

        return StreamingResponse(
            response_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    return app
