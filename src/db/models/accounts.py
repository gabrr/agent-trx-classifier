from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from db.base import Base, utc_now


class Account(Base):
    __tablename__ = "accounts"
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

    name = Column(Text, nullable=False)

    type = Column(Text, nullable=False)

    institution_name = Column(Text, nullable=True)

    currency = Column(Text, nullable=False)

    opening_balance = Column(Numeric, nullable=False)

    is_active = Column(Boolean, nullable=False)

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
