from sqlalchemy import select

from db.models import Checkpoint

from .jobs import get_job, guard_attempt


def save_checkpoint(
    session,
    owner_id,
    job_id,
    attempt_id,
    *,
    stage,
    input_fingerprint,
    workflow_version,
    model_version,
    schema_version,
    output=None,
    storage_reference=None,
):
    guard_attempt(session, owner_id, job_id, attempt_id)

    if output is None and not storage_reference:
        raise ValueError("Checkpoint requires output or private storage reference")

    checkpoint = Checkpoint(
        job_id=job_id,
        attempt_id=attempt_id,
        stage=stage,
        output=output,
        storage_reference=storage_reference,
        input_fingerprint=input_fingerprint,
        workflow_version=workflow_version,
        model_version=model_version,
        schema_version=schema_version,
    )

    session.add(checkpoint)

    session.flush()

    return checkpoint


def compatible_checkpoint(
    session,
    owner_id,
    job_id,
    *,
    stage,
    input_fingerprint,
    workflow_version,
    model_version,
    schema_version,
    source_job_id=None,
):
    job = get_job(session, owner_id, job_id)

    source = get_job(session, owner_id, source_job_id or job_id)

    if source.id != job.id and (
        job.retry_of_job_id != source.id
        or source.uploaded_file_id != job.uploaded_file_id
    ):
        raise ValueError("Checkpoint source is not the retried file")

    return session.scalar(
        select(Checkpoint)
        .where(
            Checkpoint.job_id == source.id,
            Checkpoint.stage == stage,
            Checkpoint.input_fingerprint == input_fingerprint,
            Checkpoint.workflow_version == workflow_version,
            Checkpoint.model_version == model_version,
            Checkpoint.schema_version == schema_version,
        )
        .order_by(Checkpoint.created_at.desc())
        .limit(1)
    )
