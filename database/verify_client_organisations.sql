-- Run after 0019_client_organisations.sql. Every change is rolled back.
-- Needs two existing auth users; it borrows the two oldest.

BEGIN;

DO $$
DECLARE
    v_user_a uuid;
    v_user_b uuid;
    v_acme uuid;
    v_globex uuid;
    v_request uuid;
    v_stamped uuid;
BEGIN
    SELECT id INTO v_user_a FROM auth.users ORDER BY created_at LIMIT 1;
    SELECT id INTO v_user_b FROM auth.users ORDER BY created_at OFFSET 1 LIMIT 1;
    IF v_user_b IS NULL THEN
        RAISE EXCEPTION 'Needs at least two auth users';
    END IF;
    DELETE FROM public.organisation_members WHERE user_id IN (v_user_a, v_user_b);

    INSERT INTO public.client_organisations (name) VALUES ('verify-acme')
        RETURNING id INTO v_acme;
    INSERT INTO public.client_organisations (name) VALUES ('verify-globex')
        RETURNING id INTO v_globex;
    INSERT INTO public.organisation_members (user_id, organisation_id)
        VALUES (v_user_a, v_acme);

    -- AC1-H2: a new request records its Organiser's organisation, and a
    -- supplied organisation_id is ignored.
    INSERT INTO public.event_requests (organiser_id, organisation_id, event_name)
        VALUES (v_user_a, v_globex, 'verify request')
        RETURNING id, organisation_id INTO v_request, v_stamped;
    IF v_stamped IS DISTINCT FROM v_acme THEN
        RAISE EXCEPTION 'AC1-H2: expected organisation %, got %', v_acme, v_stamped;
    END IF;

    -- AC2-X1: the recorded organisation cannot be changed afterwards.
    UPDATE public.event_requests SET organisation_id = v_globex WHERE id = v_request
        RETURNING organisation_id INTO v_stamped;
    IF v_stamped IS DISTINCT FROM v_acme THEN
        RAISE EXCEPTION 'AC2-X1: organisation changed to %', v_stamped;
    END IF;

    -- AC3-P2: an Organiser with no membership gets no organisation.
    INSERT INTO public.event_requests (organiser_id, event_name)
        VALUES (v_user_b, 'verify solo')
        RETURNING organisation_id INTO v_stamped;
    IF v_stamped IS NOT NULL THEN
        RAISE EXCEPTION 'AC3-P2: expected no organisation, got %', v_stamped;
    END IF;

    -- AC3-N3: one organisation per Organiser.
    BEGIN
        INSERT INTO public.organisation_members (user_id, organisation_id)
            VALUES (v_user_a, v_globex);
        RAISE EXCEPTION 'AC3-N3: a second membership was accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;

    -- AC3-N2: an unknown organisation is refused.
    BEGIN
        INSERT INTO public.organisation_members (user_id, organisation_id)
            VALUES (v_user_b, gen_random_uuid());
        RAISE EXCEPTION 'AC3-N2: an unknown organisation was accepted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
END;
$$;

-- AC3-N1: browser roles have no privileges on the new tables.
SELECT
    has_table_privilege('anon', 'public.organisation_members', 'SELECT') AS anon_members_select,
    has_table_privilege('authenticated', 'public.organisation_members', 'INSERT') AS auth_members_insert,
    has_table_privilege('anon', 'public.client_organisations', 'SELECT') AS anon_orgs_select,
    has_table_privilege('authenticated', 'public.client_organisations', 'INSERT') AS auth_orgs_insert;
-- Expected: false, false, false, false.

ROLLBACK;
