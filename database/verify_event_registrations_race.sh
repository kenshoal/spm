#!/usr/bin/env bash
# SCRUM-21 AC4-X1 (cross-cutting): two sessions race for the last place.
# Usage: DSN=postgresql://... ./verify_event_registrations_race.sh
# Needs 0048 applied, an existing auth user, and a DISPOSABLE database: it commits
# a fixture. Event status history is immutable, so the event cannot be deleted; the
# script removes the registrations and test users and leaves one Cancelled event
# named 'VERIFY SCRUM-21 race (left behind)'. Prints RACE VERIFICATION PASSED or exits 1.
set -euo pipefail
: "${DSN:?set DSN to the disposable database}"
PSQL=(psql -X -At -v ON_ERROR_STOP=1 "$DSN")

EVENT=$("${PSQL[@]}" -c "
  INSERT INTO public.event_requests (organiser_id, event_name, status,
      registration_opens_at, registration_closes_at, registration_capacity)
  SELECT id, 'VERIFY SCRUM-21 race', 'Draft', now() - interval '1 day', now() + interval '1 day', 1
  FROM auth.users ORDER BY created_at LIMIT 1 RETURNING id;" | head -1)
A=$("${PSQL[@]}" -c "INSERT INTO auth.users (id) VALUES (gen_random_uuid()) RETURNING id;" | head -1)
B=$("${PSQL[@]}" -c "INSERT INTO auth.users (id) VALUES (gen_random_uuid()) RETURNING id;" | head -1)
"${PSQL[@]}" -c "UPDATE public.event_requests SET status = 'Confirmed' WHERE id = '$EVENT';" >/dev/null

cleanup() {
  "${PSQL[@]}" -c "
    DELETE FROM public.event_registrations WHERE event_request_id = '$EVENT';
    UPDATE public.event_requests SET status = 'Cancelled',
        event_name = 'VERIFY SCRUM-21 race (left behind)' WHERE id = '$EVENT';
    DELETE FROM auth.users WHERE id IN ('$A', '$B');" >/dev/null || true
}
trap cleanup EXIT

# Session 1 takes the place, then holds the row lock for 3 s before committing.
"${PSQL[@]}" -c "BEGIN;
  SELECT public.register_for_event('$EVENT', '$A', now());
  SELECT pg_sleep(3);
  COMMIT;" >/tmp/race_1.out 2>&1 &
PID1=$!
sleep 1
# Session 2 starts while session 1 holds the lock, so it must queue and then see the place taken.
set +e
"${PSQL[@]}" -c "SELECT public.register_for_event('$EVENT', '$B', now());" >/tmp/race_2.out 2>&1
STATUS2=$?
set -e
wait $PID1

COUNT=$("${PSQL[@]}" -c "SELECT count(*) FROM public.event_registrations WHERE event_request_id = '$EVENT';")
if [ "$COUNT" = "1" ] && [ "$STATUS2" -ne 0 ] && grep -q "event full" /tmp/race_2.out; then
  echo "RACE VERIFICATION PASSED (1 row stored, second session refused: event full)"
else
  echo "RACE VERIFICATION FAILED: rows=$COUNT second-session-exit=$STATUS2"; cat /tmp/race_1.out /tmp/race_2.out; exit 1
fi
