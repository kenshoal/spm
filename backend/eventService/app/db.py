"""SQLAlchemy engine and session setup.

Connects to the shared Supabase Postgres project. Each microservice owns
its own schema there — see SCHEMA below — rather than a separate database,
so this module namespaces every table under it instead of the default
"public" schema.

Loads a local `.env` file if one is present (see `.env.example`) without
overwriting a real environment variable, so deployed environments that set
DATABASE_URL directly are unaffected.

`create_engine` does not open a connection until a session is used, so
importing this module — and running the test suite, which overrides
`get_db` with an in-memory SQLite session — never requires a live database.
"""

import os
import re
from collections.abc import Iterator

from dotenv import load_dotenv
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

# One schema per microservice in the shared Supabase project.
SCHEMA = "event_service"

_LOCAL_FALLBACK_URL = "postgresql+psycopg://event:event@localhost:5432/event"


def _as_psycopg_url(raw: str) -> str:
    """Normalize a bare postgres:// or postgresql:// URL (e.g. Supabase's
    connection string) to the psycopg (v3) driver this project depends on
    — SQLAlchemy would otherwise default to psycopg2, which isn't
    installed."""
    return re.sub(r"^postgres(?:ql)?://", "postgresql+psycopg://", raw, count=1)


DATABASE_URL = _as_psycopg_url(os.getenv("DATABASE_URL", _LOCAL_FALLBACK_URL))

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

metadata = MetaData(schema=SCHEMA)


class Base(DeclarativeBase):
    metadata = metadata


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
