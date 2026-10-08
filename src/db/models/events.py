from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from db.base import Base, utc_now


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("job_id", "sequence"),
        CheckConstraint("sequence > 0", name="event_sequence"),
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

    sequence = Column(BigInteger, nullable=False)

    attempt_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    event_type = Column(Text, nullable=False)

    data = Column(JSONB(none_as_null=True), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
