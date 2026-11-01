-- Release 1 hotfix 16: staff can tell who a registration belongs to. Run once.
--
-- SCRUM-25's check-in needs a manual lookup and Q&A #32 lets Organisers see attendee
-- information for their own events, but registration lists showed only account ids,
-- because eventRequestService cannot read auth.users through the Data API. This
-- returns the email of each registration on one event. eventRequestService checks
-- the caller's relationship to the event first (SCRUM-34).

CREATE OR REPLACE FUNCTION public.event_registration_attendee_emails(p_event_request_id uuid)
RETURNS TABLE (registration_id uuid, attendee_email text)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT r.id, u.email::text
    FROM public.event_registrations AS r
    JOIN auth.users AS u ON u.id = r.attendee_id
    WHERE r.event_request_id = p_event_request_id;
$$;

REVOKE ALL ON FUNCTION public.event_registration_attendee_emails(uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.event_registration_attendee_emails(uuid)
    TO service_role;

-- The Coordinator's waiting-list view (SCRUM-24 AC3, hotfix 7) needs the same lookup.
CREATE OR REPLACE FUNCTION public.event_waitlist_attendee_emails(p_event_request_id uuid)
RETURNS TABLE (entry_id uuid, attendee_email text)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT w.id, u.email::text
    FROM public.event_waitlist_entries AS w
    JOIN auth.users AS u ON u.id = w.attendee_id
    WHERE w.event_request_id = p_event_request_id;
$$;

REVOKE ALL ON FUNCTION public.event_waitlist_attendee_emails(uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.event_waitlist_attendee_emails(uuid)
    TO service_role;
