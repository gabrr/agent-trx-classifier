from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.base import utc_now
from db.models import User


def synchronize_verified_profile(
    session: Session, verified_owner_id: UUID, *, email=None, display_name=None
) -> User:
    """Call only with identity and profile data from verified authentication."""
    statement = insert(User).values(
        id=verified_owner_id, email=email, display_name=display_name
    )

    session.execute(
        statement.on_conflict_do_update(
            index_elements=[User.id],
            set_={
                "email": email,
                "display_name": display_name,
                "updated_at": utc_now(),
            },
        )
    )

    return session.get(User, verified_owner_id, populate_existing=True)
