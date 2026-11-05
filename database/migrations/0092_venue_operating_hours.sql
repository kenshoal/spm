-- Hotfix 2 (H12): each venue has its own daily operating hours. Run once, after 0091.
--
-- SCRUM-30 AC1 and AC2: Venue Staff set one daily operating start and end, on 15-minute steps
-- within 07:00 to 24:00 (Q&A #46: Venue Staff maintain operating hours; #131: 07:00 to 24:00 stays
-- the outer bound). AC6: an invalid range is refused and nothing changes. SCRUM-30 AC4, AC5,
-- SCRUM-31 AC4 and SCRUM-12 AC3: venue search, the availability check, suitability and the
-- calendar use them.
--
-- Until now every venue operated 07:00 to 24:00, and `operating_slots` (AM, PM, Night) was stored
-- but read by nothing since SCRUM-65 moved bookings to times. That column is left as it is.
--
-- Existing venues keep the whole day (420 to 1440), so nothing that was free becomes not free
-- until Venue Staff narrow a venue's hours. The same rules are checked in venueService; these
-- constraints keep a direct write honest too.

ALTER TABLE public.venues
    ADD COLUMN IF NOT EXISTS operating_start_minute integer NOT NULL DEFAULT 420,
    ADD COLUMN IF NOT EXISTS operating_end_minute integer NOT NULL DEFAULT 1440;

ALTER TABLE public.venues
    DROP CONSTRAINT IF EXISTS venues_operating_hours_check,
    ADD CONSTRAINT venues_operating_hours_check CHECK (
        operating_start_minute BETWEEN 420 AND 1440
        AND operating_end_minute BETWEEN 420 AND 1440
        AND operating_start_minute % 15 = 0
        AND operating_end_minute % 15 = 0
        AND operating_start_minute < operating_end_minute
    );
