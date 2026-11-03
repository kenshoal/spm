-- Hotfix 2 (H4): a Confirmed event that has a recorded final end can be rescheduled.
-- Run once, after 0085.
--
-- SCRUM-40 AC9 and SCRUM-29 AC4: when an approved date change (SCRUM-35) or a
-- Coordinator edit (SCRUM-29) moves a Confirmed event, the event returns to Planning,
-- its final end is cleared and the change succeeds.
--
-- Until now it failed. 0063's protect_event_final_end refused any date change while the
-- event was Confirmed and had a final end. Both routes change the dates while the event
-- is still Confirmed: 0071 reopens it only afterwards, from an AFTER trigger on the
-- arrangement review, which is too late.
--
-- This migration changes only the protection and adds the reopening:
--   1. protect_event_final_end lets the dates of a Confirmed event move (the end is then
--      cleared by the rule it already has). The end still cannot be changed directly, and
--      a Completed, Cancelled or Rejected event still keeps its dates once it has an end.
--   2. reopen_confirmed_event_on_date_change returns a Confirmed event to Planning when its
--      dates change, recorded as a system transition with the same source 0071 uses, so
--      the event is reopened even when there is no arrangement left to flag. When 0071's
--      trigger gets there first this one finds the event already in Planning and does nothing.
-- 0071 and 0077 are not edited: they keep changing the dates, and the history and the
-- notices follow the status change as before.

CREATE OR REPLACE FUNCTION private.protect_event_final_end()
RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
BEGIN
    IF CURRENT_USER IN ('anon', 'authenticated') THEN
        IF TG_OP = 'INSERT' THEN
            IF NEW.final_event_end_at IS NOT NULL THEN
                RAISE EXCEPTION 'Record the final event end through the coordinator workflow'
                    USING ERRCODE = '42501';
            END IF;
        ELSIF NEW.final_event_end_at IS DISTINCT FROM OLD.final_event_end_at THEN
            RAISE EXCEPTION 'Record the final event end through the coordinator workflow'
                USING ERRCODE = '42501';
        END IF;
    END IF;
    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;

    IF OLD.status IN ('Confirmed', 'Completed', 'Cancelled', 'Rejected') THEN
        -- A direct change of the end is refused. A reschedule of a Confirmed event is
        -- allowed (it reopens the event and clears the end); a closed event keeps its dates.
        IF NEW.final_event_end_at IS DISTINCT FROM OLD.final_event_end_at
           OR (OLD.final_event_end_at IS NOT NULL
               AND OLD.status <> 'Confirmed'
               AND NEW.proposed_date_times IS DISTINCT FROM OLD.proposed_date_times) THEN
            RAISE EXCEPTION 'The final event end is fixed after confirmation or closure'
                USING ERRCODE = 'P0004';
        END IF;
    END IF;

    IF NEW.proposed_date_times IS DISTINCT FROM OLD.proposed_date_times THEN
        NEW.final_event_end_at := NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION private.reopen_confirmed_event_on_date_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.event_requests
        WHERE id = NEW.id AND status = 'Confirmed'
    ) THEN
        PERFORM private.set_event_status_actor(
            NEW.id, NULL, 'system', 'event_change.no_longer_confirmed');
        UPDATE public.event_requests
        SET status = 'Planning'
        WHERE id = NEW.id AND status = 'Confirmed';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION private.reopen_confirmed_event_on_date_change()
    FROM PUBLIC, anon, authenticated, service_role;

DROP TRIGGER IF EXISTS reopen_confirmed_event_on_date_change ON public.event_requests;
CREATE TRIGGER reopen_confirmed_event_on_date_change
    AFTER UPDATE OF proposed_date_times ON public.event_requests
    FOR EACH ROW
    WHEN (OLD.status = 'Confirmed'
          AND NEW.status = 'Confirmed'
          AND NEW.proposed_date_times IS DISTINCT FROM OLD.proposed_date_times)
    EXECUTE FUNCTION private.reopen_confirmed_event_on_date_change();
