"""One-off bootstrap: create the event_service schema and its tables.

Run manually against a real Postgres after configuring DATABASE_URL
(`.env` or the environment):

    python -m app.init_db

There's no migration tooling in this repo yet — this is a stand-in until
one lands. Safe to re-run: both operations are idempotent.
"""

from sqlalchemy import text

from app import models  # noqa: F401  (registers Event/StatusHistory on Base.metadata)
from app.db import SCHEMA, Base, engine


def main() -> None:
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    Base.metadata.create_all(engine)
    print(f"Created schema {SCHEMA!r} and its tables.")


if __name__ == "__main__":
    main()
