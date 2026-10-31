"""Local-only committed-fixture test for SCRUM-18's venue holds (0066) under concurrency.

Use a disposable database with 0066 applied (for example built by
bootstrap_event_change_approval.py), never shared Supabase, and discard it
afterwards (fixtures are committed).

The lock protocol under test: place_venue_hold, release/convert, booking approval
and booking creation all lock the venue row FOR UPDATE first, and the shared guard
(private.check_booking_candidate) reports active holds. So two writers for one
venue run one at a time, and the second sees the first's hold or booking.
"""
import argparse
import json
import subprocess
import time
import unittest
from urllib.parse import urlparse
from uuid import uuid4


class VenueHoldConcurrencyTest(unittest.TestCase):
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

    def fixture(self):
        """A 30/45 venue and a Planning event assigned to the oldest auth user."""
        venue = self.sql(f"""
            INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
                supported_layouts, operating_slots, setup_minutes, turnaround_minutes)
            VALUES ('RACE SCRUM-18 {uuid4()}', 'Race wing', 10, '{{}}', '{{}}',
                ARRAY['theatre']::public.room_layout[], ARRAY['AM','PM','NIGHT']::public.booking_slot[], 30, 45)
            RETURNING id;
        """)
        event = self.sql("""
            INSERT INTO public.event_requests (organiser_id, event_name, status)
            SELECT id, 'RACE SCRUM-18', 'Planning' FROM auth.users ORDER BY created_at LIMIT 1
            RETURNING id;
        """)
        self.sql(f"""
            INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
            SELECT '{event}', id::text, id::text FROM auth.users ORDER BY created_at LIMIT 1;
        """)
        return venue, event

    def place(self, venue, event, start, end):
        return f"""SELECT public.place_venue_hold('{venue}', '{event}', current_date + 60,
                       current_date + 60, {start}, {end}, now() + interval '1 day', id)
                   FROM auth.users ORDER BY created_at LIMIT 1"""

    # AC2-X1 (cross-cutting): two holds for padded-overlapping times cannot both be placed; the
    # second waits on the venue lock, then is refused with the first hold
    def test_second_overlapping_hold_waits_then_is_refused(self):
        venue, event = self.fixture()
        (first_code, first_out, first_error), (second_code, second_out, second_error) = self.run_pair(
            f"race-hold-a-{venue}",
            f"BEGIN; {self.place(venue, event, 600, 720)}; SELECT pg_sleep(1.5); COMMIT;",
            f"race-hold-b-{venue}",
            f"{self.place(venue, event, 735, 780)};",
        )
        self.assertEqual(first_code, 0, first_error)
        self.assertEqual(second_code, 0, second_error)
        first = json.loads(first_out.splitlines()[0])
        second = json.loads(second_out)
        self.assertEqual(first["outcome"], "placed")
        self.assertEqual(second["outcome"], "refused")
        self.assertEqual(second["refusal_codes"], ["hold_conflict"])
        self.assertEqual(second["conflicting_hold_ids"], [first["hold"]["id"]])
        self.assertEqual(self.sql(f"SELECT count(*) FROM public.venue_holds WHERE venue_id='{venue}';"), "1")

    # AC2-X2 (cross-cutting): another event's booking approval racing a new hold waits on the
    # venue lock, then is refused with hold_conflict and stays pending
    def test_approval_waits_for_an_in_flight_hold_then_is_refused(self):
        venue, event = self.fixture()
        _, rival = self.fixture()
        booking = self.sql(f"""
            INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
                start_date, end_date, start_minute, end_minute)
            SELECT '{venue}', id, '{rival}', current_date + 60, current_date + 60, 735, 780
            FROM auth.users ORDER BY created_at LIMIT 1
            RETURNING id;
        """)
        (hold_code, _, hold_error), (approve_code, approve_out, approve_error) = self.run_pair(
            f"race-hold-{venue}",
            f"BEGIN; {self.place(venue, event, 600, 720)}; SELECT pg_sleep(1.5); COMMIT;",
            f"race-approve-{booking}",
            f"""SELECT public.decide_venue_booking_request('{booking}', 'approved', id)
                FROM auth.users ORDER BY created_at LIMIT 1;""",
        )
        self.assertEqual(hold_code, 0, hold_error)
        self.assertEqual(approve_code, 0, approve_error)
        result = json.loads(approve_out)
        self.assertEqual(result["outcome"], "refused")
        self.assertEqual(result["refusal_codes"], ["hold_conflict"])
        self.assertEqual(
            self.sql(f"SELECT status FROM public.venue_booking_requests WHERE id='{booking}';"), "pending"
        )

    # AC5-X1 (cross-cutting): releasing a hold while a second hold for the same time waits lets
    # the second through once the release commits
    def test_hold_waiting_on_a_release_is_placed(self):
        venue, event = self.fixture()
        placed = json.loads(self.sql(f"{self.place(venue, event, 600, 720)};"))
        hold_id = placed["hold"]["id"]
        (release_code, _, release_error), (place_code, place_out, place_error) = self.run_pair(
            f"race-release-{hold_id}",
            f"""BEGIN;
                SELECT public.release_venue_hold('{hold_id}', id) FROM auth.users ORDER BY created_at LIMIT 1;
                SELECT pg_sleep(1.5);
                COMMIT;""",
            f"race-replace-{hold_id}",
            f"{self.place(venue, event, 600, 720)};",
        )
        self.assertEqual(release_code, 0, release_error)
        self.assertEqual(place_code, 0, place_error)
        self.assertEqual(json.loads(place_out)["outcome"], "placed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", default="psql")
    parser.add_argument("--disposable", action="store_true", help="Confirm the database is disposable")
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in ("127.0.0.1", "localhost", "::1"):
        parser.error("Only a disposable local database is allowed; fixtures are committed")
    DSN, PSQL = args.dsn, args.psql
    unittest.main(argv=["test_venue_hold_concurrency"], verbosity=2)
