from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from db.base import Base, utc_now


class Checkpoint(Base):
    __tablename__ = "checkpoints"
    __table_args__ = (
        CheckConstraint(
            "output IS NOT NULL OR storage_reference IS NOT NULL",
            name="checkpoint_output",
        ),
        ForeignKeyConstraint(
            ["attempt_id", "job_id"],
            ["private.job_attempts.id", "private.job_attempts.job_id"],
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

    attempt_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    stage = Column(Text, nullable=False)

    output = Column(JSONB(none_as_null=True), nullable=True)

    storage_reference = Column(Text, nullable=True)

    input_fingerprint = Column(Text, nullable=False)

    workflow_version = Column(Text, nullable=False)

    model_version = Column(Text, nullable=False)

    schema_version = Column(Text, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
