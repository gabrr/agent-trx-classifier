from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    LargeBinary,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from db.base import Base, utc_now


class SessionRecord(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("refresh_version >= 0", name="refresh_version"),
        {"schema": "private"},
    )

    id_hash = Column(Text, primary_key=True, nullable=False)

    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("private.users.id"),
        nullable=False,
        index=True,
    )

    encrypted_provider_tokens = Column(LargeBinary, nullable=False)

    encryption_key_version = Column(Text, nullable=False)

    csrf_token_hash = Column(Text, nullable=False)

    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    revoked_at = Column(DateTime(timezone=True), nullable=True)

    refresh_version = Column(BigInteger, nullable=False)

    refresh_claim_expires_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    __table_args__ = ({"schema": "private"},)

    id_hash = Column(Text, primary_key=True, nullable=False)

    browser_binding_hash = Column(Text, nullable=False)

    encrypted_pkce_verifier = Column(LargeBinary, nullable=False)

    encryption_key_version = Column(Text, nullable=False)

    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    consumed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
