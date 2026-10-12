"""Local-only committed-fixture test: use a disposable PostgreSQL database, never shared Supabase."""
import argparse
import subprocess
import time
import unittest
from urllib.parse import urlparse
from uuid import uuid4


class ConcurrentHistoryTest(unittest.TestCase):
    def sql(self, query):
        result = subprocess.run(
            [PSQL, '-X', '-At', '-v', 'ON_ERROR_STOP=1', '-d', DSN, '-c', query],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    # AC1-X1 (cross-cutting): racing duplicate transitions produce one success, one P0004 and one new history row
    def test_duplicate_transition_is_atomic(self):
        event_id = str(uuid4())
        self.sql(f"""
            INSERT INTO public.event_requests(id,organiser_id,status)
            SELECT '{event_id}',id,'Submitted' FROM auth.users ORDER BY created_at LIMIT 1;
            INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
            VALUES('{event_id}','race-coordinator','race-manager');
        """)
        application = f'scrum48-race-{event_id}'
        first = subprocess.Popen(
            [PSQL, '-X', '-At', '-v', 'ON_ERROR_STOP=1', '-d', DSN, '-c', f"""
                SET application_name='{application}'; BEGIN;
                SELECT public.advance_event_request_by_coordinator('{event_id}','race-coordinator','Under Review');
                SELECT pg_sleep(1.5); COMMIT;
            """], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            # Wait until the first transaction holds the event lock, not an arbitrary delay.
            deadline = time.monotonic() + 5
            while self.sql(f"SELECT count(*) FROM pg_stat_activity WHERE application_name='{application}' AND wait_event='PgSleep';") != '1':
                self.assertIsNone(first.poll(), 'First transaction ended before holding the lock')
                self.assertLess(time.monotonic(), deadline, 'First transaction never reached its lock hold')
                time.sleep(0.02)
            second = subprocess.run(
                [PSQL, '-X', '-At', '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose', '-d', DSN, '-c', f"""
                    SELECT public.advance_event_request_by_coordinator('{event_id}','race-coordinator','Under Review');
                """], capture_output=True, text=True, timeout=10,
            )
            _, error = first.communicate(timeout=10)
            self.assertEqual(first.returncode, 0, error)
            self.assertIn(second.returncode, (1, 3), second.stderr)
            self.assertIn('P0004', second.stderr)
            self.assertEqual(self.sql(f"SELECT status FROM public.event_requests WHERE id='{event_id}';"), 'Under Review')
            self.assertEqual(self.sql(f"SELECT count(*) FROM public.event_request_status_history WHERE event_request_id='{event_id}';"), '2')
            self.assertEqual(self.sql(f"""
                SELECT previous_status || '|' || new_status || '|' || actor_id
                FROM public.event_request_status_history WHERE event_request_id='{event_id}' ORDER BY id DESC LIMIT 1;
            """), 'Submitted|Under Review|race-coordinator')
        finally:
            if first.poll() is None:
                first.terminate()
                first.communicate(timeout=5)
        # Retained-event evidence is immutable; discard this entire disposable cluster after verification.


    # AC1-X2 (cross-cutting): distinct concurrent actions serialize into an unbroken current-state history chain
    def test_distinct_transitions_keep_previous_status_chain(self):
        event_id = str(uuid4())
        self.sql(f"""
            INSERT INTO public.event_requests(id,organiser_id,status)
            SELECT '{event_id}',id,'Submitted' FROM auth.users ORDER BY created_at LIMIT 1;
            INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
            VALUES('{event_id}','race-coordinator','race-manager');
        """)
        application = f'scrum48-chain-{event_id}'
        first = subprocess.Popen(
            [PSQL, '-X', '-At', '-v', 'ON_ERROR_STOP=1', '-d', DSN, '-c', f"""
                SET application_name='{application}'; BEGIN;
                SELECT public.advance_event_request_by_coordinator('{event_id}','race-coordinator','Under Review');
                SELECT pg_sleep(1.5); COMMIT;
            """], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            deadline = time.monotonic() + 5
            while self.sql(f"SELECT count(*) FROM pg_stat_activity WHERE application_name='{application}' AND wait_event='PgSleep';") != '1':
                self.assertIsNone(first.poll(), 'First transaction ended before holding the lock')
                self.assertLess(time.monotonic(), deadline, 'First transaction never reached its lock hold')
                time.sleep(0.02)
            second = subprocess.run(
                [PSQL, '-X', '-At', '-v', 'ON_ERROR_STOP=1', '-d', DSN, '-c', f"""
                    SELECT public.advance_event_request_by_coordinator('{event_id}','race-coordinator','Cancelled');
                """], capture_output=True, text=True, timeout=10,
            )
            _, error = first.communicate(timeout=10)
            self.assertEqual(first.returncode, 0, error)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(self.sql(f"SELECT status FROM public.event_requests WHERE id='{event_id}';"), 'Cancelled')
            self.assertEqual(self.sql(f"SELECT count(*) FROM public.event_request_status_history WHERE event_request_id='{event_id}';"), '3')
            self.assertEqual(self.sql(f"""
                SELECT previous_status || '|' || new_status || '|' || actor_id || '|' || actor_role
                FROM public.event_request_status_history WHERE event_request_id='{event_id}' AND entry_kind='transition' ORDER BY occurred_at,id;
            """), 'Submitted|Under Review|race-coordinator|event_coordinator\nUnder Review|Cancelled|race-coordinator|event_coordinator')
            self.assertEqual(self.sql(f"""
                SELECT count(*) FROM (
                    SELECT occurred_at, lag(occurred_at) OVER (ORDER BY id) AS previous_time
                    FROM public.event_request_status_history WHERE event_request_id='{event_id}'
                ) ordered WHERE occurred_at<=previous_time;
            """), '0')
        finally:
            if first.poll() is None:
                first.terminate()
                first.communicate(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn', required=True)
    parser.add_argument('--psql', default='psql')
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in ('127.0.0.1', 'localhost', '::1'):
        parser.error('Only a disposable local database is allowed; fixtures are committed')
    DSN, PSQL = args.dsn, args.psql
    unittest.main(argv=['test_event_status_history_concurrency'], verbosity=2)
