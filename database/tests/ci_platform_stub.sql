-- The least of Supabase's platform that every migration needs, for a throwaway
-- vanilla PostgreSQL database in CI: the three API roles, and an auth schema with
-- users and the helper functions policies call. Never run this on a real project.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN BYPASSRLS;
    END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS auth;
CREATE TABLE IF NOT EXISTS auth.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text,
    email_confirmed_at timestamptz DEFAULT now(),
    raw_user_meta_data jsonb DEFAULT '{}',
    raw_app_meta_data jsonb DEFAULT '{}',
    created_at timestamptz DEFAULT now()
);
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS 'SELECT NULL::uuid';
CREATE OR REPLACE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql AS $$SELECT '{}'::jsonb$$;
CREATE OR REPLACE FUNCTION auth.role() RETURNS text LANGUAGE sql AS 'SELECT NULL::text';
INSERT INTO auth.users (email)
    SELECT 'user' || g || '@example.test' FROM generate_series(1, 4) AS g;
GRANT USAGE ON SCHEMA auth TO service_role;
