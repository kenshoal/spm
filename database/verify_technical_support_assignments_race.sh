#!/bin/bash
# SCRUM-19 AC2-X5 (cross-cutting): two sessions assign the same person to the
# same requirement at the same time. Both queue on the event row lock inside
# assign_technical_support_staff, so the second insert meets the
# technical_support_assignments_once unique constraint: exactly one row.
# Usage: DSN=postgresql://... ./verify_technical_support_assignments_race.sh
# Needs 0051_technical_support_assignments.sql applied and a DISPOSABLE
# database: it commits a fixture and leaves one Cancelled event behind (status
# history is immutable). Prints RACE VERIFICATION PASSED or exits 1.

set -euo pipefail
: "${DSN:?set DSN to the disposable database}"
PSQL=(psql -X -At -v ON_ERROR_STOP=1 "$DSN")

EVENT='52000000-0000-4000-8000-000000000001'
REQ='52000000-0000-4000-8000-000000000002'
COORD='52000000-0000-4000-8000-000000000003'
TSS='52000000-0000-4000-8000-000000000004'
ORG='52000000-0000-4000-8000-000000000005'

"${PSQL[@]}" <<SQL
BEGIN;
INSERT INTO auth.users (id) VALUES ('$COORD'::uuid), ('$TSS'::uuid), ('$ORG');
INSERT INTO public.staff_roles (user_id, role) VALUES
    ('$COORD'::uuid, 'event_coordinator'), ('$TSS'::uuid, 'technical_support'),
    ('$ORG', 'event_organiser');
INSERT INTO public.technical_support_skills (user_id, skill_tag) VALUES
    ('$TSS', 'audio_visual');
INSERT INTO public.event_requests (id, organiser_id, status)
    VALUES ('$EVENT', '$ORG', 'Planning');
INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
    VALUES ('$EVENT', '$COORD', '$COORD');
INSERT INTO public.technical_support_requirements
    (id, event_request_id, description, skill_tag, recorded_by)
    VALUES ('$REQ', '$EVENT', 'Race fixture: one wireless mic', 'audio_visual', '$COORD');
COMMIT;
SQL

cleanup() {
    # The organiser user stays: event_requests.organiser_id cascades into the
    # immutable status history, so deleting it would fail. Left behind: one
    # Cancelled event, its organiser account and its baseline history.
    "${PSQL[@]}" <<SQL >/dev/null || true
BEGIN;
DELETE FROM public.technical_support_assignments WHERE event_request_id = '$EVENT';
DELETE FROM public.technical_support_requirements WHERE event_request_id = '$EVENT';
DELETE FROM public.event_coordinator_assignments WHERE event_request_id = '$EVENT';
UPDATE public.event_requests SET status = 'Cancelled' WHERE id = '$EVENT';
DELETE FROM public.staff_roles WHERE user_id IN (('$COORD')::uuid, ('$TSS')::uuid);
DELETE FROM auth.users WHERE id IN (('$COORD')::uuid, ('$TSS')::uuid);
COMMIT;
SQL
}
trap cleanup EXIT

OUT1=$(mktemp)
OUT2=$(mktemp)

# Session 1 wins the event row lock and holds it across its insert.
"${PSQL[@]}" <<SQL >"$OUT1" 2>&1 &
BEGIN;
SELECT * FROM public.assign_technical_support_staff('$EVENT', '$REQ', '$TSS', '$COORD');
SELECT pg_sleep(3);
COMMIT;
SQL
SESSION1=$!
sleep 1

# Session 2 queues behind the lock, then loses to the unique constraint.
set +e
"${PSQL[@]}" <<SQL >"$OUT2" 2>&1
SELECT * FROM public.assign_technical_support_staff('$EVENT', '$REQ', '$TSS', '$COORD');
SQL
STATUS2=$?
set -e
wait "$SESSION1"

COUNT=$("${PSQL[@]}" -c \
    "SELECT count(*) FROM public.technical_support_assignments WHERE requirement_id = '$REQ'")

if [ "$COUNT" = "1" ] && [ "$STATUS2" -ne 0 ] &&
   grep -q "technical_support_assignments_once" "$OUT2"; then
    echo "RACE VERIFICATION PASSED: one row; the loser hit the unique constraint"
else
    echo "RACE VERIFICATION FAILED: count=$COUNT loser status=$STATUS2"
    cat "$OUT2"
    exit 1
fi
