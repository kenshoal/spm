"""Build the SCRUM-58 safety-review schema in an empty disposable local PostgreSQL database.

Runs the SCRUM-48 bootstrap (same safety checks: loopback only, database named
scrum48_*, empty cluster), then the venue, equipment and status migrations that
send_event_request_for_safety_review reads, ending with 0039. Never run this
against shared Supabase.
"""
import argparse
import subprocess
import sys
from pathlib import Path

MIGRATIONS = (
    "0001_baseline.sql",
    "0016_venues.sql",
    "0018_venue_booking_requests.sql",
    "0020_equipment_reservations.sql",
    "0021_equipment_requirements.sql",
    "0027_equipment_reservation_requirements.sql",
    "0028_reserve_equipment_type_check.sql",
    "0026_event_request_planning.sql",
    "0029_safety_review_status.sql",
    "0039_send_for_safety_review.sql",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", default="psql")
    parser.add_argument("--disposable", action="store_true", help="Confirm ownership of an empty disposable local cluster")
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    base = subprocess.run(
        [sys.executable, "-I", str(here / "bootstrap_event_status_history.py"),
         "--dsn", args.dsn, "--psql", args.psql] + (["--disposable"] if args.disposable else []),
        text=True, capture_output=True, timeout=60,
    )
    if base.returncode:
        parser.error("SCRUM-48 bootstrap refused or failed: " + base.stderr.strip())

    migrations = here.parent / "migrations"
    script = "BEGIN;\n" + "\n".join((migrations / name).read_text() for name in MIGRATIONS) + "\nCOMMIT;"
    result = subprocess.run(
        [args.psql, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", args.dsn],
        input=script, text=True, capture_output=True, timeout=60,
    )
    if result.returncode:
        parser.error("Safety-review migrations rolled back: " + result.stderr.strip())
    print("Disposable SCRUM-58 safety-review schema created.")


if __name__ == "__main__":
    main()
