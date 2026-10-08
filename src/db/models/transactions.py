from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Double,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from db.base import Base, utc_now


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("statement_id", "trx_id"),
        UniqueConstraint("statement_id", "position"),
        CheckConstraint("position >= 0", name="transaction_position"),
        CheckConstraint(
            "classification_confidence >= 0 AND classification_confidence <= 1",
            name="confidence_range",
        ),
        CheckConstraint(
            "private.valid_probabilities(classification_probabilities)",
            name="probabilities",
        ),
        UniqueConstraint("id", "owner_id"),
        ForeignKeyConstraint(
            ["statement_id", "owner_id"],
            ["private.statements.id", "private.statements.owner_id"],
        ),
        {"schema": "private"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid4)

    trx_id = Column(Text, nullable=False)

    statement_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.users.id"),
        nullable=False,
        index=True,
    )

    position = Column(Integer, nullable=False)

    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.categories.id"),
        nullable=True,
        index=True,
    )

    date = Column(Date, nullable=True)

    description = Column(Text, nullable=True)

    amount = Column(Text, nullable=True)

    currency = Column(Text, nullable=True)

    cardholder = Column(Text, nullable=True)

    card_last4 = Column(Text, nullable=True)

    payment_method = Column(Text, nullable=True)

    merchant_name = Column(Text, nullable=True)

    installments_current = Column(Integer, nullable=True)

    installments = Column(Integer, nullable=True)

    foreign_amount = Column(Text, nullable=True)

    foreign_currency = Column(Text, nullable=True)

    running_balance = Column(Text, nullable=True)

    report_bucket = Column(
        Text,
        ForeignKey("private.report_buckets.key"),
        nullable=False,
    )

    classification_confidence = Column(Double, nullable=False)

    classification_probabilities = Column(JSONB(none_as_null=True), nullable=False)

    report_bucket_override = Column(
        Text, ForeignKey("private.report_buckets.key"), nullable=True
    )

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
