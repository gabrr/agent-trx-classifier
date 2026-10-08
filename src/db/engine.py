from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def create_database_engine(url: str) -> Engine:
    # Disabling named prepared statements also supports Supabase transaction pools.
    return create_engine(
        url,
        connect_args={"connect_timeout": 3, "prepare_threshold": None},
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
        pool_timeout=3,
        hide_parameters=True,
    )
