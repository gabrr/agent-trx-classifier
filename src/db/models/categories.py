from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from db.base import Base, utc_now


class ReportBucket(Base):
    __tablename__ = "report_buckets"
    __table_args__ = ({"schema": "private"},)

    key = Column(Text, primary_key=True, nullable=False)

    label = Column(Text, nullable=False)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint(
            "(is_system AND owner_id IS NULL) OR (NOT is_system AND owner_id IS NOT NULL)",
            name="category_owner",
        ),
        Index(
            "uq_system_category_key",
            "key",
            unique=True,
            postgresql_where=text("is_system"),
        ),
        Index(
            "uq_user_category_key",
            "owner_id",
            "key",
            unique=True,
            postgresql_where=text("NOT is_system"),
        ),
        {"schema": "private"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid4)

    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.users.id"),
        nullable=True,
        index=True,
    )

    key = Column(Text, nullable=False)

    name = Column(Text, nullable=False)

    is_system = Column(Boolean, nullable=False)

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
