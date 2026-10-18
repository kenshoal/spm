"""Build the SCRUM-58 safety-review schema in an empty disposable local PostgreSQL database.

Runs the SCRUM-48 bootstrap (same safety checks: loopback only, database named
scrum48_*, empty cluster), then SCRUM-64's supplemental recipe from
database/README.md plus SCRUM-60's decision migrations and SCRUM-58's 0039/0046.
Each file runs in its own psql call, as 0041 must commit its new enum value
before 0042 uses it. Never run this against shared Supabase.
"""
import argparse
import subprocess
import sys
from pathlib import Path

MIGRATIONS = (
    "0001_baseline.sql",
    "0002_transition_equipment_status.sql",
    "0003_create_equipment_fn.sql",
    "0004_quantity_history.sql",
    "0005_rls_and_function_access.sql",
    "0006_rpc_execute_grants.sql",
    "0016_venues.sql",
    "0017_notifications.sql",
    "0018_venue_booking_requests.sql",
    "0018_event_change_requests.sql",
    "0019_event_change_requests_organiser_index.sql",
    "0020_event_change_request_updated_at.sql",
    "0021_event_change_request_monotonic_updated_at.sql",
    "0020_equipment_reservations.sql",
    "0021_equipment_requirements.sql",
    "0027_equipment_reservation_requirements.sql",
    "0028_reserve_equipment_type_check.sql",
    "0026_event_request_planning.sql",
    "0029_safety_review_status.sql",
    "0030_arrangement_review_reads.sql",
    "0031_arrangement_review_event_changes.sql",
    "0032_arrangement_review_clear.sql",
    "0033_arrangement_review_equipment_unavailability.sql",
    "0034_safety_review_decisions.sql",
    "0035_arrangement_review_shared_reads.sql",
    "0036_arrangement_review_safety_rechecks.sql",
    "0037_arrangement_review_notification_outbox.sql",
    "0038_arrangement_review_notification_delivery.sql",
    "0039_send_for_safety_review.sql",
    "0040_arrangement_review_safety_recheck_lock_compatibility.sql",
    "0041_booking_request_cancelled_status.sql",
    "0042_cancel_venue_booking_request.sql",
    "0043_venue_setup_turnaround.sql",
    "0044_safety_review_null_inputs.sql",
    "0045_safety_review_arrangement_reviews.sql",
    "0046_shared_event_readiness.sql",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", default="psql")
    parser.add_argument("--disposable", action="store_true", help="Confirm ownership of an empty disposable local cluster")
    parser.add_argument("--through", help="Stop after this migration file name, e.g. to see a Red run before a new one")
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
    psql = [args.psql, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", args.dsn]
    # Local Auth test-double column (SCRUM-64 recipe); genuine Supabase Auth already has it.
    steps = [("auth test double", "ALTER TABLE auth.users ADD COLUMN raw_app_meta_data jsonb NOT NULL DEFAULT '{}'::jsonb")]
    if args.through and args.through not in MIGRATIONS:
        parser.error(f"--through {args.through} is not in the migration list")
    for name in MIGRATIONS:
        steps.append((name, (migrations / name).read_text()))
        if name == args.through:
            break
    for name, script in steps:
        result = subprocess.run(psql, input=script, text=True, capture_output=True, timeout=60)
        if result.returncode:
            parser.error(f"{name} failed: " + result.stderr.strip())
    print("Disposable SCRUM-58 safety-review schema created.")


if __name__ == "__main__":
    main()
