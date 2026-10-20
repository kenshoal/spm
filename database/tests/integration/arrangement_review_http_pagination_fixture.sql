-- AC5-B7 transport-equivalent fixture, disposable isolated PostgreSQL only.
DO $$ BEGIN
 ASSERT current_database()='scrum64_queue','Use only the owned scrum64_queue test database';
END $$;
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN;
CREATE TABLE public.arrangement_reviews (
 id uuid PRIMARY KEY,event_request_id uuid NOT NULL,arrangement text NOT NULL,
 arrangement_id uuid NOT NULL,trigger_id uuid NOT NULL,trigger_type text NOT NULL,
 changed_fields text[] NOT NULL,reason text NOT NULL,raised_at timestamptz NOT NULL,
 cleared_at timestamptz,cleared_by uuid
);
INSERT INTO public.arrangement_reviews
SELECT ('00000000-0000-4000-8000-'||lpad(n::text,12,'0'))::uuid,
 'eeeeeeee-1111-4111-8111-111111111111',CASE WHEN n%2=1 THEN 'venue_booking' ELSE 'equipment_reservation' END,
 'bbbbbbbb-1111-4111-8111-111111111111',('11111111-1111-4111-8111-'||lpad(n::text,12,'0'))::uuid,
 'event_change',ARRAY['expected_attendance'],'Attendance changed; review '||n,
 CASE WHEN n=1 THEN '2026-10-14T00:00:00Z'::timestamptz ELSE '2026-10-15T01:00:00Z'::timestamptz END,NULL,NULL
FROM generate_series(1,7) n;
-- Newer cleared and other-event rows must be excluded by the exact native helper.
INSERT INTO public.arrangement_reviews
SELECT ('00000000-0000-4000-8000-'||lpad(n::text,12,'0'))::uuid,
 CASE WHEN n<10 THEN 'eeeeeeee-1111-4111-8111-111111111111'::uuid ELSE 'eeeeeeee-2222-4222-8222-222222222222'::uuid END,
 'venue_booking','bbbbbbbb-1111-4111-8111-111111111111',('11111111-1111-4111-8111-'||lpad(n::text,12,'0'))::uuid,
 'event_change',ARRAY['expected_attendance'],'Excluded control '||n,'2026-10-16T00:00:00Z',
 CASE WHEN n<10 THEN '2026-10-16T01:00:00Z'::timestamptz ELSE NULL END,
 CASE WHEN n<10 THEN 'cccccccc-1111-4111-8111-111111111111'::uuid ELSE NULL END
FROM generate_series(8,11) n;
REVOKE ALL ON public.arrangement_reviews FROM PUBLIC,anon,authenticated,service_role;
GRANT USAGE ON SCHEMA public TO service_role;
GRANT SELECT ON public.arrangement_reviews TO service_role;
-- Root loads exact repository migration0035 after this fixture; no helper substitute here.
