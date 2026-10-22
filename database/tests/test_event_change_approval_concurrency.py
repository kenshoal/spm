"""Opt-in native duplicate approval: commits fixtures only in an owned disposable DB.

Uses two actual service-role RPC sessions and an independent PostgreSQL lock witness.
The owning test database must be removed afterwards; never use shared Supabase.
"""

import argparse
import json
import time
import unittest
from urllib.parse import urlparse
from uuid import uuid4

from test_arrangement_review_lock_compatibility import Session


class ApprovalConcurrency(unittest.TestCase):
    def setUp(self):
        self.sessions = []
        self.observer = self.session()

    def tearDown(self):
        for session in reversed(self.sessions):
            session.close()

    def session(self):
        session = Session(DSN, PSQL)
        self.sessions.append(session)
        return session

    def snapshot(self):
        tables = ["event_requests", "event_request_status_history", "event_change_requests", "event_coordinator_assignments", "venue_booking_requests", "equipment", "equipment_requirements", "equipment_reservations", "notifications", "event_request_outbox", "arrangement_reviews"]
        pairs = [f"'{table}',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.{table} x)" for table in tables]
        pairs.append("'jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY review_id),'[]') FROM public.arrangement_review_notification_outbox x)")
        return json.loads(self.observer.sql("SELECT jsonb_build_object(" + ",".join(pairs) + ")"))

    # AC3-X5 (cross-cutting): a concurrent duplicate waits on the same event, then refuses without a second plan application, audit, flag or job.
    def test_duplicate_approval_serialises_and_has_no_second_effect(self):
        v = {name: str(uuid4()) for name in ("event", "venue", "booking", "equipment", "requirement", "reservation", "coordinator")}
        v["owner"] = self.observer.sql("SELECT id FROM auth.users ORDER BY id LIMIT 1")
        self.assertTrue(v["owner"], "SETUP: disposable Auth identity required")
        self.observer.sql(f"""
        INSERT INTO public.event_requests(id,organiser_id,event_name,status,expected_attendance,venue_requirements,equipment_requirements)
        VALUES('{v['event']}','{v['owner']}','VERIFY35 concurrent approval','Planning',25,'Seminar room','Microphone');
        INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
        VALUES('{v['event']}','{v['coordinator']}','verify');
        INSERT INTO public.venues(id,name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
        VALUES('{v['venue']}','VERIFY35 concurrent venue','Test wing',100,'{{}}','{{}}','{{theatre}}','{{AM}}');
        INSERT INTO public.venue_booking_requests(id,venue_id,requested_by,event_request_id,start_date,end_date,slots,status,decided_by,decided_at)
        VALUES('{v['booking']}','{v['venue']}','{v['owner']}','{v['event']}',current_date+30,current_date+30,'{{AM}}','approved','{v['owner']}',now());
        INSERT INTO public.equipment(id,type,total_owned_quantity,home_location,created_by)
        VALUES('{v['equipment']}','VERIFY35 concurrent microphone',10,'Test store','{v['owner']}');
        INSERT INTO public.equipment_requirements(id,event_request_id,equipment_type,quantity,recorded_by)
        VALUES('{v['requirement']}','{v['event']}','VERIFY35 concurrent microphone',2,'{v['owner']}');
        INSERT INTO public.equipment_reservations(id,equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
        VALUES('{v['reservation']}','{v['equipment']}','{v['requirement']}','{v['event']}',1,current_date+30,current_date+30,'{v['owner']}');
        """)
        v["change"] = self.observer.sql(f"SELECT id FROM public.create_event_change_request('{v['event']}','{v['owner']}','Concurrent non-date approval','{{\"expected_attendance\":80}}')")
        before = self.snapshot()
        winner, duplicate = self.session(), self.session()
        self.assertEqual(len({winner.pid, duplicate.pid, self.observer.pid}), 3)
        rpc = f"public.approve_non_date_event_change_request('{v['event']}','{v['change']}','{v['coordinator']}',NULL)"
        winner.sql("BEGIN; SET LOCAL ROLE service_role")
        saved = json.loads(winner.sql(f"SELECT to_jsonb(x) FROM {rpc} x"))
        self.assertEqual(saved["status"], "Approved")
        self.assertEqual(saved["coordinator_id"], v["coordinator"])
        self.assertTrue(saved["decided_at"])
        duplicate.sql("BEGIN; SET LOCAL ROLE service_role")
        marker = duplicate.start(f"""DO $$ BEGIN
          BEGIN
            PERFORM {rpc};
            RAISE EXCEPTION 'AC3-X5: duplicate approval succeeded' USING ERRCODE='P9904';
          EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL;
          END;
        END $$; SELECT 'duplicate_refused_P0004'""")
        deadline = time.monotonic() + 4
        blocked = False
        while time.monotonic() < deadline:
            if self.observer.sql(f"SELECT {winner.pid}=ANY(pg_blocking_pids({duplicate.pid}))") == "t":
                blocked = True
                break
            time.sleep(0.02)
        self.assertTrue(blocked, "No actual event-lock wait observed for competing duplicate")
        print(f"AC3-X5 lock witness winner={winner.pid} duplicate={duplicate.pid}", flush=True)
        winner.sql("COMMIT")
        after_winner = self.snapshot()
        output, error = duplicate.finish(marker)
        self.assertFalse(error, error)
        self.assertIn("duplicate_refused_P0004", output)
        duplicate.sql("COMMIT")
        self.assertEqual(self.snapshot(), after_winner, "Losing call changed protected state")
        for table in before:
            if table not in ("event_requests", "event_change_requests", "arrangement_reviews", "jobs"):
                self.assertEqual(after_winner[table], before[table], table)
        event = next(row for row in after_winner["event_requests"] if row["id"] == v["event"])
        old_event = next(row for row in before["event_requests"] if row["id"] == v["event"])
        self.assertEqual(event, {**old_event, "expected_attendance": 80, "updated_at": event["updated_at"]})
        self.assertNotEqual(event["updated_at"], old_event["updated_at"])
        reviews = [row for row in after_winner["arrangement_reviews"] if row["event_request_id"] == v["event"]]
        self.assertEqual({(row["arrangement"], row["arrangement_id"]) for row in reviews}, {("venue_booking", v["booking"]), ("equipment_reservation", v["reservation"])})
        self.assertEqual(len(reviews), 2)
        self.assertEqual(len({row["trigger_id"] for row in reviews}), 1)
        self.assertTrue(all(row["changed_fields"] == ["expected_attendance"] for row in reviews))
        jobs = [row for row in after_winner["jobs"] if row["event_request_id"] == v["event"]]
        self.assertEqual({row["review_id"] for row in jobs}, {row["id"] for row in reviews})
        self.assertEqual(len(jobs), 2)
        print("AC3-X5 PASS: one saved approval, one P0004, two flags/jobs and no losing-call writes", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", default="psql")
    parser.add_argument("--disposable", action="store_true")
    args = parser.parse_args()
    parsed = urlparse(args.dsn)
    if not args.disposable or parsed.scheme not in ("postgres", "postgresql") or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or not parsed.path.removeprefix("/").startswith("scrum48_"):
        parser.error("Requires explicit disposable loopback scrum48_* database; fixtures commit")
    DSN, PSQL = args.dsn, args.psql
    unittest.main(argv=["test_event_change_approval_concurrency"], verbosity=2)
