from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from db.base import Base, utc_now


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = ({"schema": "private"},)

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid4)

    changed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("private.users.id"),
        nullable=False,
        index=True,
    )

    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    field = Column(Text, nullable=False)

    old_value = Column(JSONB(none_as_null=True), nullable=True)

    new_value = Column(JSONB(none_as_null=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
