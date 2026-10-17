-- Venue setup and turnaround time (SCRUM-59; Week 7 Change #1).
-- Minutes in 15-minute increments (discussion #131), from 0 to 1020: the
-- 07:00-24:00 operating window. 0 means none, so existing venues start with no
-- setup or turnaround time until Venue Staff set one. Changing these values
-- does not touch bookings or blocks; SCRUM-20 uses them for conflict checks.
-- Safe to re-run: an existing column (and its check) is left as it is.
-- Access is unchanged: 0016 keeps venues server-only.

ALTER TABLE public.venues
    ADD COLUMN IF NOT EXISTS setup_minutes integer NOT NULL DEFAULT 0
        CONSTRAINT venues_setup_minutes_valid
        CHECK (setup_minutes BETWEEN 0 AND 1020 AND setup_minutes % 15 = 0),
    ADD COLUMN IF NOT EXISTS turnaround_minutes integer NOT NULL DEFAULT 0
        CONSTRAINT venues_turnaround_minutes_valid
        CHECK (turnaround_minutes BETWEEN 0 AND 1020 AND turnaround_minutes % 15 = 0);
