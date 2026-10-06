-- Assign roles to the shared development test accounts.
--
-- Run in the Supabase SQL Editor AFTER the accounts have been registered
-- (see docs/authentication.txt, "Test accounts"). Every account uses the
-- password 12345678. Dev/test data only: never run this on production.
--
-- Safe to re-run: existing role rows are left alone.

-- 1. Confirm the test accounts' emails, so they can log in without clicking a
--    confirmation link (example.com addresses cannot receive mail).
UPDATE auth.users
SET email_confirmed_at = now()
WHERE email_confirmed_at IS NULL
  AND email IN (
    'admin@example.com',
    'attendee@example.com',
    'event_organiser@example.com',
    'event_organiser2@example.com',
    'event_organiser3@example.com',
    'event_operations_manager@example.com',
    'event_coordinator1@example.com',
    'event_coordinator2@example.com',
    'technical_support@example.com',
    'venue_staff@example.com'
  );

-- 2. One role per account; two coordinator accounts so "unrelated
--    coordinator" access checks can be tested.
INSERT INTO public.staff_roles (user_id, role)
SELECT u.id, r.role
FROM (VALUES
    ('admin@example.com',                    'admin'),
    ('attendee@example.com',                 'attendee'),
    ('event_organiser@example.com',          'event_organiser'),
    ('event_organiser2@example.com',         'event_organiser'),
    ('event_organiser3@example.com',         'event_organiser'),
    ('event_operations_manager@example.com', 'event_operations_manager'),
    ('event_coordinator1@example.com',       'event_coordinator'),
    ('event_coordinator2@example.com',       'event_coordinator'),
    ('technical_support@example.com',        'technical_support'),
    ('venue_staff@example.com',              'venue_staff')
) AS r(email, role)
JOIN auth.users u ON u.email = r.email
ON CONFLICT DO NOTHING;

-- 3. Client organisations (SCRUM-39, needs 0019): organisers 1 and 2 share
--    Acme so same-organisation viewing can be tested; organiser 3 is in Globex.
INSERT INTO public.client_organisations (name)
VALUES ('Acme Events'), ('Globex Corporation')
ON CONFLICT (name) DO NOTHING;

INSERT INTO public.organisation_members (user_id, organisation_id)
SELECT u.id, o.id
FROM (VALUES
    ('event_organiser@example.com',  'Acme Events'),
    ('event_organiser2@example.com', 'Acme Events'),
    ('event_organiser3@example.com', 'Globex Corporation')
) AS m(email, organisation)
JOIN auth.users u ON u.email = m.email
JOIN public.client_organisations o ON o.name = m.organisation
ON CONFLICT (user_id) DO NOTHING;

-- 4. Check: expect 10 rows, each with confirmed = true. A missing row means
--    that account has not been registered yet.
SELECT u.email, s.role, u.email_confirmed_at IS NOT NULL AS confirmed
FROM auth.users u
JOIN public.staff_roles s ON s.user_id = u.id
WHERE u.email IN (
    'admin@example.com', 'attendee@example.com', 'event_organiser@example.com',
    'event_organiser2@example.com', 'event_organiser3@example.com',
    'event_operations_manager@example.com', 'event_coordinator1@example.com',
    'event_coordinator2@example.com', 'technical_support@example.com',
    'venue_staff@example.com'
  )
ORDER BY s.role, u.email;
