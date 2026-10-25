"""Opt-in SCRUM-40 manual/automatic completion race on an owned disposable DB.

Fixtures commit only in loopback scrum48_* databases. Never target shared Supabase.
"""

import argparse
import json
import time
import unittest
from urllib.parse import urlparse
from uuid import uuid4

from test_arrangement_review_lock_compatibility import Session


class CompletionConcurrency(unittest.TestCase):
    def setUp(self):
        self.sessions = []
        self.observer = self.session()

    def tearDown(self):
        for session in reversed(self.sessions):
            session.close()

    def session(self):
        result = Session(DSN, PSQL)
        self.sessions.append(result)
        return result

    def snapshot(self):
        tables = [
            "event_requests",
            "event_request_status_history",
            "event_coordinator_assignments",
            "event_change_requests",
            "venue_booking_requests",
            "equipment",
            "equipment_status_history",
            "equipment_requirements",
            "equipment_reservations",
            "event_registrations",
            "event_registration_reviews",
            "arrangement_reviews",
            "event_request_outbox",
            "notifications",
        ]
        pairs = [
            f"'{table}',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.{table} x)"
            for table in tables
        ]
        pairs.append(
            "'jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY review_id),'[]') FROM public.arrangement_review_notification_outbox x)"
        )
        return json.loads(
            self.observer.sql("SELECT jsonb_build_object(" + ",".join(pairs) + ")")
        )

    # AC7-X1 (cross-cutting): either manual or automatic completion can win, but the real blocked loser cannot rewrite the event or add history.
    def test_manual_and_automatic_completion_have_one_winner(self):
        owner = self.observer.sql("SELECT id FROM auth.users ORDER BY id LIMIT 1")
        self.assertTrue(owner, "SETUP: disposable Auth identity required")
        for automatic_wins in (True, False):
            with self.subTest(automatic_wins=automatic_wins):
                event, coordinator = str(uuid4()), str(uuid4())
                self.observer.sql(f"""
                  INSERT INTO public.event_requests(id,organiser_id,event_name,status,final_event_end_at)
                  VALUES('{event}','{owner}','VERIFY40 completion race','Confirmed','2026-10-01T00:00:00Z');
                  INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
                  VALUES('{event}','{coordinator}','verify40');
                """)
                before = self.snapshot()
                automatic = f"public.complete_overdue_event_request('{event}','2026-10-23T04:00:00Z')"
                manual = f"public.advance_event_request_by_coordinator('{event}','{coordinator}','Completed')"
                winner, loser = self.session(), self.session()
                winner.sql("BEGIN; SET LOCAL ROLE service_role")
                if automatic_wins:
                    self.assertEqual(winner.sql(f"SELECT {automatic}"), "t")
                else:
                    saved = json.loads(
                        winner.sql(f"SELECT to_jsonb(x) FROM {manual} x")
                    )
                    self.assertEqual(saved["status"], "Completed")
                loser.sql("BEGIN; SET LOCAL ROLE service_role")
                if automatic_wins:
                    statement = f"""DO $$ BEGIN
                      BEGIN
                        PERFORM {manual};
                        RAISE EXCEPTION 'AC7-X1: losing manual completion succeeded' USING ERRCODE='P9940';
                      EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
                      END;
                    END $$; SELECT 'manual_refused_P0004'"""
                else:
                    statement = f"SELECT {automatic}"
                marker = loser.start(statement)
                deadline = time.monotonic() + 4
                blocked = False
                while time.monotonic() < deadline:
                    if (
                        self.observer.sql(
                            f"SELECT {winner.pid}=ANY(pg_blocking_pids({loser.pid}))"
                        )
                        == "t"
                    ):
                        blocked = True
                        break
                    time.sleep(0.02)
                self.assertTrue(blocked, "No actual event-lock wait observed")
                print(
                    f"AC7-X1 lock witness automatic_wins={automatic_wins} winner={winner.pid} loser={loser.pid}",
                    flush=True,
                )
                winner.sql("COMMIT")
                after_winner = self.snapshot()
                output, error = loser.finish(marker)
                self.assertFalse(error, error)
                self.assertIn("manual_refused_P0004" if automatic_wins else "f", output)
                loser.sql("COMMIT")
                self.assertEqual(
                    self.snapshot(), after_winner, "Losing call changed protected state"
                )
                old = next(
                    row for row in before["event_requests"] if row["id"] == event
                )
                new = next(
                    row for row in after_winner["event_requests"] if row["id"] == event
                )
                self.assertEqual(
                    new, {**old, "status": "Completed", "updated_at": new["updated_at"]}
                )
                self.assertGreater(new["updated_at"], old["updated_at"])
                for table in before:
                    if table not in {"event_requests", "event_request_status_history"}:
                        self.assertEqual(before[table], after_winner[table], table)
                old_history = before["event_request_status_history"]
                new_history = after_winner["event_request_status_history"]
                self.assertEqual(len(new_history), len(old_history) + 1)
                for entry in old_history:
                    self.assertIn(entry, new_history)
                transitions = [
                    row
                    for row in new_history
                    if row["event_request_id"] == event
                    and row["new_status"] == "Completed"
                ]
                self.assertEqual(len(transitions), 1)
                saved = transitions[0]
                self.assertEqual(
                    (saved["previous_status"], saved["entry_kind"]),
                    ("Confirmed", "transition"),
                )
                self.assertEqual(
                    (saved["actor_id"], saved["actor_role"], saved["source"]),
                    (None, "system", "event_request.auto_completed")
                    if automatic_wins
                    else (coordinator, "event_coordinator", "coordinator.completion"),
                )
                self.assertTrue(saved["occurred_at"])
                self.assertEqual(
                    [row for row in before["event_requests"] if row["id"] != event],
                    [
                        row
                        for row in after_winner["event_requests"]
                        if row["id"] != event
                    ],
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", default="psql")
    parser.add_argument("--disposable", action="store_true")
    args = parser.parse_args()
    parsed = urlparse(args.dsn)
    if (
        not args.disposable
        or parsed.scheme not in ("postgres", "postgresql")
        or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
        or not parsed.path.removeprefix("/").startswith("scrum48_")
    ):
        parser.error(
            "Requires explicit disposable loopback scrum48_* database; fixtures commit"
        )
    DSN, PSQL = args.dsn, args.psql
    unittest.main(argv=["test_event_auto_completion_concurrency"], verbosity=2)
