"""Local-only committed-fixture test for SCRUM-20's venue conflict guard (0054) under concurrency.

Use a disposable database with 0023, 0024, 0043, 0050, 0051 and 0054 applied, never shared
Supabase, and discard it afterwards (fixtures are committed).

The lock protocol under test: decide_venue_booking_request locks the venue row FOR UPDATE,
then the request, and checks conflicts through private.check_booking_candidate. The guard
takes no locks; a caller (SCRUM-35's reschedule) holds the same venue lock before calling
it. So two writers for one venue run one at a time, and the second sees the first's booking.
"""
import argparse
import json
import subprocess
import time
import unittest
from urllib.parse import urlparse
from uuid import uuid4


class VenueBookingConflictConcurrencyTest(unittest.TestCase):
    def sql(self, query):
        result = subprocess.run(
            # -q drops command tags such as "INSERT 0 1", so RETURNING gives just the value.
            [PSQL, "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1", "-d", DSN, "-c", query],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def start(self, application, query):
        return subprocess.Popen(
            [PSQL, "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1", "-d", DSN,
             "-c", f"SET application_name='{application}';", "-c", query],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

    def wait_for(self, application, condition, process, what):
        """Poll pg_stat_activity until the session reaches a state, not an arbitrary delay."""
        deadline = time.monotonic() + 5
        while self.sql(
            f"SELECT count(*) FROM pg_stat_activity WHERE application_name='{application}' AND {condition};"
        ) != "1":
            self.assertIsNone(process.poll(), f"{application} ended before {what}")
            self.assertLess(time.monotonic(), deadline, f"{application} never reached {what}")
            time.sleep(0.02)

    def finish(self, process):
        output, error = process.communicate(timeout=15)
        return process.returncode, output.strip(), error

    def run_pair(self, first_app, first_query, second_app, second_query):
        """Start the first session, wait until it holds its lock, then start the second and
        require it to wait on a lock before the first commits."""
        first = self.start(first_app, first_query)
        second = None
        try:
            self.wait_for(first_app, "wait_event='PgSleep'", first, "its venue lock")
            second = self.start(second_app, second_query)
            self.wait_for(second_app, "wait_event_type='Lock'", second, "a wait on the venue lock")
            return self.finish(first), self.finish(second)
        finally:
            for process in (first, second):
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=5)

    def venue(self):
        """A venue with setup 30 and turnaround 45, so 10:00-12:00 occupies 09:30-12:45."""
        return self.sql(f"""
            INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
                supported_layouts, operating_slots, setup_minutes, turnaround_minutes)
            VALUES ('RACE SCRUM-20 {uuid4()}', 'Race wing', 10, '{{}}', '{{}}',
                ARRAY['theatre']::public.room_layout[], ARRAY['AM','PM','NIGHT']::public.booking_slot[], 30, 45)
            RETURNING id;
        """)

    def request(self, venue_id, start, end):
        return self.sql(f"""
            INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
                start_date, end_date, start_minute, end_minute)
            SELECT '{venue_id}', id, gen_random_uuid(), current_date + 60, current_date + 60, {start}, {end}
            FROM auth.users ORDER BY created_at LIMIT 1
            RETURNING id;
        """)

    def approve(self, request_id):
        return f"""SELECT public.decide_venue_booking_request('{request_id}', 'approved', id)
                   FROM auth.users ORDER BY created_at LIMIT 1"""

    def status(self, request_id):
        return self.sql(f"SELECT status FROM public.venue_booking_requests WHERE id='{request_id}';")

    # AC1-X1 (cross-cutting): two approvals for padded-overlapping times at one venue cannot both
    # succeed; the second waits on the venue lock, then is refused and recorded
    def test_second_overlapping_approval_waits_then_is_refused(self):
        venue_id = self.venue()
        first_id = self.request(venue_id, 600, 720)
        second_id = self.request(venue_id, 735, 780)

        (first_code, _, first_error), (second_code, second_out, second_error) = self.run_pair(
            f"race-approve-{first_id}", f"BEGIN; {self.approve(first_id)}; SELECT pg_sleep(1.5); COMMIT;",
            f"race-approve-{second_id}", f"{self.approve(second_id)};",
        )

        self.assertEqual(first_code, 0, first_error)
        self.assertEqual(second_code, 0, second_error)
        result = json.loads(second_out)
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(result["refusal_codes"], ["booking_conflict"])
        self.assertEqual(result["conflicting_booking_ids"], [first_id])
        self.assertEqual(self.status(first_id), "approved")
        self.assertEqual(self.status(second_id), "pending")
        self.assertEqual(self.sql(
            f"SELECT count(*) FROM public.venue_booking_refusals WHERE booking_request_id='{second_id}';"
        ), "1")

    # AC4-X1 (cross-cutting): a reschedule caller that holds the venue lock, as the contract
    # requires, waits for an in-flight approval and then the guard reports it
    def test_guard_under_the_venue_lock_sees_an_approval_that_was_in_flight(self):
        venue_id = self.venue()
        approved_id = self.request(venue_id, 600, 720)
        moved_id = self.request(venue_id, 1080, 1140)

        (approve_code, _, approve_error), (check_code, check_out, check_error) = self.run_pair(
            f"race-approve-{approved_id}",
            f"BEGIN; {self.approve(approved_id)}; SELECT pg_sleep(1.5); COMMIT;",
            f"race-reschedule-{moved_id}",
            f"""BEGIN;
                SELECT 1 FROM public.venues WHERE id = '{venue_id}' FOR UPDATE;
                SELECT private.check_booking_candidate('{venue_id}', current_date + 60, current_date + 60,
                    660, 720, ARRAY['{moved_id}']::uuid[]);
                ROLLBACK;""",
        )

        self.assertEqual(approve_code, 0, approve_error)
        self.assertEqual(check_code, 0, check_error)
        result = json.loads(check_out.splitlines()[-1])
        self.assertEqual(result["refusal_codes"], ["booking_conflict"])
        self.assertEqual(result["conflicting_booking_ids"], [approved_id])
        self.assertEqual(self.status(approved_id), "approved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", default="psql")
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in ("127.0.0.1", "localhost", "::1"):
        parser.error("Only a disposable local database is allowed; fixtures are committed")
    DSN, PSQL = args.dsn, args.psql
    unittest.main(argv=["test_venue_booking_conflict_concurrency"], verbosity=2)
