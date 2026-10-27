#!/usr/bin/env bash
# SCRUM-24 AC2-X1 / AC3-X1 / AC7-X1 / AC9-X1 (cross-cutting): two sessions race
# for one place or one offer. Usage: DSN=postgresql://... ./verify_event_waitlist_race.sh
# Needs the SCRUM-24 migration plus 0048 and 0062 applied, an existing auth user,
# and a DISPOSABLE database: it commits fixtures. The script removes the waitlist
# rows, registrations and test users and leaves Cancelled events named
# 'VERIFY SCRUM-24 race ... (left behind)' (status history is immutable).
# Prints RACE VERIFICATION PASSED or exits 1.
set -euo pipefail
: "${DSN:?set DSN to the disposable database}"
PSQL=(psql -X -At -v ON_ERROR_STOP=1 "$DSN")
OUT=$(mktemp -d)

new_event() {
  "${PSQL[@]}" -c "
    INSERT INTO public.event_requests (organiser_id, event_name, status, proposed_date_times,
        registration_opens_at, registration_closes_at, registration_capacity)
    SELECT id, '$1', 'Draft', ARRAY[now() + interval '200 days'],
        now() - interval '1 day', now() + interval '1 day', 1
    FROM auth.users ORDER BY created_at LIMIT 1 RETURNING id;" | head -1
}
new_user() { "${PSQL[@]}" -c "INSERT INTO auth.users (id) VALUES (gen_random_uuid()) RETURNING id;" | head -1; }

EVENTS=$(for i in 1 2 3 4; do new_event "VERIFY SCRUM-24 race $i"; done)
E1=$(echo "$EVENTS" | sed -n 1p); E2=$(echo "$EVENTS" | sed -n 2p)
E3=$(echo "$EVENTS" | sed -n 3p); E4=$(echo "$EVENTS" | sed -n 4p)
OWNER=$("${PSQL[@]}" -c "SELECT id FROM auth.users ORDER BY created_at LIMIT 1;" | head -1)
K=$(gen_random_uuid)  # the assigned Coordinator, varchar(64) like 0011
A=$(new_user); B=$(new_user); F=$(new_user)
"${PSQL[@]}" -c "UPDATE public.event_requests SET status = 'Confirmed'
    WHERE id IN ('$E1', '$E2', '$E3', '$E4');
  INSERT INTO public.event_coordinator_assignments (event_request_id, coordinator_id, assigned_by)
    VALUES ('$E2', '$K', '$OWNER');" >/dev/null

cleanup() {
  "${PSQL[@]}" -c "
    DELETE FROM public.waitlist_notification_outbox o USING public.event_waitlist_entries e
      WHERE o.entry_id = e.id AND e.event_request_id IN ('$E1', '$E2', '$E3', '$E4');
    DELETE FROM public.event_waitlist_place_offers p USING public.event_waitlist_places w
      WHERE p.place_id = w.id AND w.event_request_id IN ('$E1', '$E2', '$E3', '$E4');
    DELETE FROM public.event_waitlist_places WHERE event_request_id IN ('$E1', '$E2', '$E3', '$E4');
    DELETE FROM public.event_waitlist_entries WHERE event_request_id IN ('$E1', '$E2', '$E3', '$E4');
    DELETE FROM public.event_registrations WHERE event_request_id IN ('$E1', '$E2', '$E3', '$E4');
    UPDATE public.event_requests SET status = 'Cancelled',
        event_name = event_name || ' (left behind)' WHERE id IN ('$E1', '$E2', '$E3', '$E4');
    DELETE FROM auth.users WHERE id IN ('$A', '$B', '$F');" >/dev/null || true
  rm -rf "$OUT"
}
trap cleanup EXIT

full_with_one_waiting() {  # $1=event, $2=waiter: R holds the place, the waiter queues
  local reg
  reg=$("${PSQL[@]}" -c "SELECT id FROM public.register_for_event('$1', '$OWNER', now());" | head -1)
  "${PSQL[@]}" -c "SELECT public.join_waitlist('$1', '$2', now()) IS NOT NULL;" >/dev/null
  echo "$reg"
}
offer_first_waiter() {  # $1=event, $2=holder: withdraw so the first waiter is offered
  "${PSQL[@]}" -c "SELECT public.withdraw_registration('$1', '$2', now()) IS NOT NULL;" >/dev/null
}

# --- AC2-X1: session 1 withdraws R (promotion to A inside the transaction) and
# holds the event lock for 3 s; session 2 tries a direct registration meanwhile
# and must queue on the lock, then be refused 'event full': the offered place
# counts against capacity (D6). Never more than capacity Registered + Offered.
REG=$(full_with_one_waiting "$E1" "$A")
"${PSQL[@]}" -c "BEGIN;
  SELECT public.withdraw_registration('$REG', '$OWNER', now());
  SELECT pg_sleep(3);
  COMMIT;" >"$OUT/x1_1.out" 2>&1 &
PID1=$!
sleep 1
START=$(date +%s)
set +e
"${PSQL[@]}" -c "SELECT public.register_for_event('$E1', '$F', now());" >"$OUT/x1_2.out" 2>&1
STATUS2=$?
set -e
ELAPSED=$(( $(date +%s) - START ))
wait $PID1
OFFERED=$("${PSQL[@]}" -c "SELECT count(*) FROM public.event_waitlist_entries
  WHERE event_request_id = '$E1' AND status = 'Offered';")
ACTIVE=$("${PSQL[@]}" -c "SELECT count(*) FROM public.event_registrations
  WHERE event_request_id = '$E1' AND status = 'Registered';")
if [ "$STATUS2" -eq 0 ] || ! grep -q "event full" "$OUT/x1_2.out" \
    || [ "$OFFERED" != "1" ] || [ "$ACTIVE" != "0" ] || [ "$ELAPSED" -lt 1 ]; then
  echo "RACE VERIFICATION FAILED (AC2-X1): exit=$STATUS2 offered=$OFFERED active=$ACTIVE waited=${ELAPSED}s"
  cat "$OUT"/x1_*.out; exit 1
fi

# --- AC3-X1: A holds the offer. Session 1 accepts and holds the event lock for
# 3 s; session 2 (the Coordinator choosing B) queues, then is refused
# 'no open place'. Never A registered and B offered for the same place.
REG=$(full_with_one_waiting "$E2" "$A")
"${PSQL[@]}" -c "SELECT public.join_waitlist('$E2', '$B', now() + interval '1 second') IS NOT NULL;" >/dev/null
ENTRY_A=$("${PSQL[@]}" -c "SELECT id FROM public.event_waitlist_entries
  WHERE event_request_id = '$E2' AND attendee_id = '$A';")
offer_first_waiter "$E2" "$OWNER"
"${PSQL[@]}" -c "BEGIN;
  SELECT public.accept_waitlist_offer('$ENTRY_A', '$A', now() + interval '1 hour');
  SELECT pg_sleep(3);
  COMMIT;" >"$OUT/x3_1.out" 2>&1 &
PID1=$!
sleep 1
set +e
ENTRY_B=$("${PSQL[@]}" -c "SELECT id FROM public.event_waitlist_entries
  WHERE event_request_id = '$E2' AND attendee_id = '$B';")
"${PSQL[@]}" -c "SELECT public.choose_waitlist_recipient('$E2', '$ENTRY_B', '$K', now() + interval '1 hour');" >"$OUT/x3_2.out" 2>&1
STATUS2=$?
set -e
wait $PID1
REG_A=$("${PSQL[@]}" -c "SELECT count(*) FROM public.event_registrations
  WHERE event_request_id = '$E2' AND attendee_id = '$A' AND status = 'Registered';")
STILL_WAITING=$("${PSQL[@]}" -c "SELECT count(*) FROM public.event_waitlist_entries
  WHERE id = '$ENTRY_B' AND status = 'Waiting';")
if [ "$STATUS2" -eq 0 ] || ! grep -q "no open place" "$OUT/x3_2.out" \
    || [ "$REG_A" != "1" ] || [ "$STILL_WAITING" != "1" ]; then
  echo "RACE VERIFICATION FAILED (AC3-X1): exit=$STATUS2 regA=$REG_A entryB=$STILL_WAITING"
  cat "$OUT"/x3_*.out; exit 1
fi

# --- AC7-X1: session 1 withdraws A's offer and holds the event lock; session 2
# accepts the same offer and must be refused. Never both A registered and the
# place passed on.
REG=$(full_with_one_waiting "$E3" "$A")
"${PSQL[@]}" -c "SELECT public.join_waitlist('$E3', '$B', now() + interval '1 second') IS NOT NULL;" >/dev/null
ENTRY_A=$("${PSQL[@]}" -c "SELECT id FROM public.event_waitlist_entries
  WHERE event_request_id = '$E3' AND attendee_id = '$A';")
offer_first_waiter "$E3" "$OWNER"
"${PSQL[@]}" -c "BEGIN;
  SELECT public.withdraw_from_waitlist('$ENTRY_A', '$A', now() + interval '10 hours');
  SELECT pg_sleep(3);
  COMMIT;" >"$OUT/x7_1.out" 2>&1 &
PID1=$!
sleep 1
set +e
"${PSQL[@]}" -c "SELECT public.accept_waitlist_offer('$ENTRY_A', '$A', now() + interval '10 hours');" >"$OUT/x7_2.out" 2>&1
STATUS2=$?
set -e
wait $PID1
WITHDRAWN=$("${PSQL[@]}" -c "SELECT count(*) FROM public.event_waitlist_entries
  WHERE id = '$ENTRY_A' AND status = 'Withdrawn';")
REG_A=$("${PSQL[@]}" -c "SELECT count(*) FROM public.event_registrations
  WHERE event_request_id = '$E3' AND attendee_id = '$A' AND status = 'Registered';")
HANDED_ON=$("${PSQL[@]}" -c "SELECT count(*) FROM public.event_waitlist_entries
  WHERE event_request_id = '$E3' AND status = 'Offered';")
if [ "$STATUS2" -eq 0 ] || [ "$WITHDRAWN" != "1" ] || [ "$REG_A" != "0" ] \
    || [ "$HANDED_ON" != "1" ]; then
  echo "RACE VERIFICATION FAILED (AC7-X1): exit=$STATUS2 withdrawn=$WITHDRAWN regA=$REG_A handedOn=$HANDED_ON"
  cat "$OUT"/x7_*.out; exit 1
fi

# --- AC9-X1: session 1 runs the timer (A's offer expires, the place is handed
# to B) holding the event lock; session 2 registers directly and must be
# refused: there is no moment when the place is free while B is eligible.
REG=$(full_with_one_waiting "$E4" "$A")
"${PSQL[@]}" -c "SELECT public.join_waitlist('$E4', '$B', now() + interval '1 second') IS NOT NULL;" >/dev/null
offer_first_waiter "$E4" "$OWNER"
"${PSQL[@]}" -c "BEGIN;
  SELECT public.process_waitlist_timers(now() + interval '73 hours');
  SELECT pg_sleep(3);
  COMMIT;" >"$OUT/x9_1.out" 2>&1 &
PID1=$!
sleep 1
START=$(date +%s)
set +e
"${PSQL[@]}" -c "SELECT public.register_for_event('$E4', '$F', now() + interval '73 hours');" >"$OUT/x9_2.out" 2>&1
STATUS2=$?
set -e
ELAPSED=$(( $(date +%s) - START ))
wait $PID1
B_OFFERED=$("${PSQL[@]}" -c "SELECT count(*) FROM public.event_waitlist_entries
  WHERE event_request_id = '$E4' AND attendee_id = '$B' AND status = 'Offered';")
REG_F=$("${PSQL[@]}" -c "SELECT count(*) FROM public.event_registrations
  WHERE event_request_id = '$E4' AND attendee_id = '$F' AND status = 'Registered';")
if [ "$STATUS2" -eq 0 ] || ! grep -q "event full" "$OUT/x9_2.out" \
    || [ "$B_OFFERED" != "1" ] || [ "$REG_F" != "0" ] || [ "$ELAPSED" -lt 1 ]; then
  echo "RACE VERIFICATION FAILED (AC9-X1): exit=$STATUS2 bOffered=$B_OFFERED regF=$REG_F waited=${ELAPSED}s"
  cat "$OUT"/x9_*.out; exit 1
fi

echo "RACE VERIFICATION PASSED (AC2-X1: the offered place is never taken directly; AC3-X1: accept beats a later Coordinator choice; AC7-X1: withdraw beats a stale accept; AC9-X1: hand-over leaves no registerable gap)"
