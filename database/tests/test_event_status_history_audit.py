"""Rollback-only database audit; run against a disposable loopback fixture, never shared Supabase."""
import argparse
import subprocess
import unittest
from urllib.parse import urlparse


SNAPSHOT = """
SELECT jsonb_build_object(
    'events', (SELECT jsonb_agg(to_jsonb(e) ORDER BY id) FROM public.event_requests e),
    'history', (SELECT jsonb_agg(to_jsonb(h) ORDER BY id) FROM public.event_request_status_history h),
    'decisions', (SELECT jsonb_agg(to_jsonb(d) ORDER BY id) FROM public.event_request_review_decisions d),
    'outbox', (SELECT jsonb_agg(to_jsonb(o) ORDER BY id) FROM public.event_request_outbox o),
    'assignments', (SELECT jsonb_agg(to_jsonb(a) ORDER BY id) FROM public.event_coordinator_assignments a)
)::text;
"""


class HistoryAuditTest(unittest.TestCase):
    def run_sql(self, query, expected_code=None):
        result = subprocess.run(
            [PSQL, '-X', '-At', '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose', '-d', DSN],
            input=query, capture_output=True, text=True, timeout=15,
        )
        if expected_code:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn(f'ERROR:  {expected_code}:', result.stderr)
        else:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    # AC1-N3 (negative): history failure must roll back the already inserted review decision, state and downstream effects
    def test_review_history_failure_rolls_back_entire_workflow(self):
        self.run_sql("""
            BEGIN;
            INSERT INTO public.event_requests(id,organiser_id,status)
            SELECT '48000000-0000-4000-8000-000000000003',id,'Under Review' FROM auth.users LIMIT 1;
            INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
            VALUES('48000000-0000-4000-8000-000000000003','audit-coordinator','audit-manager');
            CREATE FUNCTION pg_temp.fail_history_insert() RETURNS trigger LANGUAGE plpgsql AS $f$
            BEGIN RAISE EXCEPTION 'Injected history storage failure' USING ERRCODE='P9910'; END; $f$;
            CREATE TRIGGER test_fail_history BEFORE INSERT ON public.event_request_status_history
            FOR EACH ROW EXECUTE FUNCTION pg_temp.fail_history_insert();
            DO $d$
            DECLARE before_state jsonb; after_state jsonb;
            BEGIN
                SELECT jsonb_build_object('event',(SELECT to_jsonb(e) FROM public.event_requests e WHERE id='48000000-0000-4000-8000-000000000003'),
                    'history',(SELECT jsonb_agg(to_jsonb(h) ORDER BY id) FROM public.event_request_status_history h),
                    'decisions',(SELECT jsonb_agg(to_jsonb(d) ORDER BY id) FROM public.event_request_review_decisions d),
                    'outbox',(SELECT jsonb_agg(to_jsonb(o) ORDER BY id) FROM public.event_request_outbox o),
                    'assignments',(SELECT jsonb_agg(to_jsonb(a) ORDER BY id) FROM public.event_coordinator_assignments a)) INTO before_state;
                BEGIN
                    PERFORM public.decide_event_request_by_coordinator('48000000-0000-4000-8000-000000000003','audit-coordinator','Changes Requested','Explain attendance');
                    RAISE EXCEPTION 'AC1-N3: failed history insert unexpectedly succeeded';
                EXCEPTION WHEN SQLSTATE 'P9910' THEN NULL; END;
                SELECT jsonb_build_object('event',(SELECT to_jsonb(e) FROM public.event_requests e WHERE id='48000000-0000-4000-8000-000000000003'),
                    'history',(SELECT jsonb_agg(to_jsonb(h) ORDER BY id) FROM public.event_request_status_history h),
                    'decisions',(SELECT jsonb_agg(to_jsonb(d) ORDER BY id) FROM public.event_request_review_decisions d),
                    'outbox',(SELECT jsonb_agg(to_jsonb(o) ORDER BY id) FROM public.event_request_outbox o),
                    'assignments',(SELECT jsonb_agg(to_jsonb(a) ORDER BY id) FROM public.event_coordinator_assignments a)) INTO after_state;
                ASSERT before_state IS NOT DISTINCT FROM after_state, 'AC1-N3: workflow partially persisted after history failure';
            END; $d$;
            ROLLBACK;
        """)

    # AC5-N9 (negative): actual role execution cannot bypass table privileges or server-only recording and transition functions
    def test_actual_browser_and_service_write_denials_preserve_all_rows(self):
        before = self.run_sql(SNAPSHOT)
        for role in ('anon', 'authenticated', 'service_role'):
            statements = [
                "INSERT INTO public.event_request_status_history(event_request_id,new_status,actor_role,source,entry_kind,occurred_at) VALUES('48000000-0000-4000-8000-000000000001','Draft','system','tampered','created',now())",
                "UPDATE public.event_request_status_history SET source='tampered'",
                "DELETE FROM public.event_request_status_history",
                "TRUNCATE public.event_request_status_history",
            ]
            if role != 'service_role':
                statements += [
                    "SELECT * FROM public.event_request_status_history",
                    "SELECT private.set_event_status_actor('48000000-0000-4000-8000-000000000001',NULL,'system','forged')",
                    "SELECT public.advance_event_request_by_coordinator('48000000-0000-4000-8000-000000000001','forged','Cancelled')",
                    "SELECT public.decide_event_request_by_coordinator('48000000-0000-4000-8000-000000000001','forged','Approved',NULL)",
                    "SELECT public.resume_event_request_review_by_coordinator('48000000-0000-4000-8000-000000000001','forged')",
                ]
            for statement in statements:
                with self.subTest(role=role, operation=statement.split()[0:2]):
                    self.run_sql(f'BEGIN; SET LOCAL ROLE {role}; {statement}; ROLLBACK;', expected_code='42501')
                    self.assertEqual(self.run_sql(SNAPSHOT), before)

    # AC2-B2 (boundary): null, blank and one/two-character context boundaries cannot corrupt stored metadata or protected rows
    def test_lower_actor_role_source_boundaries(self):
        self.run_sql("""
            BEGIN;
            DO $d$
            DECLARE v_owner uuid; v_event uuid; bad record; valid_length int; before_history jsonb;
            BEGIN
                SELECT id INTO v_owner FROM auth.users LIMIT 1;
                INSERT INTO public.event_requests(organiser_id,status) VALUES(v_owner,'Submitted') RETURNING id INTO v_event;
                SELECT jsonb_agg(to_jsonb(h) ORDER BY id) INTO before_history FROM public.event_request_status_history h WHERE event_request_id=v_event;
                FOR bad IN SELECT * FROM (VALUES
                    (NULL::text,'system'::text,NULL::text),
                    (NULL,'system',''), (NULL,'system',' '),
                    ('actor',NULL,'source'),('actor','','source'),('actor',' ','source'),
                    (NULL,'event_coordinator','source'),('','event_coordinator','source'),(' ','event_coordinator','source')
                ) AS invalid(actor_id,actor_role,source) LOOP
                    BEGIN
                        PERFORM private.set_event_status_actor(v_event,bad.actor_id,bad.actor_role,bad.source);
                        RAISE EXCEPTION 'AC2-B2: invalid context was accepted';
                    EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
                    ASSERT (SELECT status='Submitted' FROM public.event_requests WHERE id=v_event);
                    ASSERT (SELECT jsonb_agg(to_jsonb(h) ORDER BY id) FROM public.event_request_status_history h WHERE event_request_id=v_event) = before_history;
                END LOOP;
                BEGIN
                    PERFORM private.set_event_status_actor(NULL,'actor','event_coordinator','source');
                    RAISE EXCEPTION 'AC2-B2: missing event context was accepted';
                EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
                FOREACH valid_length IN ARRAY ARRAY[1,2] LOOP
                    PERFORM private.set_event_status_actor(v_event,repeat('a',valid_length),repeat('r',valid_length),repeat('s',valid_length));
                    UPDATE public.event_requests SET status=CASE valid_length WHEN 1 THEN 'Under Review' ELSE 'Approved' END WHERE id=v_event;
                    ASSERT (SELECT actor_id=repeat('a',valid_length) AND actor_role=repeat('r',valid_length) AND source=repeat('s',valid_length)
                        FROM public.event_request_status_history WHERE event_request_id=v_event ORDER BY id DESC LIMIT 1);
                END LOOP;
            END; $d$;
            ROLLBACK;
        """)

    # AC4-X4 (cross-cutting): legacy installation records known current state once without fabricating pre-installation transitions
    def test_real_legacy_fixture_has_honest_baseline(self):
        actual = self.run_sql("""
            SELECT entry_kind || '|' || new_status || '|' || actor_role || '|' || source || '|' ||
                (previous_status IS NULL)::text || '|' || (actor_id IS NULL)::text || '|' || (occurred_at IS NOT NULL)::text
            FROM public.event_request_status_history WHERE event_request_id='48000000-0000-4000-8000-000000000001';
        """)
        self.assertEqual(actual, 'baseline|Draft|system|history.recording_started|true|true|true')
        self.assertEqual(self.run_sql("SELECT count(*) FROM public.event_request_status_history WHERE event_request_id='48000000-0000-4000-8000-000000000001';"), '1')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn', required=True)
    parser.add_argument('--psql', default='psql')
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in ('127.0.0.1', 'localhost', '::1'):
        parser.error('Only a disposable loopback database is allowed')
    DSN, PSQL = args.dsn, args.psql
    unittest.main(argv=['test_event_status_history_audit'], verbosity=2)
