"""Opt-in native saved-decision and arrangement-review integration checks.

Preload the reviewed published safety/readiness SQL through 0047 and genuine
SCRUM-64 prerequisites in an owned disposable loopback scrum48_* PostgreSQL DB.
The base feature checkout alone does not supply this external stack. See
docs/testcases/scrum_64_integration_handoff.md for pinned setup and evidence.
Only --scope handover/all requires the public handover RPC; decision omits it.
Native current staff_roles checks are not JWT/HTTP authorisation proof.
No production replacements are supplied. Every case rolls back its real fixtures.
"""

import argparse
import subprocess
import unittest
from urllib.parse import urlparse

OFFICER = "64000000-0000-4000-8000-000000009001"
WRONG = "64000000-0000-4000-8000-000000009002"
COORDINATOR = "64000000-0000-4000-8000-000000009003"
E1 = "64000000-0000-4000-8000-000000009101"
E2 = "64000000-0000-4000-8000-000000009102"
E3 = "64000000-0000-4000-8000-000000009103"
VENUE = "64000000-0000-4000-8000-000000009201"
BOOKING = "64000000-0000-4000-8000-000000009301"
SIBLING = "64000000-0000-4000-8000-000000009302"
EQUIPMENT = "64000000-0000-4000-8000-000000009401"
REQ = "64000000-0000-4000-8000-000000009501"
OTHER_REQ = "64000000-0000-4000-8000-000000009502"
RESERVATION = "64000000-0000-4000-8000-000000009601"
OTHER_RES = "64000000-0000-4000-8000-000000009602"
REASON = "Recheck emergency access and the microphone safety arrangement"
TARGETS = f'[{{"arrangement":"venue_booking","id":"{BOOKING}"}},{{"arrangement":"equipment_reservation","id":"{RESERVATION}"}}]'


def decide(event=E1, actor=OFFICER, decision="changes_requested", targets=TARGETS):
    return f"public.decide_safety_review('{event}','{actor}','{decision}','{REASON}','{targets}'::jsonb)"


def snapshot_sql():
    tables = ["event_requests", "event_request_status_history", "safety_reviews", "arrangement_reviews", "venue_booking_requests", "equipment_reservations", "equipment_requirements", "equipment", "equipment_status_history", "notifications", "event_request_outbox"]
    fields = [f"'{t}',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.{t} x)" for t in tables]
    fields.append("'review_jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY review_id),'[]') FROM public.arrangement_review_notification_outbox x)")
    return "CREATE FUNCTION pg_temp.integration_state() RETURNS jsonb LANGUAGE sql STABLE AS $state$ SELECT jsonb_build_object(" + ",".join(fields) + ") $state$;"


def fixtures(*, require_handover=False):
    handover_capability = """
      ASSERT to_regprocedure('public.send_event_request_for_safety_review(uuid,character varying)') IS NOT NULL,
       'CAPABILITY MISSING: actual published handover required; no fake gate';
    """ if require_handover else ""
    return f"""
    DO $required$ BEGIN
      ASSERT to_regprocedure('public.decide_safety_review(uuid,uuid,text,text,jsonb)') IS NOT NULL,
       'CAPABILITY MISSING: actual published decide_safety_review required; no bootstrap replacement';
      {handover_capability}
    END $required$;
    INSERT INTO auth.users(id) VALUES('{OFFICER}'),('{WRONG}'),('{COORDINATOR}');
    INSERT INTO public.staff_roles(user_id,role) VALUES('{OFFICER}','safety_officer'),('{WRONG}','venue_staff'),('{COORDINATOR}','event_coordinator');
    INSERT INTO public.event_requests(id,organiser_id,event_name,status,expected_attendance) VALUES
      ('{E1}','{OFFICER}','VERIFY combined safety main','Safety Review',25),
      ('{E2}','{OFFICER}','VERIFY combined safety other','Safety Review',25),
      ('{E3}','{OFFICER}','VERIFY incomplete handover','Planning',25);
    INSERT INTO public.event_coordinator_assignments(event_request_id,coordinator_id,assigned_by)
      VALUES('{E1}','{COORDINATOR}','{OFFICER}'),('{E3}','{COORDINATOR}','{OFFICER}');
    INSERT INTO public.venues(id,name,location,max_capacity,facilities,accessibility_features,supported_layouts,operating_slots)
      VALUES('{VENUE}','VERIFY combined safety venue','Test wing',100,'{{}}','{{}}','{{theatre}}','{{AM,PM}}');
    INSERT INTO public.venue_booking_requests(id,venue_id,requested_by,event_request_id,start_date,end_date,slots,status,decided_by,decided_at) VALUES
      ('{BOOKING}','{VENUE}','{COORDINATOR}','{E1}',current_date+30,current_date+30,'{{AM}}','approved','{OFFICER}',now()),
      ('{SIBLING}','{VENUE}','{COORDINATOR}','{E1}',current_date+30,current_date+30,'{{PM}}','approved','{OFFICER}',now());
    INSERT INTO public.equipment(id,type,total_owned_quantity,home_location,created_by)
      VALUES('{EQUIPMENT}','VERIFY integration microphone',10,'Test store','{OFFICER}');
    INSERT INTO public.equipment_requirements(id,event_request_id,equipment_type,quantity,recorded_by) VALUES
      ('{REQ}','{E1}','VERIFY integration microphone',1,'{OFFICER}'),
      ('{OTHER_REQ}','{E2}','VERIFY integration microphone',1,'{OFFICER}');
    INSERT INTO public.equipment_reservations(id,equipment_id,requirement_id,event_request_id,quantity,collection_date,return_date,created_by) VALUES
      ('{RESERVATION}','{EQUIPMENT}','{REQ}','{E1}',1,current_date+29,current_date+30,'{OFFICER}'),
      ('{OTHER_RES}','{EQUIPMENT}','{OTHER_REQ}','{E2}',1,current_date+29,current_date+30,'{OFFICER}');
    {snapshot_sql()}
    CREATE FUNCTION pg_temp.integration_unrelated() RETURNS jsonb LANGUAGE sql STABLE AS $unrelated$
      SELECT jsonb_build_object(
        'events',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_requests x WHERE id<>'{E1}'),
        'history',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.event_request_status_history x WHERE event_request_id<>'{E1}'),
        'decisions',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.safety_reviews x WHERE event_request_id<>'{E1}'),
        'reviews',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]') FROM public.arrangement_reviews x WHERE event_request_id<>'{E1}'),
        'jobs',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY review_id),'[]') FROM public.arrangement_review_notification_outbox x WHERE event_request_id<>'{E1}'))
      $unrelated$;
    """


class CombinedSafetyIntegration(unittest.TestCase):
    def native(self, body, *, prefix=""):
        require_handover = self._testMethodName == "test_actual_handover_consumes_shared_outstanding_facts"
        query = "BEGIN;\n" + fixtures(require_handover=require_handover) + prefix + "\n" + body + "\nROLLBACK;"
        result = subprocess.run(
            [PSQL, "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose", "-d", DSN],
            input=query, text=True, capture_output=True, timeout=25, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("INTEGRATION ASSERTIONS PASSED", result.stderr)

    # AC7-X5 (cross-cutting): the actual saved changes_requested UUID/reason must own exact flags and required jobs in the same committed result.
    def test_actual_saved_decision_raises_exact_review_causes(self):
        self.native(f"""DO $case$
        DECLARE before_state jsonb:=pg_temp.integration_state(); unrelated_before jsonb:=pg_temp.integration_unrelated(); saved public.safety_reviews; returned jsonb; history_count integer;
        BEGIN
          SELECT count(*) INTO history_count FROM public.event_request_status_history WHERE event_request_id='{E1}';
          SET LOCAL ROLE service_role;
          SELECT to_jsonb(x) INTO returned FROM {decide()} x;
          RESET ROLE;
          SELECT * INTO saved FROM public.safety_reviews WHERE event_request_id='{E1}';
          ASSERT saved.id IS NOT NULL AND saved.decision='changes_requested' AND saved.decided_by='{OFFICER}'
            AND saved.reason='{REASON}' AND saved.targets='{TARGETS}'::jsonb
            AND saved.decided_at>=transaction_timestamp() AND saved.decided_at<=clock_timestamp(),
            'AC7-X5: actual saved decision/actor/reason/targets missing';
          ASSERT (SELECT count(*)=2 AND bool_and(event_request_id='{E1}' AND trigger_id=saved.id
            AND trigger_type='safety_recheck' AND reason=saved.reason AND changed_fields='{{}}'::text[]
            AND cleared_at IS NULL AND cleared_by IS NULL AND raised_at>=transaction_timestamp()
            AND ((arrangement='venue_booking' AND arrangement_id='{BOOKING}')
              OR(arrangement='equipment_reservation' AND arrangement_id='{RESERVATION}')))
            FROM public.arrangement_reviews WHERE event_request_id='64000000-0000-4000-8000-000000009101'), 'AC7-X5: saved changes_requested decision did not raise the two exact real-cause flags';
          ASSERT (SELECT count(*)=2 AND bool_and(payload->>'trigger_id'=saved.id::text
            AND payload->>'trigger_type'='safety_recheck' AND payload->>'reason'=saved.reason
            AND published_at IS NULL) FROM public.arrangement_review_notification_outbox WHERE event_request_id='{E1}'),
            'AC7-X5: required enqueue absent or lost actual saved decision cause';
          ASSERT (SELECT to_jsonb(e)=returned AND status='Planning' FROM public.event_requests e WHERE id='{E1}'),
            'AC7-X5: caller lifecycle/result mismatch';
          ASSERT (SELECT count(*)=history_count+1 FROM public.event_request_status_history WHERE event_request_id='{E1}')
            AND (SELECT count(*)=1 FROM public.event_request_status_history WHERE event_request_id='{E1}'
              AND previous_status='Safety Review' AND new_status='Planning' AND actor_id='{OFFICER}'
              AND actor_role='safety_officer' AND entry_kind='transition' AND source<>''),
            'AC7-X5: actual officer lifecycle audit missing';
          ASSERT pg_temp.integration_state()-ARRAY['event_requests','event_request_status_history','safety_reviews','arrangement_reviews','review_jobs']
            =before_state-ARRAY['event_requests','event_request_status_history','safety_reviews','arrangement_reviews','review_jobs'],
            'AC7-X5: caller mutated unrelated arrangements/inbox/submission work';
          ASSERT pg_temp.integration_unrelated()=unrelated_before,'AC7-X5: caller changed unrelated event/history/decision/review/job rows';
          RAISE NOTICE 'INTEGRATION ASSERTIONS PASSED AC7-X5';
        END $case$;""")

    # AC7-N1 (negative): actual native current-role authorisation refuses wrong/removed officers and retains an empty-target success control.
    def test_current_role_wrong_and_removed_officer(self):
        self.native(f"""DO $case$
        DECLARE before_state jsonb; message text;
        BEGIN
          before_state:=pg_temp.integration_state();
          BEGIN
            SET LOCAL ROLE service_role; PERFORM {decide(actor=WRONG)}; RESET ROLE;
            RAISE EXCEPTION 'AC7-N1: wrong role decision succeeded' USING ERRCODE='P9901';
          EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
          ASSERT pg_temp.integration_state()=before_state,'AC7-N1: wrong role wrote protected facts';
          DELETE FROM public.staff_roles WHERE user_id='{OFFICER}' AND role='safety_officer';
          before_state:=pg_temp.integration_state();
          BEGIN
            SET LOCAL ROLE service_role; PERFORM {decide()}; RESET ROLE;
            RAISE EXCEPTION 'AC7-N1: removed officer decision succeeded' USING ERRCODE='P9901';
          EXCEPTION WHEN SQLSTATE 'P0003' THEN NULL; END;
          ASSERT pg_temp.integration_state()=before_state,'AC7-N1: removed officer wrote protected facts';
          INSERT INTO public.staff_roles(user_id,role) VALUES('{OFFICER}','safety_officer');
          SET LOCAL ROLE service_role; PERFORM {decide(targets='[]')}; RESET ROLE;
          ASSERT (SELECT count(*)=1 AND bool_and(decided_by='{OFFICER}' AND reason='{REASON}' AND targets='[]'::jsonb) FROM public.safety_reviews WHERE event_request_id='{E1}')
            AND (SELECT status='Planning' FROM public.event_requests WHERE id='{E1}')
            AND NOT EXISTS(SELECT 1 FROM public.arrangement_reviews WHERE event_request_id='{E1}')
            AND NOT EXISTS(SELECT 1 FROM public.arrangement_review_notification_outbox WHERE event_request_id='{E1}'),
            'AC7-N1: restored current officer/empty-target positive control failed';
          RAISE NOTICE 'INTEGRATION ASSERTIONS PASSED AC7-N1 (native role only, no JWT/API claim)';
        END $case$;""")

    # AC7-N3 (negative): actual caller cross-event refusal rolls back saved decision/lifecycle as well as all possible flag work.
    def test_cross_event_target_rolls_back_actual_caller(self):
        targets = f'[{{"arrangement":"venue_booking","id":"{BOOKING}"}},{{"arrangement":"equipment_reservation","id":"{OTHER_RES}"}}]'
        self.native(f"""DO $case$
        DECLARE before_state jsonb:=pg_temp.integration_state();
        BEGIN
          BEGIN
            SET LOCAL ROLE service_role; PERFORM {decide(targets=targets)}; RESET ROLE;
            RAISE EXCEPTION 'AC7-N3: actual caller accepted cross-event target instead of 22023' USING ERRCODE='P9902';
          EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
          ASSERT pg_temp.integration_state()=before_state,'AC7-N3: rejected target left actual decision/status/history/flags/jobs';
          RAISE NOTICE 'INTEGRATION ASSERTIONS PASSED AC7-N3';
        END $case$;""")

    # AC7-X6 (cross-cutting): a real second enqueue failure must roll back the caller's saved decision/status/history and both flags/jobs.
    def test_required_enqueue_failure_rolls_back_actual_decision(self):
        prefix = f"""
        CREATE TEMP SEQUENCE integration_job_attempts;
        CREATE FUNCTION pg_temp.integration_job_fault() RETURNS trigger LANGUAGE plpgsql AS $fault$
        BEGIN
          IF NEW.event_request_id='{E1}' AND nextval('pg_temp.integration_job_attempts')=2 THEN
            RAISE EXCEPTION 'SCRUM64 integration injected second enqueue failure' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $fault$;
        CREATE TRIGGER integration_second_job_fault BEFORE INSERT ON public.arrangement_review_notification_outbox
          FOR EACH ROW EXECUTE FUNCTION pg_temp.integration_job_fault();
        """
        self.native(f"""DO $case$
        DECLARE before_state jsonb:=pg_temp.integration_state(); message text;
        BEGIN
          BEGIN
            SET LOCAL ROLE service_role; PERFORM {decide()}; RESET ROLE;
            RAISE EXCEPTION 'AC7-X6: actual saved caller never reached required second enqueue failure' USING ERRCODE='P9903';
          EXCEPTION WHEN check_violation THEN
            GET STACKED DIAGNOSTICS message=MESSAGE_TEXT;
            ASSERT message='SCRUM64 integration injected second enqueue failure','AC7-X6: unrelated setup failure caught';
          END;
          ASSERT currval('pg_temp.integration_job_attempts')=2,'AC7-X6: actual second job was not attempted';
          ASSERT pg_temp.integration_state()=before_state,'AC7-X6: required enqueue fault left actual decision/lifecycle/flags/jobs';
          RAISE NOTICE 'INTEGRATION ASSERTIONS PASSED AC7-X6';
        END $case$;""", prefix=prefix)

    # AC7-X7 (cross-cutting): repeating the actual stale decision follows P0004 without rewriting its saved payload or lifecycle history.
    def test_actual_stale_decision_preserves_saved_evidence(self):
        self.native(f"""DO $case$
        DECLARE before_state jsonb;
        BEGIN
          SET LOCAL ROLE service_role; PERFORM {decide(targets='[]')}; RESET ROLE;
          before_state:=pg_temp.integration_state();
          BEGIN
            SET LOCAL ROLE service_role; PERFORM {decide(decision='approved',targets='[]')}; RESET ROLE;
            RAISE EXCEPTION 'AC7-X7: stale actual decision succeeded' USING ERRCODE='P9904';
          EXCEPTION WHEN SQLSTATE 'P0004' THEN NULL; END;
          ASSERT pg_temp.integration_state()=before_state,'AC7-X7: stale caller changed immutable saved evidence';
          ASSERT (SELECT count(*)=1 AND bool_and(decision='changes_requested' AND reason='{REASON}' AND targets='[]'::jsonb) FROM public.safety_reviews WHERE event_request_id='{E1}'),
            'AC7-X7: first saved decision missing or overwritten';
          RAISE NOTICE 'INTEGRATION ASSERTIONS PASSED AC7-X7';
        END $case$;""")

    def refusal(self, call, label):
        return f"""
        before_state:=pg_temp.integration_state();
        BEGIN
          SET LOCAL ROLE service_role; PERFORM {call}; RESET ROLE;
          RAISE EXCEPTION '{label}: consuming gate accepted outstanding work instead of P0005' USING ERRCODE='P9905';
        EXCEPTION WHEN SQLSTATE 'P0005' THEN
          GET STACKED DIAGNOSTICS details=PG_EXCEPTION_DETAIL;
          ASSERT jsonb_typeof(details::jsonb)='array' AND jsonb_array_length(details::jsonb)>0,
            '{label}: refusal omitted useful nonempty JSON issues';
        END;
        ASSERT pg_temp.integration_state()=before_state,'{label}: gate refusal mutated protected state';
        """

    def cancelled_flag(self):
        return f"""
        SET LOCAL ROLE service_role; PERFORM public.cancel_venue_booking_request('{BOOKING}','{COORDINATOR}'); RESET ROLE;
        INSERT INTO public.arrangement_reviews(event_request_id,arrangement,arrangement_id,trigger_id,trigger_type,changed_fields,reason)
        VALUES('{E1}','venue_booking','{BOOKING}',gen_random_uuid(),'event_change','{{}}','Retained uncleared cancelled-booking evidence');
        """

    # AC5-X12 (cross-cutting): actual approval must refuse ordinary unreadiness and retained cancelled-booking review facts without guessed issue item shapes.
    def test_actual_approval_consumes_readiness_and_outstanding_facts(self):
        for case in ("ordinary", "cancelled-review"):
            with self.subTest(case=case):
                setup = "" if case == "ordinary" else self.cancelled_flag()
                event = E2 if case == "ordinary" else E1
                body = self.refusal(decide(event=event,decision="approved",targets="[]"), "AC5-X12")
                self.native(f"""DO $case$ DECLARE before_state jsonb; details text;
                BEGIN {setup} {body}
                  RAISE NOTICE 'INTEGRATION ASSERTIONS PASSED AC5-X12';
                END $case$;""")

    # AC5-X13 (cross-cutting): real coordinator handover keeps its ordinary refusal and must also consume retained outstanding review facts.
    def test_actual_handover_consumes_shared_outstanding_facts(self):
        for case in ("ordinary", "cancelled-review"):
            with self.subTest(case=case):
                setup = "" if case == "ordinary" else f"SET LOCAL ROLE service_role; PERFORM {decide(targets='[]')}; RESET ROLE;" + self.cancelled_flag()
                event = E3 if case == "ordinary" else E1
                body = self.refusal(f"public.send_event_request_for_safety_review('{event}','{COORDINATOR}')", "AC5-X13")
                self.native(f"""DO $case$ DECLARE before_state jsonb; details text;
                BEGIN {setup} {body}
                  RAISE NOTICE 'INTEGRATION ASSERTIONS PASSED AC5-X13';
                END $case$;""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", default="psql")
    parser.add_argument("--disposable", action="store_true")
    parser.add_argument("--scope", choices=("decision", "handover", "all"), default="all",
                        help="Select published decision checks, handover diagnostics or both (default)")
    args = parser.parse_args()
    parsed = urlparse(args.dsn)
    if not args.disposable or parsed.scheme not in ("postgres", "postgresql") or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or not parsed.path.removeprefix("/").startswith("scrum48_"):
        parser.error("Refusing anything except an explicitly disposable loopback scrum48_* database")
    DSN, PSQL = args.dsn, args.psql
    names = unittest.defaultTestLoader.getTestCaseNames(CombinedSafetyIntegration)
    handover_name = "test_actual_handover_consumes_shared_outstanding_facts"
    if args.scope == "decision":
        names = [name for name in names if name != handover_name]
    elif args.scope == "handover":
        names = [handover_name]
    suite = unittest.TestSuite(CombinedSafetyIntegration(name) for name in names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
