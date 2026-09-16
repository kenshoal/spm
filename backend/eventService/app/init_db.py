"""One-off bootstrap: create this service's own table.

Run manually against a real Postgres after configuring DATABASE_URL
(`.env` or the environment):

    python -m app.init_db

Only ever creates `event_coordinator_assignments` — explicitly restricted
to that one table so this can never touch `event_requests`, which is
eventRequestService's table, not this service's to create or alter.

There's no migration tooling in this repo yet — this is a stand-in until
one lands. Safe to re-run: create_all is idempotent (skips existing
tables).
"""

from app.db import Base, engine
from app.models import EventCoordinatorAssignment


def main() -> None:
    Base.metadata.create_all(engine, tables=[EventCoordinatorAssignment.__table__])
    print(f"Created table {EventCoordinatorAssignment.__tablename__!r}.")


if __name__ == "__main__":
    main()
