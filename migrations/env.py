from alembic import context
from sqlalchemy import create_engine, pool, text

from config import database_url
from db import models  # noqa: F401
from db.base import Base

url = database_url()

if not url:
    raise ValueError("DATABASE_URL is required for migrations")


def configure(connection=None):
    context.configure(
        connection=connection,
        url=url if connection is None else None,
        target_metadata=Base.metadata,
        include_schemas=True,
        version_table_schema="private",
        literal_binds=connection is None,
    )

    if connection is None:
        context.execute("CREATE SCHEMA IF NOT EXISTS private")

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    configure()

else:
    engine = create_engine(
        url,
        poolclass=pool.NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": 3, "prepare_threshold": None},
    )

    with engine.connect() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS private"))

        connection.commit()

        configure(connection)

    engine.dispose()
