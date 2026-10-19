"""Committed fixtures: explicit disposable PostgreSQL only; never shared Supabase.

Exercises native event-only protocol compatibility, not an HTTP safety workflow or
Tate's readiness verdict. The child-first review INSERT is a protocol fixture.
"""

import argparse
import json
import queue
import subprocess
import threading
import time
import unittest
from urllib.parse import urlparse
from uuid import uuid4


class Session:
    """One persistent real psql/backend session, with observable statement barriers."""

    def __init__(self, dsn, psql):
        self.process = subprocess.Popen(
            [psql, "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose", "-d", dsn],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        self.lines = queue.Queue()
        self.errors = []
        self.stdout = threading.Thread(target=self._read_output, daemon=True)
        self.stderr = threading.Thread(target=self._read_errors, daemon=True)
        self.stdout.start()
        self.stderr.start()
        self.pid = int(self.sql("SELECT pg_backend_pid()"))
        self.sql("SET statement_timeout='15s'; SET lock_timeout='12s'; SET deadlock_timeout='2s'")

    def _read_output(self):
        for line in self.process.stdout:
            self.lines.put(line.rstrip("\n"))
        self.lines.put(None)

    def _read_errors(self):
        self.errors.extend(self.process.stderr)

    def start(self, statement):
        marker = "barrier_" + uuid4().hex
        self.process.stdin.write(statement.rstrip("; \n") + f";\nSELECT '{marker}';\n")
        self.process.stdin.flush()
        return marker

    def finish(self, marker, timeout=18):
        result = []
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError("Native statement did not reach its bounded barrier")
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty as error:
                raise AssertionError("Native statement barrier timed out") from error
            if line == marker:
                return "\n".join(result), ""
            if line is None:
                self.process.wait(timeout=2)
                self.stderr.join(timeout=2)
                return "\n".join(result), "".join(self.errors)
            result.append(line)

    def sql(self, statement):
        value, error = self.finish(self.start(statement))
        if error:
            raise AssertionError("Native SQL failed: " + error)
        return value

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write("ROLLBACK;\n\\q\n")
                self.process.stdin.flush()
                self.process.wait(timeout=3)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.process.terminate()
                self.process.wait(timeout=3)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()


class ArrangementReviewLocks(unittest.TestCase):
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

    def fixture(self):
        values = {key: str(uuid4()) for key in ("event", "venue", "booking", "equipment", "requirement", "reservation", "cause", "writer_cause")}
        values["actor"] = self.observer.sql("SELECT id FROM auth.users ORDER BY id LIMIT1".replace("LIMIT1", "LIMIT 1"))
        self.assertTrue(values["actor"], "setup: disposable identity missing")
        v = values
        self.observer.sql(f"""
        INSERT INTO public.event_requests(id,organiser_id,event_name,status)
        VALUES('{v['event']}','{v['actor']}','VERIFY SCRUM64 event lock compatibility','Planning');
        INSERT INTO public.venues(id,name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
        VALUES('{v['venue']}','SCRUM64 lock fixture','Test wing',100,'{{}}','{{}}','{{theatre}}','{{AM}}');
        INSERT INTO public.venue_booking_requests(id,venue_id,requested_by,event_request_id,start_date,end_date,slots,status,decided_by,decided_at)
        VALUES('{v['booking']}','{v['venue']}','{v['actor']}','{v['event']}',current_date+30,current_date+30,'{{AM}}','approved','{v['actor']}',now());
        INSERT INTO public.equipment(id,type,total_owned_quantity,home_location,created_by)
        VALUES('{v['equipment']}','SCRUM64 lock microphone',10,'Test store','{v['actor']}');
        INSERT INTO public.equipment_requirements(id,event_request_id,equipment_type,quantity,recorded_by)
        VALUES('{v['requirement']}','{v['event']}','SCRUM64 lock microphone',1,'{v['actor']}');
        INSERT INTO public.equipment_reservations(id,equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by)
        VALUES('{v['reservation']}','{v['equipment']}','{v['requirement']}','{v['event']}',1,current_date+29,current_date+30,'{v['actor']}');
        """)
        return v

    def protected(self):
        tables = ["event_requests", "event_request_status_history", "venue_booking_requests", "equipment_reservations", "equipment_requirements", "equipment", "equipment_status_history", "notifications", "event_request_outbox"]
        pairs = [f"'{table}',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.{table} x)" for table in tables]
        return json.loads(self.observer.sql("SELECT jsonb_build_object(" + ",".join(pairs) + ")"))

    @staticmethod
    def helper(v, domain="equipment_reservation"):
        target = v["booking" if domain == "venue_booking" else "reservation"]
        targets = json.dumps([{"arrangement": domain, "id": target}])
        return f"SELECT private.raise_safety_arrangement_reviews('{v['event']}','{v['cause']}','{targets}'::jsonb,'Specific protocol recheck')"

    @staticmethod
    def event_lock(v):
        return f"SELECT id FROM public.event_requests WHERE id='{v['event']}' FOR UPDATE"

    @staticmethod
    def reader(v):
        return f"SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') FROM public.get_outstanding_arrangement_reviews('{v['event']}') x"

    def blocked(self, waiter, blocker, timeout=1.5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.observer.sql(f"SELECT {blocker.pid}=ANY(pg_blocking_pids({waiter.pid}))") == "t":
                print(f"native blocking witness waiter={waiter.pid} blocker={blocker.pid}", flush=True)
                return True
            if waiter.process.poll() is not None:
                return False
            time.sleep(0.02)
        return False

    def assert_flag(self, row, v, *, domain="equipment_reservation", cause=None, reason="Specific protocol recheck"):
        target = v["booking" if domain == "venue_booking" else "reservation"]
        self.assertEqual(row["event_request_id"], v["event"])
        self.assertEqual(row["arrangement"], domain)
        self.assertEqual(row["arrangement_id"], target)
        if cause is not None:
            self.assertEqual(row["trigger_id"], cause)
        self.assertEqual(row["reason"], reason)
        self.assertIsNone(row["cleared_at"])
        self.assertIsNone(row["cleared_by"])
        self.assertTrue(row["raised_at"])

    # AC7-X4 (cross-cutting): event-first helper calls must not wait on either child domain and cycle against a real event-FK writer.
    def test_helper_compatible_with_child_first_event_last_protocol(self):
        for domain, table, key in (("venue_booking", "venue_booking_requests", "booking"), ("equipment_reservation", "equipment_reservations", "reservation")):
            with self.subTest(domain=domain):
                v = self.fixture()
                before = self.protected()
                writer, caller = self.session(), self.session()
                self.assertEqual(len({writer.pid, caller.pid, self.observer.pid}), 3)
                writer.sql(f"BEGIN; SELECT id FROM public.{table} WHERE id='{v[key]}' FOR UPDATE")
                caller.sql("BEGIN; " + self.event_lock(v))
                caller_marker = caller.start(self.helper(v, domain))
                # Under old0036 caller waits for writer's child. New event-only body completes while writer retains it.
                child_wait = self.blocked(caller, writer)
                target = v[key]
                writer_marker = writer.start(f"""INSERT INTO public.arrangement_reviews
                (event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason)
                VALUES('{v['event']}','{domain}','{target}','{v['writer_cause']}','event_change','{{}}','Protocol writer cause')""")
                parent_wait = self.blocked(writer, caller)
                print(f"{domain}: caller_child_wait={child_wait}, writer_event_wait={parent_wait}", flush=True)
                self.assertTrue(parent_wait, "setup: protocol writer never reached held event FK")
                _, caller_error = caller.finish(caller_marker)
                if not caller_error:
                    caller.sql("COMMIT")
                _, writer_error = writer.finish(writer_marker)
                if not writer_error:
                    writer.sql("COMMIT")
                self.assertFalse(caller_error or writer_error, "AC7-X4 expected both transactions to commit; actual native errors:\n" + caller_error + writer_error)
                self.assertFalse(child_wait, "AC7-X4: event-first helper waited on a target child")
                rows = json.loads(self.observer.sql(self.reader(v)))
                self.assertEqual(len(rows), 2)
                causes = {row["trigger_id"]: row for row in rows}
                self.assertEqual(set(causes), {v["cause"], v["writer_cause"]})
                self.assert_flag(causes[v["cause"]], v, domain=domain, cause=v["cause"])
                self.assert_flag(causes[v["writer_cause"]], v, domain=domain, cause=v["writer_cause"], reason="Protocol writer cause")
                self.assertEqual(self.observer.sql(f"SELECT count(*) FROM public.arrangement_review_notification_outbox WHERE event_request_id='{v['event']}'"), "2")
                self.assertEqual(self.protected(), before)

    # AC5-X10 (cross-cutting): an event-only shared facts reader waits for an earlier genuine flag transaction and sees its complete committed evidence.
    def test_writer_first_shared_reader_sees_committed_review(self):
        v = self.fixture()
        before = self.protected()
        writer, reader = self.session(), self.session()
        writer.sql("BEGIN; " + self.event_lock(v))
        self.assertEqual(writer.sql(self.helper(v)), "1")
        reader.sql("BEGIN")
        marker = reader.start(self.event_lock(v) + "; " + self.reader(v))
        self.assertTrue(self.blocked(reader, writer, timeout=4), "reader did not wait for earlier flag transaction")
        writer.sql("COMMIT")
        output, error = reader.finish(marker)
        self.assertFalse(error, error)
        rows = json.loads(output.splitlines()[-1])
        self.assertEqual(len(rows), 1)
        self.assert_flag(rows[0], v, cause=v["cause"])
        reader.sql("COMMIT")
        self.assertEqual(self.protected(), before)
        self.assertEqual(self.observer.sql(f"SELECT count(*) FROM public.arrangement_review_notification_outbox WHERE event_request_id='{v['event']}'"), "1")

    # AC5-X11 (cross-cutting): event-first facts reads exclude uncommitted operational review work and the real writer proceeds after release.
    def test_event_first_shared_reader_orders_actual_equipment_writer(self):
        v = self.fixture()
        before = self.protected()
        reader, writer = self.session(), self.session()
        reader.sql("BEGIN; " + self.event_lock(v))
        self.assertEqual(json.loads(reader.sql(self.reader(v))), [])
        writer.sql("BEGIN")
        marker = writer.start(f"SELECT public.transition_equipment_status('{v['equipment']}','DAMAGED','{v['actor']}','Actual operational cause')")
        self.assertTrue(self.blocked(writer, reader, timeout=4), "actual operational writer never waited on held parent FK")
        self.assertEqual(json.loads(reader.sql(self.reader(v))), [])
        reader.sql("COMMIT")
        _, error = writer.finish(marker)
        self.assertFalse(error, error)
        writer.sql("COMMIT")
        rows = json.loads(self.observer.sql(self.reader(v)))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["trigger_type"], "equipment_unavailable")
        self.assertEqual(row["changed_fields"], ["operational_status"])
        self.assertEqual(row["arrangement_id"], v["reservation"])
        self.assertIn("AVAILABLE -> DAMAGED", row["reason"])
        self.assertIn("Actual operational cause", row["reason"])
        self.assertEqual(self.observer.sql(f"SELECT operational_status FROM public.equipment WHERE id='{v['equipment']}'"), "DAMAGED")
        self.assertEqual(self.observer.sql(f"SELECT count(*) FROM public.equipment_status_history WHERE equipment_id='{v['equipment']}' AND old_status='AVAILABLE' AND new_status='DAMAGED' AND changed_by='{v['actor']}' AND review_trigger_id='{row['trigger_id']}'"), "1")
        after = self.protected()
        for table in before:
            if table not in ("equipment", "equipment_status_history"):
                self.assertEqual(after[table], before[table], table)
        for table in ("equipment", "equipment_status_history"):
            self.assertEqual([r for r in after[table] if r.get("equipment_id", r.get("id")) != v["equipment"]], [r for r in before[table] if r.get("equipment_id", r.get("id")) != v["equipment"]])
        self.assertEqual(self.observer.sql(f"SELECT count(*) FROM public.arrangement_review_notification_outbox WHERE event_request_id='{v['event']}'"), "1")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", default="psql")
    parser.add_argument("--disposable", action="store_true")
    args = parser.parse_args()
    parsed = urlparse(args.dsn)
    if not args.disposable or parsed.scheme not in ("postgres", "postgresql") or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or not parsed.path.removeprefix("/").startswith("scrum48_"):
        parser.error("Only an explicitly disposable loopback scrum48_* database is allowed; fixtures commit")
    DSN, PSQL = args.dsn, args.psql
    unittest.main(argv=["test_arrangement_review_lock_compatibility"], verbosity=2)
