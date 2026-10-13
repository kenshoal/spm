"""Create SCRUM-48 test fixtures in an empty disposable local PostgreSQL database.

Requires PostgreSQL 14+ and psql, plus an explicitly disposable database named
scrum48_*. Never run this fixture against shared Supabase or an existing schema.
"""
import argparse
import subprocess
from pathlib import Path
from urllib.parse import urlparse


MIGRATIONS = (
    "0007_event_requests.sql",
    "0008_event_request_submission_outbox.sql",
    "0010_staff_roles.sql",
    "0011_event_coordinator_assignments.sql",
    "0011_event_request_review_status.sql",
    "0012_coordinator_status_transitions.sql",
    "0016_event_request_review_decisions.sql",
    "0022_monotonic_event_request_updated_at_trigger.sql",
)

# These auth functions are deliberately test doubles; they do not prove Supabase Auth.
AUTH_FIXTURE = """
CREATE ROLE anon;
CREATE ROLE authenticated;
CREATE ROLE service_role BYPASSRLS;
CREATE SCHEMA auth;
CREATE TABLE auth.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz DEFAULT now()
);
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS 'SELECT NULL::uuid';
CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql AS 'SELECT ''{}''::jsonb';
INSERT INTO auth.users DEFAULT VALUES;
"""

# Refuse any user schema/object, even empty tables or functions. The fixture also
# owns its role definitions; an existing matching role means the cluster is reused.
EMPTY_TARGET = """
SELECT current_database(),
    (SELECT count(*) FROM pg_namespace WHERE nspname NOT LIKE 'pg_%'
        AND nspname NOT IN ('public', 'information_schema'))
  + (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema')
  + (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema')
  + (SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
        WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema')
  + (SELECT count(*) FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role'));
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", default="psql")
    parser.add_argument("--disposable", action="store_true", help="Confirm ownership of an empty disposable local cluster")
    args = parser.parse_args()
    parsed = urlparse(args.dsn)
    database = parsed.path.removeprefix("/")
    if not args.disposable or parsed.scheme not in ("postgres", "postgresql"):
        parser.error("Use --disposable and an explicit PostgreSQL URL")
    if parsed.hostname not in ("127.0.0.1", "localhost", "::1") or not database.startswith("scrum48_"):
        parser.error("Only a loopback database named scrum48_* is allowed")

    command = [args.psql, "-X", "-At", "-v", "ON_ERROR_STOP=1", "-d", args.dsn]
    check = subprocess.run(command, input=EMPTY_TARGET, text=True, capture_output=True, timeout=15)
    if check.returncode:
        parser.error("Could not inspect the disposable database: " + check.stderr.strip())
    if check.stdout.strip() != database + "|0":
        parser.error("Refusing a nonempty or reused target; initialise a fresh owned disposable cluster")

    migrations = Path(__file__).resolve().parents[2] / "database" / "migrations"
    statements = [AUTH_FIXTURE] + [(migrations / name).read_text() for name in MIGRATIONS]
    statements.append("""
        INSERT INTO public.event_requests(id,organiser_id,status)
        SELECT '48000000-0000-4000-8000-000000000001',id,'Draft' FROM auth.users LIMIT 1;
        GRANT USAGE ON SCHEMA public TO service_role;
        GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;
    """)
    statements.append((migrations / "0025_event_request_status_history.sql").read_text())
    result = subprocess.run(command, input="BEGIN;\n" + "\n".join(statements) + "\nCOMMIT;", text=True, capture_output=True, timeout=30)
    if result.returncode:
        parser.error("Fixture creation rolled back: " + result.stderr.strip())
    print("Disposable SCRUM-48 schema created with one honest legacy Draft baseline.")


if __name__ == "__main__":
    main()
