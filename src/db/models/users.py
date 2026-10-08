from sqlalchemy import Column, DateTime, Text, text
from sqlalchemy.dialects.postgresql import UUID

from db.base import Base, utc_now


class User(Base):
    __tablename__ = "users"
    __table_args__ = ({"schema": "private"},)

    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False)

    email = Column(Text, nullable=True)

    display_name = Column(Text, nullable=True)

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
