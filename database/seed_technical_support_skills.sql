-- Seed Technical Support Staff skill tags for the shared development database
-- (SCRUM-19). Run in the Supabase SQL Editor AFTER the accounts exist; the
-- accounts themselves come from seed_test_accounts.sql (technical_support and
-- venue_staff) plus, for a second suitable-for-lighting staff member,
-- technical_support2@example.com registered through authService.
-- Dev/test data only: never run this on production.
-- Safe to re-run: existing skill rows are left alone.
--
-- Fixtures:
--   technical_support@example.com  -> audio_visual, it_network
--   venue_staff@example.com        -> audio_visual   (tag without the TSS role,
--                                     so "suitable" must require both)
--   technical_support2@example.com -> lighting       (register the account first)

INSERT INTO public.technical_support_skills (user_id, skill_tag)
SELECT u.id::text, s.skill_tag
FROM (VALUES
    ('technical_support@example.com',  'audio_visual'),
    ('technical_support@example.com',  'it_network'),
    ('venue_staff@example.com',        'audio_visual'),
    ('technical_support2@example.com', 'lighting')
) AS s(email, skill_tag)
JOIN auth.users u ON u.email = s.email
ON CONFLICT DO NOTHING;

-- Expect the seeded rows; technical_support2 appears once its account exists.
SELECT sk.user_id, u.email, sk.skill_tag
FROM public.technical_support_skills sk
LEFT JOIN auth.users u ON u.id::text = sk.user_id
ORDER BY u.email NULLS LAST, sk.skill_tag;
