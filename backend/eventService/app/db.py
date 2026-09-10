"""SQLAlchemy engine and session setup.

Defaults to the Postgres instance docker-compose wires up; override
`DATABASE_URL` for local runs or tests. `create_engine` does not open a
connection until a session is used, so tests can override `get_db` with an
in-memory SQLite session without a live database.
"""

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://event:event@localhost:5432/event"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
