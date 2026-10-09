"""Remove unused backend sessions and login attempts."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """LOCK TABLE private.sessions, private.login_attempts IN ACCESS EXCLUSIVE MODE"""
    )

    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM private.sessions)
           OR EXISTS (SELECT 1 FROM private.login_attempts) THEN
            RAISE EXCEPTION 'Obsolete authentication tables contain data; review before removal';
        END IF;
        END $$"""
    )

    op.drop_table("sessions", schema="private")

    op.drop_table("login_attempts", schema="private")


def downgrade():
    raise RuntimeError("Backend-managed authentication is no longer supported")
