import asyncio
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from config import AgentConfig, JobConfig
from services.authentication import AuthenticationService
from services.authentication.interface import VerifiedUser
from services.jobs import JobService, job_service_factory
from tools.object_storage import StorageError, object_storage_factory
from tools.task_queue import task_queue_factory

from .dependencies import current_user, get_auth_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def get_job_service(request: Request) -> JobService:
    service = getattr(request.app.state, "job_service", None)

    if service is not None:
        return service

    sessions = getattr(request.app.state, "db_sessions", None)

    if sessions is None:
        raise HTTPException(503, "Job database unavailable")

    try:
        settings = JobConfig.from_environment()

        storage = object_storage_factory(bucket_name=settings.bucket_name)

        queue = task_queue_factory(
            project_id=settings.project_id,
            location=settings.location,
            queue_name=settings.queue_name,
            backend_url=settings.backend_url,
            service_account_email=settings.task_caller_email,
        )

        service = job_service_factory(sessions, storage, queue, settings)

    except ValueError:
        raise HTTPException(503, "Job configuration unavailable") from None

    request.app.state.job_service = service
    return service


@router.post("", status_code=202)
async def submit_job(
    file: Annotated[UploadFile, File()],
    principal: Annotated[VerifiedUser, Depends(current_user)],
    service: Annotated[JobService, Depends(get_job_service)],
    submission_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=128)
    ],
):
    try:
        content = await file.read(AgentConfig().max_file_bytes + 1)

    finally:
        await file.close()

    try:
        result = await asyncio.to_thread(
            service.submit_job,
            principal.id,
            content,
            file.filename or "statement.pdf",
            submission_key,
        )

    except ValueError as error:
        raise HTTPException(422, str(error)) from None

    except StorageError:
        raise HTTPException(503, "Document storage unavailable") from None

    return JSONResponse(result, status_code=202, headers={"Cache-Control": "no-store"})


@router.get("/{job_id}")
def get_job(
    job_id: UUID,
    principal: Annotated[VerifiedUser, Depends(current_user)],
    service: Annotated[JobService, Depends(get_job_service)],
):
    try:
        result = service.get_job(principal.id, job_id)

    except LookupError:
        raise HTTPException(404, "Job not found") from None

    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.get("/{job_id}/result")
def get_result(
    job_id: UUID,
    principal: Annotated[VerifiedUser, Depends(current_user)],
    service: Annotated[JobService, Depends(get_job_service)],
):
    try:
        result = service.get_result(principal.id, job_id)

    except LookupError:
        raise HTTPException(404, "Job not found") from None

    if result is None:
        raise HTTPException(409, "Result is not available")

    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.post("/{job_id}/retry", status_code=202)
def retry_job(
    job_id: UUID,
    principal: Annotated[VerifiedUser, Depends(current_user)],
    service: Annotated[JobService, Depends(get_job_service)],
    submission_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=128)
    ],
):
    try:
        result = service.retry_job(principal.id, job_id, submission_key)

    except LookupError:
        raise HTTPException(404, "Job not found") from None

    except ValueError as error:
        raise HTTPException(409, str(error)) from None

    return JSONResponse(result, status_code=202, headers={"Cache-Control": "no-store"})


@router.get("/{job_id}/events")
async def stream_job_events(
    request: Request,
    job_id: UUID,
    principal: Annotated[VerifiedUser, Depends(current_user)],
    service: Annotated[JobService, Depends(get_job_service)],
    auth: Annotated[AuthenticationService, Depends(get_auth_service)],
    after_sequence: Annotated[int, Header(alias="Last-Event-ID", ge=0)] = 0,
):
    try:
        job = await asyncio.to_thread(service.get_job, principal.id, job_id)

    except LookupError:
        raise HTTPException(404, "Job not found") from None

    listener = getattr(request.app.state, "job_listener", None)

    if listener is None:
        raise HTTPException(503, "Event listener unavailable")

    async def stream():
        loop = asyncio.get_running_loop()

        queue = asyncio.Queue(maxsize=128)

        overflowed = asyncio.Event()

        def put(event):
            if queue.full():
                overflowed.set()

            else:
                queue.put_nowait(event)

        def deliver(event):
            loop.call_soon_threadsafe(put, event)

        token = await asyncio.to_thread(
            listener.subscribe,
            principal.id,
            job_id,
            deliver,
            after_sequence=after_sequence,
        )

        cursor = after_sequence
        next_auth_check = loop.time()

        try:
            while not overflowed.is_set():
                if await request.is_disconnected():
                    return

                if loop.time() >= next_auth_check:
                    if not await asyncio.to_thread(auth.is_token_active, principal):
                        yield "event: session_expired\ndata: {}\n\n"
                        return

                    next_auth_check = loop.time() + 10

                if queue.empty() and job["status"] in {"succeeded", "failed"}:
                    return

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)

                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue

                if event.sequence <= cursor:
                    continue

                cursor = event.sequence
                data = json.dumps(event.data, ensure_ascii=False, allow_nan=False)

                yield f"id: {cursor}\nevent: {event.event_type}\ndata: {data}\n\n"
                if event.event_type in {"result", "error"}:
                    return

        finally:
            listener.unsubscribe(token)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
    )
