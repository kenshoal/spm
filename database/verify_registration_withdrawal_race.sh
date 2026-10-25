#!/usr/bin/env bash
# SCRUM-22 AC3-X1 / AC3-X2 (cross-cutting): two sessions race on one registration.
# Usage: DSN=postgresql://... ./verify_registration_withdrawal_race.sh
# Needs 0048 and 0062 applied, an existing auth user, and a DISPOSABLE database: it
# commits fixtures. Event status history is immutable, so the events cannot be
# deleted; the script removes the registrations and test users and leaves two
# Cancelled events named 'VERIFY SCRUM-22 race ... (left behind)'.
# Prints RACE VERIFICATION PASSED or exits 1.
set -euo pipefail
: "${DSN:?set DSN to the disposable database}"
PSQL=(psql -X -At -v ON_ERROR_STOP=1 "$DSN")
OUT=$(mktemp -d)

new_event() {
  "${PSQL[@]}" -c "
    INSERT INTO public.event_requests (organiser_id, event_name, status, proposed_date_times,
        registration_opens_at, registration_closes_at, registration_capacity)
    SELECT id, '$1', 'Draft', ARRAY[now() + interval '30 days'],
        now() - interval '1 day', now() + interval '1 day', 1
    FROM auth.users ORDER BY created_at LIMIT 1 RETURNING id;" | head -1
}
new_user() { "${PSQL[@]}" -c "INSERT INTO auth.users (id) VALUES (gen_random_uuid()) RETURNING id;" | head -1; }

EVENT1=$(new_event 'VERIFY SCRUM-22 race last place')
EVENT2=$(new_event 'VERIFY SCRUM-22 race double withdraw')
A=$(new_user); B=$(new_user)
"${PSQL[@]}" -c "UPDATE public.event_requests SET status = 'Confirmed' WHERE id IN ('$EVENT1', '$EVENT2');" >/dev/null

cleanup() {
  "${PSQL[@]}" -c "
    DELETE FROM public.event_registrations WHERE event_request_id IN ('$EVENT1', '$EVENT2');
    UPDATE public.event_requests SET status = 'Cancelled',
        event_name = event_name || ' (left behind)' WHERE id IN ('$EVENT1', '$EVENT2');
    DELETE FROM auth.users WHERE id IN ('$A', '$B');" >/dev/null || true
  rm -rf "$OUT"
}
trap cleanup EXIT

# --- AC3-X1: A holds the only place. Session 1 withdraws A and holds the event lock
# for 3 s before committing; session 2 (B registers) starts meanwhile and must queue,
# then take the freed place. Never two Registered rows.
REG_A=$("${PSQL[@]}" -c "SELECT id FROM public.register_for_event('$EVENT1', '$A', now());" | head -1)
"${PSQL[@]}" -c "BEGIN;
  SELECT public.withdraw_registration('$REG_A', '$A', now());
  SELECT pg_sleep(3);
  COMMIT;" >"$OUT/x1_1.out" 2>&1 &
PID1=$!
sleep 1
START=$(date +%s)
set +e
"${PSQL[@]}" -c "SELECT public.register_for_event('$EVENT1', '$B', now());" >"$OUT/x1_2.out" 2>&1
STATUS2=$?
set -e
ELAPSED=$(( $(date +%s) - START ))
wait $PID1
ACTIVE=$("${PSQL[@]}" -c "SELECT count(*) FROM public.event_registrations WHERE event_request_id = '$EVENT1' AND status = 'Registered';")
WITHDRAWN=$("${PSQL[@]}" -c "SELECT count(*) FROM public.event_registrations WHERE event_request_id = '$EVENT1' AND status = 'Withdrawn';")
if [ "$STATUS2" -ne 0 ] || [ "$ACTIVE" != "1" ] || [ "$WITHDRAWN" != "1" ] || [ "$ELAPSED" -lt 1 ]; then
  echo "RACE VERIFICATION FAILED (AC3-X1): exit=$STATUS2 active=$ACTIVE withdrawn=$WITHDRAWN waited=${ELAPSED}s"
  cat "$OUT"/x1_*.out; exit 1
fi

# --- AC3-X2: two sessions withdraw the same registration. One succeeds, the other
# queues on the lock and is then refused 'already withdrawn'; withdrawn_at is set once.
REG_A2=$("${PSQL[@]}" -c "SELECT id FROM public.register_for_event('$EVENT2', '$A', now());" | head -1)
"${PSQL[@]}" -c "BEGIN;
  SELECT public.withdraw_registration('$REG_A2', '$A', now());
  SELECT pg_sleep(3);
  COMMIT;" >"$OUT/x2_1.out" 2>&1 &
PID1=$!
sleep 1
set +e
"${PSQL[@]}" -c "SELECT public.withdraw_registration('$REG_A2', '$A', now() + interval '1 hour');" >"$OUT/x2_2.out" 2>&1
STATUS2=$?
set -e
wait $PID1
STAMPS=$("${PSQL[@]}" -c "SELECT count(*) FROM public.event_registrations WHERE id = '$REG_A2' AND status = 'Withdrawn' AND withdrawn_at < now() + interval '5 minutes';")
if [ "$STATUS2" -eq 0 ] || ! grep -q "already withdrawn" "$OUT/x2_2.out" || [ "$STAMPS" != "1" ]; then
  echo "RACE VERIFICATION FAILED (AC3-X2): exit=$STATUS2 stamps=$STAMPS"
  cat "$OUT"/x2_*.out; exit 1
fi

echo "RACE VERIFICATION PASSED (AC3-X1: freed place taken once, never 2 Registered; AC3-X2: second withdrawal refused 'already withdrawn')"
