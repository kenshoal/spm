-- Venue booking requests (SCRUM-32).
--
-- An Event Coordinator's request for a venue, a date range and slots.
-- Submitting creates a pending row and reserves nothing. When Venue Staff decide
-- (SCRUM-15) the same row becomes the booking: an approved request is the
-- confirmed booking, and there is no separate allocation table. Safe to re-run.
--
-- Agreed with the SCRUM-15 and SCRUM-23 owner on 4 October 2026:
--   * start_date and end_date are inclusive; NIGHT belongs to its starting date.
--   * slots follow the venue_blocks rules: at least one, no NULL, no duplicate.
--   * pending requests never block each other; only an approval can conflict.
--   * decision_reason is required to reject; suggested_alternative is optional.
--   * approving a request and creating a block both lock the venues row, so
--     neither can bypass the other's checks. That lock belongs in the approve
--     and block functions, not here, because a constraint cannot express it.
--   * event_request_id is required, but it has no foreign key: eventRequestService
--     owns event requests, and venueService checks the reference through its API.
--   * coordinator_id is not stored. It goes stale when a Coordinator is
--     reassigned, so the current one is looked up through event_request_id.
--
-- requested_by and decided_by are plain uuid columns with no foreign key to
-- auth.users, as with changed_by in equipment_status_history (0001) and
-- assigned_by in staff_roles (0010). venueService takes them from the verified
-- token, never from the request body.
--
-- The event_name, expected_attendance and requirements_note columns are a
-- snapshot taken from the event at submission, so Venue Staff can assess a
-- request without being allowed to read the event request itself. They are
-- nullable because the source event may not have them.

DO $$
BEGIN
    CREATE TYPE public.booking_request_status AS ENUM
        ('pending', 'approved', 'rejected');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END;
$$;

CREATE TABLE IF NOT EXISTS public.venue_booking_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id uuid NOT NULL REFERENCES public.venues (id) ON DELETE RESTRICT,
    requested_by uuid NOT NULL,
    event_request_id uuid NOT NULL,
    event_name text,
    expected_attendance integer,
    requirements_note text,
    start_date date NOT NULL,
    end_date date NOT NULL,
    slots public.booking_slot[] NOT NULL,
    status public.booking_request_status NOT NULL DEFAULT 'pending',
    decision_reason text,
    suggested_alternative text,
    decided_by uuid,
    decided_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT venue_booking_requests_dates_ordered
        CHECK (end_date >= start_date),
    CONSTRAINT venue_booking_requests_slots_not_empty
        CHECK (cardinality(slots) > 0),
    CONSTRAINT venue_booking_requests_slots_no_nulls
        CHECK (array_position(slots, NULL) IS NULL),
    -- A subquery is not allowed in a CHECK, so each slot value is counted.
    CONSTRAINT venue_booking_requests_slots_no_duplicates
        CHECK (
            cardinality(array_positions(slots, 'AM'::public.booking_slot)) <= 1
            AND cardinality(array_positions(slots, 'PM'::public.booking_slot)) <= 1
            AND cardinality(array_positions(slots, 'NIGHT'::public.booking_slot)) <= 1
        ),
    -- The decision fields always agree with the status. A rejection needs a
    -- non-blank reason; an approval carries no reason or alternative.
    CONSTRAINT venue_booking_requests_decision_consistent
        CHECK (
            (status = 'pending'
                AND decided_by IS NULL
                AND decided_at IS NULL
                AND decision_reason IS NULL
                AND suggested_alternative IS NULL)
            OR (status = 'approved'
                AND decided_by IS NOT NULL
                AND decided_at IS NOT NULL
                AND decision_reason IS NULL
                AND suggested_alternative IS NULL)
            OR (status = 'rejected'
                AND decided_by IS NOT NULL
                AND decided_at IS NOT NULL
                AND decision_reason IS NOT NULL
                AND btrim(decision_reason) <> '')
        )
);

-- Overlap checks for a venue, and its approved bookings.
CREATE INDEX IF NOT EXISTS venue_booking_requests_venue_status_idx
    ON public.venue_booking_requests (venue_id, status);

-- A Coordinator's own requests, newest first.
CREATE INDEX IF NOT EXISTS venue_booking_requests_requester_created_idx
    ON public.venue_booking_requests (requested_by, created_at DESC, id DESC);

-- The Venue Staff queue: pending requests, oldest first.
CREATE INDEX IF NOT EXISTS venue_booking_requests_pending_queue_idx
    ON public.venue_booking_requests (created_at, id)
    WHERE status = 'pending';

-- Finding the bookings of one event.
CREATE INDEX IF NOT EXISTS venue_booking_requests_event_idx
    ON public.venue_booking_requests (event_request_id);

ALTER TABLE public.venue_booking_requests ENABLE ROW LEVEL SECURITY;

-- No policies: venueService reaches this table with the secret key, which
-- bypasses RLS. Browsers get no direct access, so a leaked publishable key
-- cannot read or write anyone's booking requests.
REVOKE ALL ON public.venue_booking_requests FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.venue_booking_requests TO service_role;
