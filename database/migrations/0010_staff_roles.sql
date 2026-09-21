CREATE TABLE IF NOT EXISTS staff_roles (
    user_id uuid NOT NULL,
    role varchar(40) NOT NULL CHECK (
        role IN (
            'admin',
            'attendee',
            'event_coordinator',
            'event_operations_manager',
            'event_organiser',
            'technical_support',
            'venue_staff'
        )
    ),
    assigned_by uuid,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, role)
);

ALTER TABLE staff_roles ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON staff_roles FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON staff_roles TO service_role;
