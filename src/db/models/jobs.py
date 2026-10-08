from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Double,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from db.base import Base, utc_now


class Batch(Base):
    __tablename__ = "batches"
    __table_args__ = (
        UniqueConstraint("id", "owner_id"),
        {"schema": "private"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid4)

    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.users.id"),
        nullable=False,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("owner_id", "submission_key"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')", name="job_status"
        ),
        ForeignKeyConstraint(
            ["active_attempt_id", "id"],
            ["private.job_attempts.id", "private.job_attempts.job_id"],
            name="fk_active_attempt_job",
            use_alter=True,
        ),
        Index("ix_jobs_owner_status_created", "owner_id", "status", "created_at"),
        UniqueConstraint("id", "owner_id"),
        ForeignKeyConstraint(
            ["batch_id", "owner_id"], ["private.batches.id", "private.batches.owner_id"]
        ),
        ForeignKeyConstraint(
            ["uploaded_file_id", "owner_id"],
            ["private.uploaded_files.id", "private.uploaded_files.owner_id"],
        ),
        ForeignKeyConstraint(
            ["retry_of_job_id", "owner_id"],
            ["private.jobs.id", "private.jobs.owner_id"],
        ),
        {"schema": "private"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid4)

    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.users.id"),
        nullable=False,
        index=True,
    )

    batch_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    uploaded_file_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    retry_of_job_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    submission_key = Column(Text, nullable=False)

    status = Column(Text, nullable=False)

    current_stage = Column(Text, nullable=True)

    active_attempt_id = Column(UUID(as_uuid=True), nullable=True)

    claim_expires_at = Column(DateTime(timezone=True), nullable=True)

    deadline_at = Column(DateTime(timezone=True), nullable=True)

    result = Column(JSONB(none_as_null=True), nullable=True)

    result_schema_version = Column(Text, nullable=True)

    success_message = Column(Text, nullable=True)

    error_code = Column(Text, nullable=True)

    error_reason = Column(Text, nullable=True)

    diagnostic_reference = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=utc_now,
    )

    started_at = Column(DateTime(timezone=True), nullable=True)

    finished_at = Column(DateTime(timezone=True), nullable=True)


class JobAttempt(Base):
    __tablename__ = "job_attempts"
    __table_args__ = (
        UniqueConstraint("id", "job_id"),
        UniqueConstraint("job_id", "attempt_number"),
        CheckConstraint("attempt_number > 0", name="attempt_number"),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')", name="attempt_status"
        ),
        {"schema": "private"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid4)

    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.jobs.id"),
        nullable=False,
        index=True,
    )

    attempt_number = Column(Integer, nullable=False)

    status = Column(Text, nullable=False)

    claim_expires_at = Column(DateTime(timezone=True), nullable=True)

    started_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    finished_at = Column(DateTime(timezone=True), nullable=True)

    error_code = Column(Text, nullable=True)

    error_details = Column(JSONB(none_as_null=True), nullable=True)


class RunMetrics(Base):
    __tablename__ = "run_metrics"
    __table_args__ = ({"schema": "private"},)

    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.jobs.id"),
        primary_key=True,
        nullable=False,
        index=True,
    )

    elapsed_seconds = Column(Double, nullable=False)

    classification_seconds = Column(Double, nullable=False)

    classification_model_calls = Column(Integer, nullable=False)

    transaction_count = Column(Integer, nullable=False)
