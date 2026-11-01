-- Release 1 hotfix 12: capacity per room layout. Run once.
--
-- Q&A #112: capacity varies by layout, is supplied as a venue attribute, and the
-- chosen layout's capacity is what suitability uses. layout_capacities maps a layout
-- to its capacity; a layout with no entry falls back to max_capacity, so existing
-- venues keep working until Venue Staff fill them in. venueService validates the keys
-- and the values.

ALTER TABLE public.venues
    ADD COLUMN IF NOT EXISTS layout_capacities jsonb NOT NULL DEFAULT '{}'::jsonb
        CONSTRAINT venues_layout_capacities_object
            CHECK (jsonb_typeof(layout_capacities) = 'object');
