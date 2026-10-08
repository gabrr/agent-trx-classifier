from sqlalchemy import select

from db.base import utc_now
from db.models import LoginAttempt, SessionRecord


def _ciphertext(value):
    if not isinstance(value, bytes) or not value:
        raise ValueError("Nonempty encrypted bytes required")


def create_session(
    session,
    owner_id,
    *,
    id_hash,
    encrypted_provider_tokens,
    encryption_key_version,
    csrf_token_hash,
    expires_at,
):
    """Caller hashes IDs and encrypts tokens before crossing this boundary."""
    _ciphertext(encrypted_provider_tokens)

    record = SessionRecord(
        id_hash=id_hash,
        owner_id=owner_id,
        encrypted_provider_tokens=encrypted_provider_tokens,
        encryption_key_version=encryption_key_version,
        csrf_token_hash=csrf_token_hash,
        expires_at=expires_at,
        refresh_version=0,
    )

    session.add(record)

    session.flush()

    return record


def get_session(session, owner_id, id_hash):
    return session.scalar(
        select(SessionRecord).where(
            SessionRecord.id_hash == id_hash,
            SessionRecord.owner_id == owner_id,
            SessionRecord.revoked_at.is_(None),
            SessionRecord.expires_at > utc_now(),
        )
    )


def revoke_session(session, owner_id, id_hash):
    record = session.scalar(
        select(SessionRecord)
        .where(SessionRecord.id_hash == id_hash, SessionRecord.owner_id == owner_id)
        .with_for_update()
    )

    if record is None:
        raise LookupError("Session not found")

    record.revoked_at = utc_now()


def create_login_attempt(
    session,
    *,
    id_hash,
    browser_binding_hash,
    encrypted_pkce_verifier,
    encryption_key_version,
    expires_at,
):
    _ciphertext(encrypted_pkce_verifier)

    attempt = LoginAttempt(
        id_hash=id_hash,
        browser_binding_hash=browser_binding_hash,
        encrypted_pkce_verifier=encrypted_pkce_verifier,
        encryption_key_version=encryption_key_version,
        expires_at=expires_at,
    )

    session.add(attempt)

    session.flush()

    return attempt


def consume_login_attempt(session, *, id_hash, browser_binding_hash):
    # No owner exists before login; the hashed browser binding is mandatory.
    attempt = session.scalar(
        select(LoginAttempt)
        .where(
            LoginAttempt.id_hash == id_hash,
            LoginAttempt.browser_binding_hash == browser_binding_hash,
            LoginAttempt.consumed_at.is_(None),
            LoginAttempt.expires_at > utc_now(),
        )
        .with_for_update()
    )

    if attempt is None:
        raise LookupError("Login attempt not found")

    attempt.consumed_at = utc_now()

    return attempt
