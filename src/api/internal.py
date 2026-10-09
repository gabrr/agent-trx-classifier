from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from services.jobs import JobService

from .dependencies import require_maintenance_caller, require_task_caller
from .jobs import get_job_service

router = APIRouter(prefix="/internal", tags=["internal"])


class ProcessJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID


@router.post("/process", dependencies=[Depends(require_task_caller)], status_code=204)
async def process_job(
    payload: ProcessJobRequest, service: Annotated[JobService, Depends(get_job_service)]
):
    try:
        outcome = await service.process_job(payload.job_id)

    except LookupError:
        # The trusted delivery no longer references a job; retries cannot fix it.
        return Response(status_code=204)

    if outcome.status == "busy":
        raise HTTPException(409, "Job attempt already active")

    if outcome.status == "retry":
        raise HTTPException(503, "Job processing temporarily unavailable")

    return Response(status_code=204)


@router.post("/maintenance", dependencies=[Depends(require_maintenance_caller)])
def maintenance(service: Annotated[JobService, Depends(get_job_service)]):
    return service.run_maintenance()
