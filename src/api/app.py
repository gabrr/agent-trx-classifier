import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from runtime.factory import classifier_factory
from runtime.interface import DocumentClassifier
from runtime.runner import document_input
from runtime.settings import Settings

from .streaming import stream_events


def create_app(classifier: DocumentClassifier | None = None) -> FastAPI:
    # todo: implement a queue system for classification requests.
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
            document = await file.read(Settings().max_upload_bytes + 1)
        finally:
            await file.close()

        filename = file.filename or "statement.pdf"

        try:
            document_input(document, filename)

        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        if app.state.run_lock.locked():
            raise HTTPException(
                status_code=409, detail="A classification is already running."
            )

        await app.state.run_lock.acquire()

        async def response_stream():
            try:
                events = app.state.classifier.events(document, filename=filename)

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
