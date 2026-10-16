"""Local-only committed-fixture test for SCRUM-58's safety-review gate under concurrency.

Use a disposable database built by bootstrap_safety_review.py, never shared Supabase,
and discard the whole cluster afterwards (fixtures are committed and history is immutable).

The lock protocol under test: the gate (send_event_request_for_safety_review) locks only
the event row, FOR UPDATE, and reads everything else unlocked. Writers that can make an
event unready lock their own rows first and reach the event last, through the FK
KEY SHARE taken when they insert a row referencing it, which conflicts with FOR UPDATE.
"""
import argparse
import subprocess
import time
import unittest
from urllib.parse import urlparse
from uuid import uuid4

COORDINATOR = "race-coordinator"


class SafetyReviewConcurrencyTest(unittest.TestCase):
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
            [PSQL, "-X", "-At", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose", "-d", DSN,
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
        _, error = process.communicate(timeout=15)
        return process.returncode, error

    def planning_event(self, approved_booking=True):
        event_id = str(uuid4())
        self.sql(f"""
            INSERT INTO public.event_requests(id, organiser_id, event_name, status)
            SELECT '{event_id}', id, 'RACE SCRUM-58', 'Draft' FROM auth.users ORDER BY created_at LIMIT 1;
            UPDATE public.event_requests SET status = 'Planning' WHERE id = '{event_id}';
            INSERT INTO public.event_coordinator_assignments(event_request_id, coordinator_id, assigned_by)
            VALUES ('{event_id}', '{COORDINATOR}', 'race-manager');
        """)
        if approved_booking:
            self.sql(f"""
                WITH v AS (
                    INSERT INTO public.venues (name, location, max_capacity, facilities,
                        accessibility_features, supported_layouts, operating_slots)
                    VALUES ('Race Hall', 'Level 1', 100, '{{}}', '{{}}', '{{theatre}}', '{{AM,PM}}') RETURNING id
                )
                INSERT INTO public.venue_booking_requests (venue_id, requested_by, event_request_id,
                    start_date, end_date, slots, status, decided_by, decided_at)
                SELECT id, gen_random_uuid(), '{event_id}', DATE '2026-11-02', DATE '2026-11-02', '{{AM}}',
                    'approved', gen_random_uuid(), now() FROM v;
            """)
        return event_id

    def requirement_insert(self, event_id):
        return (
            "INSERT INTO public.equipment_requirements (event_request_id, equipment_type, quantity, recorded_by) "
            f"VALUES ('{event_id}', 'Projector', 3, gen_random_uuid())"
        )

    def assert_no_deadlock(self, *errors):
        for error in errors:
            self.assertNotIn("40P01", error)
            self.assertNotIn("deadlock detected", error)

    # AC2-X2 (cross-cutting): a reservation in flight (requirement then equipment locked, event reached last)
    # does not deadlock with the gate; the gate refuses on committed data and the reservation still commits
    def test_reservation_in_flight_does_not_deadlock_with_handover(self):
        event_id = self.planning_event()
        requirement_id = self.sql(f"{self.requirement_insert(event_id)} RETURNING id;")
        equipment_id = self.sql(
            "INSERT INTO public.equipment (type, total_owned_quantity, home_location) "
            "VALUES ('Projector', 50, 'Store') RETURNING id;"
        )
        writer_app, gate_app = f"race-writer-{event_id}", f"race-gate-{event_id}"
        # The writer holds reserve_equipment's first lock, as if paused inside it, then runs the real function.
        writer = self.start(writer_app, f"""
            BEGIN;
            SELECT 1 FROM public.equipment_requirements WHERE id = '{requirement_id}' FOR UPDATE;
            SELECT pg_sleep(1.5);
            SELECT id FROM public.reserve_equipment('{requirement_id}', '{equipment_id}', 3,
                DATE '2026-11-02', DATE '2026-11-02', gen_random_uuid());
            COMMIT;
        """)
        gate = None
        try:
            self.wait_for(writer_app, "wait_event='PgSleep'", writer, "its requirement lock")
            gate = self.start(gate_app, f"SELECT status FROM public.send_event_request_for_safety_review('{event_id}', '{COORDINATOR}');")
            gate_code, gate_error = self.finish(gate)
            writer_code, writer_error = self.finish(writer)
        finally:
            for process in (writer, gate):
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=5)

        self.assert_no_deadlock(gate_error, writer_error)
        self.assertEqual(writer_code, 0, writer_error)
        # The reservation was uncommitted when the gate read, so the event was correctly not ready yet.
        self.assertNotEqual(gate_code, 0)
        self.assertIn("P0005", gate_error)
        self.assertIn("equipment_not_reserved", gate_error)
        self.assertEqual(self.sql(f"SELECT status FROM public.event_requests WHERE id='{event_id}';"), "Planning")
        self.assertEqual(self.sql(f"SELECT sum(quantity) FROM public.equipment_reservations WHERE requirement_id='{requirement_id}';"), "3")
        # Once committed, the same reservation makes the event ready.
        self.assertEqual(
            self.sql(f"SELECT status FROM public.send_event_request_for_safety_review('{event_id}', '{COORDINATOR}');"),
            "Safety Review",
        )

    # AC3-X2 (cross-cutting): a writer that reached the event first makes the gate wait, then the gate sees its row
    def test_handover_waits_for_uncommitted_requirement_and_refuses(self):
        event_id = self.planning_event()
        writer_app, gate_app = f"race-writer-{event_id}", f"race-gate-{event_id}"
        writer = self.start(writer_app, f"""
            BEGIN;
            {self.requirement_insert(event_id)};
            SELECT pg_sleep(1.5);
            COMMIT;
        """)
        gate = None
        try:
            self.wait_for(writer_app, "wait_event='PgSleep'", writer, "its requirement insert")
            gate = self.start(gate_app, f"SELECT status FROM public.send_event_request_for_safety_review('{event_id}', '{COORDINATOR}');")
            self.wait_for(gate_app, "wait_event_type='Lock'", gate, "a wait on the event lock")
            writer_code, writer_error = self.finish(writer)
            gate_code, gate_error = self.finish(gate)
        finally:
            for process in (writer, gate):
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=5)

        self.assert_no_deadlock(gate_error, writer_error)
        self.assertEqual(writer_code, 0, writer_error)
        self.assertNotEqual(gate_code, 0)
        self.assertIn("P0005", gate_error)
        self.assertIn('"required": 3, "reserved": 0', gate_error)
        self.assertEqual(self.sql(f"SELECT status FROM public.event_requests WHERE id='{event_id}';"), "Planning")
        self.assertEqual(
            self.sql(f"SELECT count(*) FROM public.event_request_status_history WHERE event_request_id='{event_id}' AND new_status='Safety Review';"),
            "0",
        )

    # AC3-X3 (cross-cutting): when the gate goes first, a writer touching the event waits for it and then
    # completes; no deadlock, and the handover is recorded once
    def test_writer_waits_for_handover_then_completes(self):
        event_id = self.planning_event()
        writer_app, gate_app = f"race-writer-{event_id}", f"race-gate-{event_id}"
        gate = self.start(gate_app, f"""
            BEGIN;
            SELECT status FROM public.send_event_request_for_safety_review('{event_id}', '{COORDINATOR}');
            SELECT pg_sleep(1.5);
            COMMIT;
        """)
        writer = None
        try:
            self.wait_for(gate_app, "wait_event='PgSleep'", gate, "its event lock")
            writer = self.start(writer_app, f"{self.requirement_insert(event_id)};")
            self.wait_for(writer_app, "wait_event_type='Lock'", writer, "a wait on the event lock")
            gate_code, gate_error = self.finish(gate)
            writer_code, writer_error = self.finish(writer)
        finally:
            for process in (gate, writer):
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=5)

        self.assert_no_deadlock(gate_error, writer_error)
        self.assertEqual(gate_code, 0, gate_error)
        self.assertEqual(writer_code, 0, writer_error)
        # The requirement landed after the handover; SCRUM-60's approval re-check is what catches it.
        self.assertEqual(self.sql(f"SELECT status FROM public.event_requests WHERE id='{event_id}';"), "Safety Review")
        self.assertEqual(self.sql(f"SELECT count(*) FROM public.equipment_requirements WHERE event_request_id='{event_id}';"), "1")
        self.assertEqual(
            self.sql(f"SELECT count(*) FROM public.event_request_status_history WHERE event_request_id='{event_id}' AND new_status='Safety Review';"),
            "1",
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", default="psql")
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in ("127.0.0.1", "localhost", "::1"):
        parser.error("Only a disposable local database is allowed; fixtures are committed")
    DSN, PSQL = args.dsn, args.psql
    unittest.main(argv=["test_safety_review_concurrency"], verbosity=2)
