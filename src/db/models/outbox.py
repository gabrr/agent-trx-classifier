from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from db.base import Base, utc_now


class Outbox(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        UniqueConstraint("task_name"),
        CheckConstraint("retry_count >= 0", name="outbox_retry_count"),
        Index("ix_outbox_dispatch_retry", "dispatch_status", "next_attempt_at"),
        {"schema": "private"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid4)

    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.jobs.id"),
        nullable=False,
        index=True,
    )

    action = Column(Text, nullable=False)

    task_name = Column(Text, nullable=False)

    payload = Column(JSONB(none_as_null=True), nullable=False)

    dispatch_status = Column(Text, nullable=False)

    retry_count = Column(Integer, nullable=False)

    next_attempt_at = Column(DateTime(timezone=True), nullable=True)

    dispatched_at = Column(DateTime(timezone=True), nullable=True)

    last_error = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
