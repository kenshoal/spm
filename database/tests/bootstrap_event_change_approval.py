"""Build the SCRUM-35 amendment schema in an empty, owned local PostgreSQL cluster.

Reuses bootstrap_safety_review.py and its strict loopback/scrum48_*/empty-cluster
checks, genuine migrations and explicitly labelled Auth doubles. Supplemental
files are applied separately so previously added enum values are committed.
No production function is replaced with a fixture. Never target shared Supabase.
"""

import argparse
import subprocess
import sys
from pathlib import Path

SUPPLEMENTAL_MIGRATIONS = (
    "0023_venue_blocks.sql",
    "0024_venue_booking_decisions.sql",
    "0047_safety_review_approval_readiness.sql",
    "0049_event_change_rejection.sql",
    "0051_venue_block_times.sql",
    "0053_event_change_non_date_approval.sql",
    "0054_venue_booking_conflict_guard.sql",
    "0055_venue_timing_change_reviews.sql",
    "0056_event_venue_booking_creation.sql",
    "0058_event_registration_reviews.sql",
    "0059_event_change_date_approval.sql",
    "0064_venue_block_booking_reviews.sql",
    "0068_venue_replacement_requests.sql",
)

# Vanilla PostgreSQL lacks the platform baseline ACLs independently observed
# on shared SPM on 22 October. Match only the required read/lock permissions;
# never restore the service INSERT/DELETE revoked by genuine 0056.
LOCAL_PLATFORM_ACL = """
GRANT SELECT, UPDATE ON public.venues TO service_role;
GRANT SELECT ON public.venue_blocks TO service_role;
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", default="psql")
    parser.add_argument("--disposable", action="store_true", help="Confirm ownership of an empty disposable local cluster")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    baseline = subprocess.run(
        [sys.executable, "-I", str(here / "bootstrap_safety_review.py"),
         "--dsn", args.dsn, "--psql", args.psql] + (["--disposable"] if args.disposable else []),
        text=True, capture_output=True, timeout=120, check=False,
    )
    if baseline.returncode:
        parser.error("Guarded safety-review bootstrap refused or failed: " + baseline.stderr.strip())
    print(baseline.stdout.strip(), flush=True)
    migrations = here.parent / "migrations"
    command = [args.psql, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", args.dsn]
    for name, script in [
        *((name, (migrations / name).read_text()) for name in SUPPLEMENTAL_MIGRATIONS),
        ("observed local platform ACL fixture", LOCAL_PLATFORM_ACL),
    ]:
        result = subprocess.run(command, input=script, text=True, capture_output=True, timeout=60, check=False)
        if result.returncode:
            parser.error(f"{name} failed: " + result.stderr.strip())
        print("Applied " + name, flush=True)
    print("Disposable SCRUM-35 amendment schema created; Auth is a local test double.")


if __name__ == "__main__":
    main()
