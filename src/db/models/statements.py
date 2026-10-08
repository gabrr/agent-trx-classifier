from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from db.base import Base, utc_now


class Statement(Base):
    __tablename__ = "statements"
    __table_args__ = (
        UniqueConstraint("job_id"),
        CheckConstraint(
            "kind IN ('credit_card', 'checking_account', 'unknown')",
            name="statement_kind",
        ),
        UniqueConstraint("id", "owner_id"),
        ForeignKeyConstraint(
            ["job_id", "owner_id"], ["private.jobs.id", "private.jobs.owner_id"]
        ),
        ForeignKeyConstraint(
            ["account_id", "owner_id"],
            ["private.accounts.id", "private.accounts.owner_id"],
        ),
        {"schema": "private"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid4)

    job_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.users.id"),
        nullable=False,
        index=True,
    )

    account_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    kind = Column(Text, nullable=False)

    institution_name = Column(Text, nullable=True)

    currency = Column(Text, nullable=True)

    statement_due_date = Column(Date, nullable=True)

    statement_close_date = Column(Date, nullable=True)

    statement_total = Column(Text, nullable=True)

    page_count = Column(Integer, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
