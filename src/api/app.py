import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from langgraph.graph.state import CompiledStateGraph

from config import AgentConfig, database_config
from tools.event_stream import workflow_events
from tools.statement_file import StatementFileInput

from .streaming import stream_events


def create_app(workflow: CompiledStateGraph | None = None) -> FastAPI:
    config = AgentConfig()

    # TODO: implement a queue system for classification requests.
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from db.engine import create_database_engine
        from db.listener import JobUpdateListener
        from db.session import session_factory

        settings = database_config()

        app.state.workflow = workflow
        app.state.run_lock = asyncio.Lock()

        app.state.db_engine = None
        listener = None
        try:
            if settings.runtime_url:
                app.state.db_engine = create_database_engine(settings.runtime_url)

                app.state.db_sessions = session_factory(app.state.db_engine)

                listener = JobUpdateListener(
                    settings.listener_url, app.state.db_sessions
                )

                listener.start()

            yield
        finally:
            if listener:
                await asyncio.to_thread(listener.close)

            if app.state.db_engine:
                await asyncio.to_thread(app.state.db_engine.dispose)

    app = FastAPI(title="TRX Classifier", lifespan=lifespan)

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

    @app.post("/classify")
    async def classify(file: Annotated[UploadFile, File()]):
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
