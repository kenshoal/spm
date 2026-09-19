"""One-off bootstrap: create this service's own tables.

Run manually against a real Postgres after configuring DATABASE_URL
(`.env` or the environment):

    python -m app.init_db

Only ever creates this service's own tables (`_TABLES` below) —
explicitly restricted to those so this can never touch `event_requests`,
which is eventRequestService's table, not this service's to create or
alter.

There's no migration tooling in this repo yet — this is a stand-in until
one lands. Safe to re-run: create_all is idempotent (skips existing
tables).
"""

from app.db import Base, engine
from app.models import EventCoordinatorAssignment, NotificationOutbox

_TABLES = [EventCoordinatorAssignment.__table__, NotificationOutbox.__table__]


def main() -> None:
    Base.metadata.create_all(engine, tables=_TABLES)
    print(f"Created tables {[t.name for t in _TABLES]}.")


if __name__ == "__main__":
    main()
