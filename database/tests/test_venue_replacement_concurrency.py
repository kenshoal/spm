"""Local-only committed-fixture test for SCRUM-63's venue replacement (0068) under concurrency.

Use a disposable scrum48_* database with the SCRUM-35 amendment bootstrap applied (it includes
0064 and 0068), never shared Supabase, and discard it afterwards (fixtures are committed).

The lock protocol under test: create_replacement_venue_booking_request calls 0056's creator
(venue row, then event row), then locks the replaced booking and checks it again.
decide_venue_booking_request locks the venue row, then the request row, then updates the
replaced booking. cancel_venue_booking_request locks only its own row. So each pair below runs
one at a time, and the second session sees the first's committed result.
"""
import argparse
import subprocess
import time
import unittest
from urllib.parse import urlparse
from uuid import uuid4


class VenueReplacementConcurrencyTest(unittest.TestCase):
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
        """Start the first session, wait until it holds its locks, then start the second and
        require it to wait on a lock before the first commits."""
        first = self.start(first_app, first_query)
        second = None
        try:
            self.wait_for(first_app, "wait_event='PgSleep'", first, "its locks")
            second = self.start(second_app, second_query)
            self.wait_for(second_app, "wait_event_type='Lock'", second, "a wait on a lock")
            return self.finish(first), self.finish(second)
        finally:
            for process in (first, second):
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=5)

    def fixture(self):
        """A flagged approved booking at venue 1 of an event with an assigned coordinator, and
        two other venues. Returns the ids."""
        tag = uuid4()
        user = self.sql("SELECT id FROM auth.users ORDER BY created_at LIMIT 1;")
        actor = self.sql("SELECT gen_random_uuid();")
        event = self.sql(f"""
            INSERT INTO public.event_requests (organiser_id, event_name, status)
            VALUES ('{user}', 'RACE SCRUM-63 {tag}', 'Planning') RETURNING id;""")
        self.sql(f"""
            INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
            VALUES ('{event}', '{actor}', 'race63');""")
        venues = [
            self.sql(f"""
                INSERT INTO public.venues (name, location, max_capacity, facilities, accessibility_features,
                    supported_layouts, operating_slots)
                VALUES ('RACE SCRUM-63 {tag} {n}', 'Race wing', 10, '{{}}', '{{}}',
                    ARRAY['theatre']::public.room_layout[], ARRAY['AM','PM','NIGHT']::public.booking_slot[])
                RETURNING id;""")
            for n in range(3)
        ]
        booking = self.sql(f"""
            INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id, start_date, end_date,
                start_minute, end_minute, status, decided_by, decided_at)
            VALUES ('{venues[0]}', '{actor}', '{event}', current_date + 70, current_date + 70, 540, 720,
                'approved', '{user}', now()) RETURNING id;""")
        self.sql(f"""
            INSERT INTO public.arrangement_reviews (event_request_id, arrangement, arrangement_id, trigger_id,
                trigger_type, changed_fields, reason)
            VALUES ('{event}', 'venue_booking', '{booking}', gen_random_uuid(), 'venue_block', '{{}}', 'RACE flag');""")
        return {"user": user, "actor": actor, "event": event, "venues": venues, "booking": booking}

    def replace(self, f, venue):
        return (f"SELECT id FROM public.create_replacement_venue_booking_request('{f['booking']}', gen_random_uuid(), "
                f"'{venue}', '{f['actor']}', (SELECT updated_at FROM public.event_requests WHERE id = '{f['event']}'))")

    def status(self, booking_id):
        return self.sql(f"SELECT status FROM public.venue_booking_requests WHERE id='{booking_id}';")

    def replacements(self, f):
        return self.sql(f"SELECT count(*) FROM public.venue_booking_requests WHERE replaces_booking_id='{f['booking']}';")

    # AC4-X1 (cross-cutting): two replacements for one flagged booking cannot both be stored;
    # the second waits on the event lock, then hits the one-active-replacement rule
    def test_two_replacements_for_one_booking_store_only_one(self):
        f = self.fixture()

        (first_code, _, first_error), (second_code, _, second_error) = self.run_pair(
            f"race-replace-1-{f['booking']}", f"BEGIN; {self.replace(f, f['venues'][1])}; SELECT pg_sleep(1.5); COMMIT;",
            f"race-replace-2-{f['booking']}", f"{self.replace(f, f['venues'][2])};",
        )

        self.assertEqual(first_code, 0, first_error)
        self.assertNotEqual(second_code, 0)
        self.assertIn("venue_booking_replacement_active_idx", second_error)
        self.assertEqual(self.replacements(f), "1")
        self.assertEqual(self.status(f["booking"]), "approved")

    # AC4-X4 (cross-cutting): a replacement requested while the coordinator is cancelling the
    # booking is refused once the cancel commits, and nothing is stored
    def test_replacement_for_a_booking_being_cancelled_is_refused(self):
        f = self.fixture()

        (cancel_code, _, cancel_error), (replace_code, _, replace_error) = self.run_pair(
            f"race-cancel-{f['booking']}",
            f"BEGIN; SELECT public.cancel_venue_booking_request('{f['booking']}', '{f['actor']}'); SELECT pg_sleep(1.5); COMMIT;",
            f"race-replace-{f['booking']}", f"{self.replace(f, f['venues'][1])};",
        )

        self.assertEqual(cancel_code, 0, cancel_error)
        self.assertNotEqual(replace_code, 0)
        self.assertIn("booking is not approved", replace_error)
        self.assertEqual(self.replacements(f), "0")
        self.assertEqual(self.status(f["booking"]), "cancelled")

    # AC5-X1 (cross-cutting): approving a replacement while the coordinator cancels the original
    # leaves one consistent result: the replacement approved and the original cancelled, once
    def test_approval_and_a_cancel_of_the_original_agree(self):
        f = self.fixture()
        replacement = self.sql(f"{self.replace(f, f['venues'][1])};")

        (approve_code, approve_out, approve_error), (cancel_code, _, cancel_error) = self.run_pair(
            f"race-approve-{replacement}",
            f"""BEGIN; SELECT public.decide_venue_booking_request('{replacement}', 'approved', '{f['user']}');
                SELECT pg_sleep(1.5); COMMIT;""",
            f"race-cancel-{f['booking']}",
            f"SELECT public.cancel_venue_booking_request('{f['booking']}', '{f['actor']}');",
        )

        self.assertEqual(approve_code, 0, approve_error)
        self.assertIn('"outcome": "approved"', approve_out)
        self.assertNotEqual(cancel_code, 0)
        self.assertIn("cannot be cancelled", cancel_error)
        self.assertEqual(self.status(replacement), "approved")
        self.assertEqual(self.status(f["booking"]), "cancelled")
        self.assertEqual(self.sql(
            f"SELECT cancelled_by FROM public.venue_booking_requests WHERE id='{f['booking']}';"
        ), f["user"])
        self.assertEqual(self.sql(
            f"SELECT count(*) FROM public.arrangement_reviews WHERE arrangement_id='{f['booking']}' AND cleared_at IS NULL;"
        ), "0")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", default="psql")
    parser.add_argument("--disposable", action="store_true", help="Confirm this is an owned disposable database")
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in ("127.0.0.1", "localhost", "::1"):
        parser.error("Only a disposable local database is allowed; fixtures are committed")
    DSN, PSQL = args.dsn, args.psql
    unittest.main(argv=["test_venue_replacement_concurrency"], verbosity=2)
