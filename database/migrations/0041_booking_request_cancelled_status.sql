-- Add the cancelled status for venue booking requests (SCRUM-61).
--
-- This is its own file because Postgres cannot use a new enum value in the
-- transaction that adds it: 0042 uses 'cancelled' in a CHECK constraint and a
-- function, so it must run after this file has been applied. Safe to re-run.

ALTER TYPE public.booking_request_status ADD VALUE IF NOT EXISTS 'cancelled';
