"""Three native date/membership schedules; committed fixtures require an owned local DB.

Uses the production date/creation/venue-decision RPCs and pg_blocking_pids barriers.
No mocked mutation or sleep-based scheduling; never run against shared Supabase.
"""

import argparse
import json
import sys
import time
import unittest
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4


class DateConcurrency(unittest.TestCase):
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
        tables = ["event_requests", "event_change_requests", "event_request_status_history", "event_coordinator_assignments", "venue_booking_requests", "venue_booking_refusals", "venue_blocks", "venues", "venue_timing_changes", "equipment", "equipment_requirements", "equipment_reservations", "event_registrations", "event_registration_reviews", "arrangement_reviews", "event_request_outbox", "notifications"]
        pairs = [f"'{table}',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.{table} x)" for table in tables]
        pairs.append("'jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY review_id),'[]') FROM public.arrangement_review_notification_outbox x)")
        return json.loads(self.observer.sql("SELECT jsonb_build_object(" + ",".join(pairs) + ")"))

    def fixture(self):
        v = {name: str(uuid4()) for name in ("event", "other_event", "venue", "new_venue", "booking", "created", "competing")}
        v["owner"] = self.observer.sql("SELECT id FROM auth.users ORDER BY id LIMIT 1")
        self.assertTrue(v["owner"], "SETUP: disposable Auth fixture required")
        self.observer.sql(f"""
        INSERT INTO public.event_requests(id,organiser_id,event_name,status,expected_attendance,proposed_date_times)
        VALUES('{v['event']}','{v['owner']}','VERIFY35 date race','Planning',25,ARRAY[((current_date+30)::text||'T10:00:00+08:00')::timestamptz]),
              ('{v['other_event']}','{v['owner']}','VERIFY35 competing venue event','Planning',25,'{{}}');
        INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
        VALUES('{v['event']}','{v['owner']}','verify35');
        INSERT INTO public.venues(id,name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
        VALUES('{v['venue']}','VERIFY35 original race venue','Test wing',100,'{{}}','{{}}','{{theatre}}','{{AM,PM,NIGHT}}'),
              ('{v['new_venue']}','VERIFY35 unknown race venue','Test wing',100,'{{}}','{{}}','{{theatre}}','{{AM,PM,NIGHT}}');
        INSERT INTO public.venue_booking_requests(id,venue_id,requested_by,event_request_id,start_date,end_date,start_minute,end_minute,status,decided_by,decided_at)
        VALUES('{v['booking']}','{v['venue']}','{v['owner']}','{v['event']}',current_date+30,current_date+30,600,690,'approved','{v['owner']}',now());
        """)
        v["version"] = self.observer.sql(f"SELECT updated_at FROM public.event_requests WHERE id='{v['event']}'")
        v["change"] = self.observer.sql(f"SELECT id FROM public.create_event_change_request('{v['event']}','{v['owner']}','Move the activity two days',jsonb_build_object('proposed_date_times',jsonb_build_array((current_date+32)::text||'T10:00:00+08:00')))")
        v["old_day"] = self.observer.sql("SELECT (current_date+30)::text")
        v["new_day"] = self.observer.sql("SELECT (current_date+32)::text")
        return v

    @staticmethod
    def rpc(v):
        return f"public.approve_date_event_change_request('{v['event']}','{v['change']}','{v['owner']}',NULL,NULL)"

    @staticmethod
    def creator(v):
        data = {"id": v["created"], "venue_id": v["new_venue"], "event_request_id": v["event"], "requested_by": v["owner"], "status": "pending", "start_date": v["old_day"], "end_date": v["old_day"], "start_minute": 900, "end_minute": 1020}
        return "public.create_event_venue_booking_request('" + json.dumps(data) + f"'::jsonb,'{v['version']}'::timestamptz)"

    @staticmethod
    def expect_refusal(expression, code):
        return f"""DO $$ BEGIN
          BEGIN
            PERFORM {expression};
            RAISE EXCEPTION 'Unexpected successful concurrent mutation' USING ERRCODE='P9999';
          EXCEPTION WHEN SQLSTATE '{code}' THEN NULL;
          END;
        END $$; SELECT 'refused_{code}'"""

    def witness(self, waiter, blocker, label):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.observer.sql(f"SELECT {blocker.pid}=ANY(pg_blocking_pids({waiter.pid}))") == "t":
                print(f"{label} native lock witness blocker={blocker.pid} waiter={waiter.pid}", flush=True)
                return
            time.sleep(0.02)
        self.fail(f"{label}: required actual row-lock wait not observed")

    # AC3-X27 (cross-cutting): a newly committed booking at a previously unknown venue forces membership refusal after the date caller's venue wait, without late-locking that venue or writing a partial plan.
    def test_new_venue_creator_wins_and_date_membership_drift_refuses(self):
        v = self.fixture()
        blocker, date, creator = self.session(), self.session(), self.session()
        blocker.sql(f"BEGIN; SELECT id FROM public.venues WHERE id='{v['venue']}' FOR UPDATE")
        date.sql("BEGIN; SET LOCAL ROLE service_role")
        marker = date.start(self.expect_refusal(self.rpc(v), "P0004"))
        self.witness(date, blocker, "AC3-X27")
        creator.sql("BEGIN; SET LOCAL ROLE service_role")
        created = json.loads(creator.sql(f"SELECT to_jsonb(x) FROM {self.creator(v)} x"))
        self.assertEqual((created["id"], created["venue_id"], created["event_request_id"], created["status"]), (v["created"], v["new_venue"], v["event"], "pending"))
        creator.sql("COMMIT")
        after_creator = self.snapshot()
        blocker.sql("COMMIT")
        result, error = date.finish(marker)
        self.assertFalse(error, error)
        self.assertIn("refused_P0004", result)
        date.sql("COMMIT")
        self.assertEqual(self.snapshot(), after_creator, "AC3-X27: refused date call changed protected state")
        proposal = next(row for row in after_creator["event_change_requests"] if row["id"] == v["change"])
        self.assertEqual(proposal["status"], "Pending")
        self.assertIsNone(proposal["applied_booking_plan"])

    # AC3-X28 (cross-cutting): a creator waiting behind committed date approval rechecks its old event version and refuses without inserting an old-date booking.
    def test_date_wins_and_waiting_creator_rechecks_version(self):
        v = self.fixture()
        date, creator = self.session(), self.session()
        date.sql("BEGIN; SET LOCAL ROLE service_role")
        saved = json.loads(date.sql(f"SELECT to_jsonb(x) FROM {self.rpc(v)} x"))
        self.assertEqual(saved["status"], "Approved")
        self.assertEqual(saved["applied_booking_plan"], [{"booking_id": v["booking"], "start_date": v["new_day"], "end_date": v["new_day"], "start_minute": 600, "end_minute": 690}])
        creator.sql("BEGIN; SET LOCAL ROLE service_role")
        marker = creator.start(self.expect_refusal(self.creator(v), "P0004"))
        self.witness(creator, date, "AC3-X28")
        date.sql("COMMIT")
        after_date = self.snapshot()
        result, error = creator.finish(marker)
        self.assertFalse(error, error)
        self.assertIn("refused_P0004", result)
        creator.sql("COMMIT")
        self.assertEqual(self.snapshot(), after_date, "AC3-X28: stale creator changed protected state")
        self.assertFalse(any(row["id"] == v["created"] for row in after_date["venue_booking_requests"]))
        moved = next(row for row in after_date["venue_booking_requests"] if row["id"] == v["booking"])
        self.assertEqual((moved["start_date"], moved["end_date"], moved["start_minute"], moved["end_minute"], moved["status"]), (v["new_day"], v["new_day"], 600, 690, "approved"))
        self.assertEqual(len([row for row in after_date["event_registration_reviews"] if row["event_request_id"] == v["event"]]), 1)
        flags = [row for row in after_date["arrangement_reviews"] if row["event_request_id"] == v["event"]]
        self.assertEqual(len(flags), 1)
        self.assertEqual((flags[0]["arrangement"], flags[0]["arrangement_id"], flags[0]["changed_fields"]), ("venue_booking", v["booking"], ["proposed_date_times"]))
        self.assertEqual([row["review_id"] for row in after_date["jobs"] if row["event_request_id"] == v["event"]], [flags[0]["id"]])

    # AC4-X6 (cross-cutting): a real competing venue approval wins the venue lock, so the date caller observes its newly committed collision and refuses the entire transaction.
    def test_competing_venue_approval_wins_and_date_rechecks_guard(self):
        v = self.fixture()
        self.observer.sql(f"""INSERT INTO public.venue_booking_requests(id,venue_id,requested_by,event_request_id,start_date,end_date,start_minute,end_minute)
         VALUES('{v['competing']}','{v['venue']}','{v['owner']}','{v['other_event']}',current_date+32,current_date+32,600,690)""")
        approver, date = self.session(), self.session()
        approver.sql("BEGIN; SET LOCAL ROLE service_role")
        outcome = json.loads(approver.sql(f"SELECT public.decide_venue_booking_request('{v['competing']}','approved','{v['owner']}')"))
        self.assertEqual(outcome["outcome"], "approved")
        date.sql("BEGIN; SET LOCAL ROLE service_role")
        marker = date.start(self.expect_refusal(self.rpc(v), "P0005"))
        self.witness(date, approver, "AC4-X6")
        approver.sql("COMMIT")
        after_approval = self.snapshot()
        result, error = date.finish(marker)
        self.assertFalse(error, error)
        self.assertIn("refused_P0005", result)
        date.sql("COMMIT")
        self.assertEqual(self.snapshot(), after_approval, "AC4-X6: conflicting date approval left partial plan/audit/reviews/jobs")
        original = next(row for row in after_approval["venue_booking_requests"] if row["id"] == v["booking"])
        self.assertEqual(original["start_date"], v["old_day"])
        proposal = next(row for row in after_approval["event_change_requests"] if row["id"] == v["change"])
        self.assertEqual(proposal["status"], "Pending")
        self.assertIsNone(proposal["applied_booking_plan"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", default="psql")
    parser.add_argument("--disposable", action="store_true")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    parsed = urlparse(args.dsn)
    if not args.disposable or parsed.scheme not in ("postgres", "postgresql") or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or not parsed.path.removeprefix("/").startswith("scrum48_"):
        parser.error("Requires explicit disposable loopback scrum48_* database; fixtures commit")
    sys.path.insert(0, str(args.repo / "database" / "tests"))
    from test_arrangement_review_lock_compatibility import Session

    DSN, PSQL = args.dsn, args.psql
    unittest.main(argv=["test_date_change_concurrency"], verbosity=2)
