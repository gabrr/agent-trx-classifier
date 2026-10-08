from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from db.base import Base, utc_now


class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="file_size"),
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

    filename = Column(Text, nullable=False)

    content_type = Column(Text, nullable=False)

    size_bytes = Column(BigInteger, nullable=False)

    storage_bucket = Column(Text, nullable=False)

    storage_object = Column(Text, nullable=False)

    storage_generation = Column(Text, nullable=True)

    checksum = Column(Text, nullable=True)

    status = Column(Text, nullable=False)

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
