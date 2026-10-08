import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from config import database_url
from db import models
from db.engine import create_database_engine
from db.repositories.files import create_file
from db.repositories.jobs import claim_job, create_job, get_job
from db.repositories.results import complete_job, get_result
from db.repositories.transactions import activity_history, edit_transaction
from db.repositories.users import synchronize_verified_profile
from workflows.trx_classifier.models import NormalizedStatement


@pytest.fixture(scope="module")
def database():
    runtime = database_url()

    admin = os.environ.get("DATABASE_ADMIN_URL")

    # Reject production before connecting, including an accidental remote trx_test.
    for url in (runtime, admin):
        if not url:
            pytest.fail("Explicit local trx_test runtime/admin URLs required")

        parsed = make_url(url)

        if parsed.database != "trx_test" or parsed.host not in {
            "localhost",
            "127.0.0.1",
            "db",
        }:
            pytest.fail("Smoke tests only allow local trx_test")

    engine = create_database_engine(runtime)

    administrator = create_database_engine(admin)

    factory = sessionmaker(engine, expire_on_commit=False)

    owner_id, other_id = uuid4(), uuid4()

    try:
        with factory.begin() as session:
            synchronize_verified_profile(session, owner_id)

            synchronize_verified_profile(session, other_id)

        yield factory, owner_id, other_id
    finally:
        # Explicit tiny-fixture cleanup uses admin; app has no audit DELETE grant.
        with administrator.begin() as session:
            job_ids = select(models.Job.id).where(
                models.Job.owner_id.in_([owner_id, other_id])
            )

            statement_ids = select(models.Statement.id).where(
                models.Statement.owner_id == owner_id
            )

            session.execute(
                delete(models.ActivityEvent).where(
                    models.ActivityEvent.changed_by == owner_id
                )
            )

            session.execute(
                delete(models.Transaction).where(
                    models.Transaction.statement_id.in_(statement_ids)
                )
            )

            session.execute(
                delete(models.Statement).where(models.Statement.owner_id == owner_id)
            )

            session.execute(
                delete(models.RunMetrics).where(models.RunMetrics.job_id.in_(job_ids))
            )

            session.execute(
                delete(models.Event).where(models.Event.job_id.in_(job_ids))
            )

            session.execute(
                delete(models.Checkpoint).where(models.Checkpoint.job_id.in_(job_ids))
            )

            session.execute(
                delete(models.Outbox).where(models.Outbox.job_id.in_(job_ids))
            )

            session.execute(
                models.Job.__table__.update()
                .where(models.Job.owner_id == owner_id)
                .values(active_attempt_id=None)
            )

            session.execute(
                delete(models.JobAttempt).where(models.JobAttempt.job_id.in_(job_ids))
            )

            session.execute(delete(models.Job).where(models.Job.owner_id == owner_id))

            session.execute(
                delete(models.UploadedFile).where(
                    models.UploadedFile.owner_id == owner_id
                )
            )

            session.execute(
                delete(models.User).where(models.User.id.in_([owner_id, other_id]))
            )

        engine.dispose()

        administrator.dispose()


@pytest.fixture(scope="module")
def saved_job(database):
    factory, owner_id, _ = database
    result = NormalizedStatement.model_validate(
        {
            "statement": {"kind": "unknown", "statement_total": "-1.234,50"},
            "transactions": [
                {
                    "id": "trx-original-1",
                    "amount": "-1.234,50",
                    "report_bucket": "variable",
                    "classification_confidence": 0.8,
                    "classification_probabilities": {
                        "installments": 0.05,
                        "fixed": 0.1,
                        "variable": 0.8,
                        "movements": 0.05,
                    },
                }
            ],
            "metrics": {"transaction_count": 1},
        }
    )

    with factory.begin() as session:
        file = create_file(
            session,
            owner_id,
            filename="synthetic.pdf",
            content_type="application/pdf",
            size_bytes=1,
            storage_bucket="private-test",
            storage_object=str(uuid4()),
        )

        job = create_job(session, owner_id, file.id, str(uuid4()))

        job_id = job.id
        attempt = claim_job(session, owner_id, job_id)

        complete_job(session, owner_id, job_id, attempt.id, result)

        complete_job(session, owner_id, job_id, attempt.id, result)

    return job_id, result


def test_select_one(database):
    factory, _, _ = database
    with factory() as session:
        assert session.scalar(text("SELECT 1")) == 1


def test_save_and_retrieve_result(database, saved_job):
    factory, owner_id, _ = database
    job_id, expected = saved_job
    with factory() as session:
        assert get_job(session, owner_id, job_id).status == "succeeded"
        assert get_result(session, owner_id, job_id) == expected
        transactions = list(
            session.scalars(
                select(models.Transaction).where(
                    models.Transaction.owner_id == owner_id
                )
            )
        )

        assert len(transactions) == 1
        assert transactions[0].amount == "-1.234,50"
        assert transactions[0].date is None


def test_other_owner_cannot_retrieve(database, saved_job):
    factory, _, other_id = database
    with factory() as session, pytest.raises(LookupError):
        get_job(session, other_id, saved_job[0])


def test_edit_and_activity(database, saved_job):
    factory, owner_id, _ = database
    with factory.begin() as session:
        transaction = session.scalar(
            select(models.Transaction).where(models.Transaction.owner_id == owner_id)
        )

        transaction_id = transaction.id
        edit_transaction(
            session, owner_id, transaction_id, {"report_bucket_override": "fixed"}
        )

    with factory() as session:
        history = activity_history(session, owner_id, transaction_id)

        assert len(history) == 1
        assert (history[0].old_value, history[0].new_value) == ("variable", "fixed")
        assert history[0].changed_by == owner_id
        assert get_result(session, owner_id, saved_job[0]) == saved_job[1]
