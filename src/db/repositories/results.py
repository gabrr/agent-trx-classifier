from sqlalchemy import select

from db.base import utc_now
from db.models import Account, JobAttempt, RunMetrics, Statement, Transaction
from workflows.trx_classifier.models import NormalizedStatement

from .events import append_locked
from .jobs import StaleAttemptError, get_job, guard_attempt


def complete_job(
    session,
    owner_id,
    job_id,
    attempt_id,
    result,
    *,
    account_id=None,
    schema_version="1",
    success_message="Completed",
):
    # Revalidate even already-instantiated Pydantic objects (which may be mutated).
    payload = (
        result.model_dump(mode="json")
        if isinstance(result, NormalizedStatement)
        else result
    )

    normalized = NormalizedStatement.model_validate(payload)

    job = get_job(session, owner_id, job_id, lock=True)

    if job.status == "succeeded":
        if job.active_attempt_id != attempt_id:
            raise StaleAttemptError("Another attempt completed this job")

        return session.scalar(select(Statement).where(Statement.job_id == job_id))

    guard_attempt(session, owner_id, job_id, attempt_id)

    if (
        account_id
        and session.scalar(
            select(Account.id).where(
                Account.id == account_id, Account.owner_id == owner_id
            )
        )
        is None
    ):
        raise LookupError("Account not found")

    statement = Statement(
        job_id=job_id,
        owner_id=owner_id,
        account_id=account_id,
        **normalized.statement.model_dump(),
    )

    session.add(statement)

    session.flush()

    for position, transaction in enumerate(normalized.transactions):
        values = transaction.model_dump()

        trx_id = values.pop("id")

        values["classification_probabilities"] = transaction.model_dump(mode="json")[
            "classification_probabilities"
        ]
        session.add(
            Transaction(
                statement_id=statement.id,
                owner_id=owner_id,
                trx_id=trx_id,
                position=position,
                **values,
            )
        )

    session.add(RunMetrics(job_id=job_id, **normalized.metrics.model_dump()))

    job.result = normalized.model_dump(mode="json")

    job.result_schema_version = schema_version
    job.success_message = success_message
    job.status = "succeeded"
    job.finished_at = utc_now()

    job.claim_expires_at = None
    attempt = session.get(JobAttempt, attempt_id)

    attempt.status = "succeeded"
    attempt.finished_at = job.finished_at
    attempt.claim_expires_at = None
    append_locked(session, job, "result", job.result, attempt_id)

    return statement


def get_result(session, owner_id, job_id):
    job = get_job(session, owner_id, job_id)

    return NormalizedStatement.model_validate(job.result) if job.result else None
