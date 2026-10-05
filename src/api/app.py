import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from config import AgentConfig
from runtime.factory import classifier_factory
from runtime.interface import DocumentClassifier
from tools.statement_file import StatementFileInput

from .streaming import stream_events


def create_app(classifier: DocumentClassifier | None = None) -> FastAPI:
    config = AgentConfig()

    # TODO: implement a queue system for classification requests.
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.classifier = classifier or await asyncio.to_thread(classifier_factory)

        app.state.run_lock = asyncio.Lock()

        yield

    app = FastAPI(title="TRX Classifier", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

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
                events = app.state.classifier.events(statement_file)

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
