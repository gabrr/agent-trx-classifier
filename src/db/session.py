from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


def session_factory(engine: Engine) -> sessionmaker:
    """Repositories take a Session; callers commit via `with factory.begin()`."""
    return sessionmaker(engine, expire_on_commit=False)
