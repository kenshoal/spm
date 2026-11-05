-- Release 1 hotfix 19: venue block reasons from the Week 7 customer update. Run once.
--
-- Week 7 change 2 lists the reasons Venue Staff block a venue for: "maintenance,
-- equipment failure, renovation, safety concerns, or other operational reasons".
-- block_reason (0023) held maintenance, renovation, safety and internal_use, so a
-- block for equipment failure or any other reason could not be recorded. This adds
-- the two missing values. internal_use stays: it is one of the "other" reasons the
-- team already offered, and removing an enum value would break existing rows.
--
-- A new enum value cannot be used in the transaction that adds it. The SQL Editor
-- runs this file as one statement batch that only adds, so nothing here uses them.

ALTER TYPE public.block_reason ADD VALUE IF NOT EXISTS 'equipment_failure';
ALTER TYPE public.block_reason ADD VALUE IF NOT EXISTS 'other';
