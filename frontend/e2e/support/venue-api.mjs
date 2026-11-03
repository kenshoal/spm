import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const venues = new Map();
const blocks = new Map();
const bookings = new Map();
const holds = new Map();
const NOTIFICATION_SEED = "http://127.0.0.1:8107/__seed";
const REASONS = ["maintenance", "equipment_failure", "renovation", "safety", "internal_use", "other"];
const SESSIONS = {
  "test-session": "event_organiser",
  "coordinator-session": "event_coordinator",
  "ops-session": "event_operations_manager",
  "venue-session": "venue_staff",
  "tech-session": "technical_support",
  "safety-session": "safety_officer",
};

function send(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
}

// SCRUM-59: like venueService, setup and turnaround are 0-1020 minutes in 15-minute steps.
function invalidPrep(value) {
  return value !== undefined && !(Number.isInteger(value) && value >= 0 && value <= 1020 && value % 15 === 0);
}

// SCRUM-30: like venueService, the operating hours are 15-minute steps within 07:00-24:00, start before end.
function invalidMinute(value) {
  return value !== undefined && !(Number.isInteger(value) && value >= 420 && value <= 1440 && value % 15 === 0);
}

function invalidHours(start, end) {
  return invalidMinute(start) || invalidMinute(end) || (start !== undefined && end !== undefined && start >= end);
}

function invalid(body) {
  return !body.name || !body.location || !Number.isInteger(body.max_capacity) || body.max_capacity <= 0
    || invalidPrep(body.setup_minutes) || invalidPrep(body.turnaround_minutes)
    || invalidHours(body.operating_start_minute, body.operating_end_minute);
}

// SCRUM-65: bookings and blocks carry start_minute / end_minute; slots are the
// ones the time touches (AM 07:00-12:00, PM 12:00-18:00, NIGHT 18:00-24:00).
const SLOT_RANGES = { AM: [420, 720], PM: [720, 1080], NIGHT: [1080, 1440] };

function withTimes(item) {
  let { start_minute: start, end_minute: end } = item;
  if (start === undefined || end === undefined) {
    const ranges = (item.slots ?? []).map((s) => SLOT_RANGES[s]);
    start = Math.min(...ranges.map((r) => r[0]));
    end = Math.max(...ranges.map((r) => r[1]));
  }
  const slots = Object.entries(SLOT_RANGES).filter(([, [a, b]]) => start < b && a < end).map(([s]) => s);
  return { ...item, start_minute: start, end_minute: end, slots };
}

function validTimes(start, end) {
  return Number.isInteger(start) && Number.isInteger(end) && start % 15 === 0 && end % 15 === 0
    && start >= 420 && end <= 1440 && end > start;
}

// Dates are inclusive YYYY-MM-DD strings; a shared date and overlapping
// half-open times overlap.
function overlaps(a, b) {
  return a.start_date <= b.end_date && b.start_date <= a.end_date
    && a.start_minute < b.end_minute && b.start_minute < a.end_minute;
}

// SCRUM-66: like venueService, a time is free when its own setup and turnaround fit 07:00-24:00,
// no active block overlaps it and no approved booking overlaps it once both are padded with the
// venue's setup and turnaround. Blocks are not padded.
// SCRUM-18: a hold protects its time while active and unexpired.
const protecting = (hold) => hold.status === "active" && new Date(hold.expires_at).getTime() > Date.now();

// With withHolds, active holds count as taken too, padded like bookings.
function freeAt(venue, day, start, end, withHolds = false) {
  const setup = venue.setup_minutes ?? 0;
  const turnaround = venue.turnaround_minutes ?? 0;
  if (start - setup < 420 || end + turnaround > 1440) return false;
  const wanted = { start_date: day, end_date: day, start_minute: start, end_minute: end };
  const padded = { ...wanted, start_minute: start - setup, end_minute: end + turnaround };
  const taken = [
    ...[...bookings.values()].filter((b) => b.status === "approved"),
    ...(withHolds ? [...holds.values()].filter(protecting) : []),
  ];
  return ![...blocks.values()].some((b) => b.venue_id === venue.id && b.status === "active" && overlaps(b, wanted))
    && !taken.some((b) => b.venue_id === venue.id
      && overlaps({ ...b, start_minute: b.start_minute - setup, end_minute: b.end_minute + turnaround }, padded));
}

function makeVenue(body) {
  const now = new Date().toISOString();
  return {
    facilities: [], accessibility_features: [], supported_layouts: [], operating_slots: ["AM", "PM", "NIGHT"],
    setup_minutes: 0, turnaround_minutes: 0, operating_start_minute: 420, operating_end_minute: 1440,
    ...body, id: body.id ?? randomUUID(), status: body.status ?? "available", created_at: now, updated_at: now,
  };
}

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  if (request.method === "GET" && url.pathname === "/health") return send(response, 200, { status: "ok" });
  if (request.method === "POST" && url.pathname === "/__seed") {
    const venue = makeVenue(await readJson(request));
    venues.set(venue.id, venue);
    return send(response, 201, venue);
  }
  // Test-only: a pending booking request, as SCRUM-32 submission would create it.
  if (request.method === "POST" && url.pathname === "/__seed_booking") {
    const body = await readJson(request);
    const booking = withTimes({
      id: randomUUID(), event_request_id: randomUUID(), event_name: null, expected_attendance: null,
      requirements_note: null, status: "pending", decision_reason: null, suggested_alternative: null,
      decided_by: null, decided_at: null, cancelled_at: null, replaces_booking_id: null, created_at: new Date().toISOString(), ...body,
    });
    bookings.set(booking.id, booking);
    return send(response, 201, booking);
  }

  const role = SESSIONS[(request.headers.authorization ?? "").replace(/^Bearer /, "")];
  if (!role) return send(response, 401, { detail: "Authentication required" });

  if (url.pathname === "/venues" && request.method === "GET") return send(response, 200, [...venues.values()]);
  if (url.pathname === "/venues" && request.method === "POST") {
    if (role !== "venue_staff") return send(response, 403, { detail: "Insufficient permissions" });
    const body = await readJson(request);
    if (invalid(body)) return send(response, 422, { detail: "Invalid venue" });
    const venue = makeVenue(body);
    venues.set(venue.id, venue);
    return send(response, 201, venue);
  }

  if (url.pathname === "/venues/search" && request.method === "GET") {
    const capacity = url.searchParams.get("required_capacity");
    const location = url.searchParams.get("location");
    const startParam = url.searchParams.get("start_minute");
    const endParam = url.searchParams.get("end_minute");
    const layout = url.searchParams.get("layout");
    const facilities = url.searchParams.getAll("facility").map((f) => f.toLowerCase());
    const access = url.searchParams.getAll("accessibility").map((a) => a.toLowerCase());
    // SCRUM-23 / SCRUM-15 / SCRUM-65: a dated search skips venues blocked or
    // booked at an overlapping time, or with no free time that day. SCRUM-18: a
    // venue free except for holds is returned as tentatively held.
    const day = url.searchParams.get("date");
    const wanted = startParam !== null && endParam !== null
      ? { start_date: day, end_date: day, start_minute: Number(startParam), end_minute: Number(endParam) }
      : null;
    if ((startParam !== null || endParam !== null) && (!day || !wanted || !validTimes(wanted.start_minute, wanted.end_minute))) {
      return send(response, 422, { detail: [{ type: "invalid_times" }] });
    }
    // With only a date, the day counts when some 15-minute booking would be accepted (SCRUM-66).
    const freeOn = (v, withHolds) => {
      if (!day) return true;
      if (wanted) return freeAt(v, day, wanted.start_minute, wanted.end_minute, withHolds);
      return Array.from({ length: 68 }, (_, i) => 420 + i * 15).some((start) => freeAt(v, day, start, start + 15, withHolds));
    };
    return send(response, 200, [...venues.values()].filter((v) =>
      v.status === "available"
      && freeOn(v, false)
      && (!capacity || v.max_capacity >= Number(capacity))
      && (!location || v.location.toLowerCase().includes(location.toLowerCase()))
      && (!layout || v.supported_layouts.includes(layout))
      && facilities.every((f) => v.facilities.map((x) => x.toLowerCase()).includes(f))
      && access.every((a) => v.accessibility_features.map((x) => x.toLowerCase()).includes(a)))
      .map((v) => ({ ...v, tentatively_held: !freeOn(v, true) })));
  }

  // Mirrors venueService's POST /venues/{id}/suitability rules (SCRUM-12) so the
  // browser journey can run without the real service. It proves the screen, not
  // the real API contract; that is covered by venueService's own tests.
  const check = url.pathname.match(/^\/venues\/([^/]+)\/suitability$/);
  if (check && request.method === "POST") {
    const target = venues.get(decodeURIComponent(check[1]));
    if (!target) return send(response, 404, { detail: "Venue not found" });
    const need = await readJson(request);
    const has = (list, wanted) => list.map((x) => x.toLowerCase()).includes(wanted.toLowerCase());
    const mismatches = [];
    if (need.expected_attendance > target.max_capacity) mismatches.push({ attribute: "capacity", reason: `Expected attendance ${need.expected_attendance} exceeds the venue's maximum capacity of ${target.max_capacity}.` });
    if (need.required_layout && !target.supported_layouts.includes(need.required_layout)) mismatches.push({ attribute: "layout", reason: `The venue does not support the ${need.required_layout} layout.` });
    // SCRUM-65: every venue operates 07:00-24:00; an invalid time is a 422.
    if ((need.required_start_minute !== undefined || need.required_end_minute !== undefined)
        && !validTimes(need.required_start_minute, need.required_end_minute)) {
      return send(response, 422, { detail: [{ type: "invalid_times" }] });
    }
    const missing = (need.required_facilities ?? []).filter((f) => !has(target.facilities, f));
    if (missing.length) mismatches.push({ attribute: "facilities", reason: `Missing required facility: ${missing.join(", ")}.` });
    const lacking = (need.required_accessibility ?? []).filter((a) => !has(target.accessibility_features, a));
    if (lacking.length) mismatches.push({ attribute: "accessibility", reason: `Missing required accessibility feature: ${lacking.join(", ")}.` });
    return send(response, 200, { venue_id: target.id, suitable: mismatches.length === 0, mismatches });
  }

  // Mirrors venueService's block and SCRUM-15 decision rules so the browser
  // journeys run without the real service; the real rules are covered by
  // venueService's own tests and database verification.
  const blockPath = url.pathname.match(/^\/venues\/([^/]+)\/blocks$/);
  if (blockPath) {
    // SCRUM-60: the Safety Officer reads blocks as restrictions; only Venue Staff write.
    if (role !== "venue_staff" && !(role === "safety_officer" && request.method === "GET")) {
      return send(response, 403, { detail: "Insufficient permissions" });
    }
    const venueId = decodeURIComponent(blockPath[1]);
    if (!venues.has(venueId)) return send(response, 404, { detail: "Venue not found" });
    if (request.method === "GET") return send(response, 200, [...blocks.values()].filter((b) => b.venue_id === venueId));
    if (request.method === "POST") {
      const body = await readJson(request);
      if (!body.start_date || !body.end_date || body.end_date < body.start_date || body.slots !== undefined
          || !validTimes(body.start_minute, body.end_minute) || !REASONS.includes(body.reason_category)) {
        return send(response, 422, { detail: "Invalid block" });
      }
      const block = withTimes({
        ...body, reason_detail: body.reason_detail ?? null,
        id: randomUUID(), venue_id: venueId, status: "active", created_by: "playwright-venue", created_at: new Date().toISOString(),
      });
      blocks.set(block.id, block);
      // SCRUM-23 AC3: like venueService, alert the Coordinator of each approved,
      // not-yet-ended booking the new block overlaps; never fail the block.
      const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Singapore" });
      const affected = [...bookings.values()].filter((b) =>
        b.venue_id === venueId && b.status === "approved" && b.end_date >= today && overlaps(b, block));
      for (const booking of affected) {
        await fetch(NOTIFICATION_SEED, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event_type: "venue_block_affects_booking", recipient_id: booking.requested_by,
            payload: {
              block_id: block.id, booking_request_id: booking.id, event_request_id: booking.event_request_id,
              event_name: booking.event_name, venue_id: venueId, venue_name: venues.get(venueId)?.name ?? null,
              block_start_date: block.start_date, block_end_date: block.end_date, block_slots: block.slots,
              block_start_minute: block.start_minute, block_end_minute: block.end_minute,
              reason_category: block.reason_category, reason_detail: block.reason_detail,
              booking_start_date: booking.start_date, booking_end_date: booking.end_date, booking_slots: booking.slots,
              booking_start_minute: booking.start_minute, booking_end_minute: booking.end_minute,
            },
          }),
        }).catch(() => undefined);
      }
      return send(response, 201, block);
    }
  }

  if (url.pathname === "/booking-requests" && request.method === "GET") {
    if (role !== "venue_staff") return send(response, 403, { detail: "Insufficient permissions" });
    const wanted = url.searchParams.get("status") ?? "pending";
    return send(response, 200, [...bookings.values()].filter((b) => b.status === wanted).sort((a, b) => a.created_at.localeCompare(b.created_at)));
  }

  // Mirrors venueService's SCRUM-61 reads and cancel so the coordinator's event page
  // can be driven in a browser. The mock does not check the event's assignment; the
  // real service does (venueService's own tests and the real-stack check cover that).
  const eventBookings = url.pathname.match(/^\/booking-requests\/event\/([^/]+)$/);
  if (eventBookings && request.method === "GET") {
    if (!["venue_staff", "event_coordinator", "safety_officer"].includes(role)) return send(response, 403, { detail: "Insufficient permissions" });
    const eventId = decodeURIComponent(eventBookings[1]);
    return send(response, 200, [...bookings.values()].filter((b) => b.event_request_id === eventId).sort((a, b) => a.created_at.localeCompare(b.created_at)));
  }
  const cancelPath = url.pathname.match(/^\/booking-requests\/([^/]+)\/cancel$/);
  if (cancelPath && request.method === "POST") {
    if (role !== "event_coordinator") return send(response, 403, { detail: "Insufficient permissions" });
    const booking = bookings.get(decodeURIComponent(cancelPath[1]));
    if (!booking) return send(response, 404, { detail: "Booking request not found" });
    if (!["pending", "approved"].includes(booking.status)) return send(response, 409, { detail: "Booking request cannot be cancelled" });
    Object.assign(booking, { status: "cancelled", cancelled_by: "playwright-coordinator", cancelled_at: new Date().toISOString() });
    return send(response, 200, booking);
  }

  // Mirrors venueService's SCRUM-63 POST /booking-requests/{id}/replacement: a pending request at
  // another venue, for the same event, dates and times, linked to the replaced booking. Like the
  // cancel above, the mock checks neither the event's assignment nor the venue-block flag; the real
  // service and the database verifier cover those.
  const replacementPath = url.pathname.match(/^\/booking-requests\/([^/]+)\/replacement$/);
  if (replacementPath && request.method === "POST") {
    if (role !== "event_coordinator") return send(response, 403, { detail: "Insufficient permissions" });
    const original = bookings.get(decodeURIComponent(replacementPath[1]));
    if (!original) return send(response, 404, { detail: "Booking request not found" });
    const body = await readJson(request);
    if (typeof body.venue_id !== "string" || !body.venue_id || Object.keys(body).some((key) => key !== "venue_id")) {
      return send(response, 422, { detail: "Invalid replacement" });
    }
    const target = venues.get(body.venue_id);
    if (!target) return send(response, 404, { detail: "Venue not found" });
    if (original.status !== "approved") return send(response, 409, { detail: "Booking is not approved" });
    if (target.id === original.venue_id) return send(response, 422, { detail: "A replacement must be at a different venue" });
    if ([...bookings.values()].some((b) => b.replaces_booking_id === original.id && ["pending", "approved"].includes(b.status))) {
      return send(response, 409, { detail: "A replacement has already been requested" });
    }
    const replacement = withTimes({
      id: randomUUID(), venue_id: target.id, requested_by: "playwright-coordinator", event_request_id: original.event_request_id,
      event_name: original.event_name, expected_attendance: original.expected_attendance, requirements_note: original.requirements_note,
      start_date: original.start_date, end_date: original.end_date, start_minute: original.start_minute, end_minute: original.end_minute,
      status: "pending", decision_reason: null, suggested_alternative: null, decided_by: null, decided_at: null,
      cancelled_by: null, cancelled_at: null, replaces_booking_id: original.id, created_at: new Date().toISOString(),
    });
    bookings.set(replacement.id, replacement);
    // SCRUM-67: the approved bookings it overlaps at the new venue, setup and turnaround included.
    // Dates and times only, as the real service returns; a warning, never a refusal.
    const hold = (b) => [b.start_minute - (target.setup_minutes ?? 0), b.end_minute + (target.turnaround_minutes ?? 0)];
    const [wantedStart, wantedEnd] = hold(replacement);
    const conflicts = [...bookings.values()]
      .filter((b) => b.venue_id === target.id && b.status === "approved" && b.id !== replacement.id
        && b.start_date <= replacement.end_date && replacement.start_date <= b.end_date
        && wantedStart < hold(b)[1] && hold(b)[0] < wantedEnd)
      .map((b) => ({ start_date: b.start_date, end_date: b.end_date, start_minute: b.start_minute, end_minute: b.end_minute }));
    return send(response, 201, { ...replacement, conflicts });
  }

  const decisionPath = url.pathname.match(/^\/booking-requests\/([^/]+)\/decision$/);
  if (decisionPath && request.method === "POST") {
    if (role !== "venue_staff") return send(response, 403, { detail: "Insufficient permissions" });
    const booking = bookings.get(decodeURIComponent(decisionPath[1]));
    if (!booking) return send(response, 404, { detail: "Booking request not found" });
    const body = await readJson(request);
    const reason = typeof body.reason === "string" ? body.reason.trim() : "";
    const alternative = typeof body.suggested_alternative === "string" ? body.suggested_alternative.trim() : "";
    if (!["approved", "rejected"].includes(body.decision) || (body.decision === "rejected" && !reason)
        || (body.decision === "approved" && (reason || alternative))) {
      return send(response, 422, { detail: "Invalid decision" });
    }
    if (booking.status !== "pending") return send(response, 409, { detail: "Booking request has already been decided" });
    if (body.decision === "approved") {
      const target = venues.get(booking.venue_id);
      const codes = [];
      if (!target || target.status !== "available") codes.push("venue_unavailable");
      const blocking = [...blocks.values()].filter((b) => b.venue_id === booking.venue_id && b.status === "active" && overlaps(b, booking));
      const clashing = [...bookings.values()].filter((b) => b.venue_id === booking.venue_id && b.status === "approved" && b.id !== booking.id && overlaps(b, booking));
      if (blocking.length) codes.push("active_block");
      if (clashing.length) codes.push("booking_conflict");
      if (codes.length) {
        return send(response, 409, { detail: {
          message: "Approval refused", refusal_codes: codes,
          conflicting_block_ids: blocking.map((b) => b.id), conflicting_booking_ids: clashing.map((b) => b.id),
        } });
      }
    }
    Object.assign(booking, {
      status: body.decision, decision_reason: body.decision === "rejected" ? reason : null,
      suggested_alternative: body.decision === "rejected" && alternative ? alternative : null,
      decided_by: "playwright-venue", decided_at: new Date().toISOString(),
    });
    // SCRUM-63 AC5: an approved replacement cancels the booking it replaces if that is still approved.
    if (booking.status === "approved" && booking.replaces_booking_id) {
      const replaced = bookings.get(booking.replaces_booking_id);
      if (replaced?.status === "approved") {
        Object.assign(replaced, { status: "cancelled", cancelled_by: "playwright-venue", cancelled_at: new Date().toISOString() });
      }
    }
    // Like venueService, hand the saved decision to notificationService; never fail on it.
    await fetch(NOTIFICATION_SEED, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_type: `venue_booking_${booking.status}`, recipient_id: booking.requested_by,
        payload: {
          booking_request_id: booking.id, event_request_id: booking.event_request_id, event_name: booking.event_name,
          venue_id: booking.venue_id, venue_name: venues.get(booking.venue_id)?.name ?? null,
          start_date: booking.start_date, end_date: booking.end_date, slots: booking.slots,
          start_minute: booking.start_minute, end_minute: booking.end_minute,
          decision_reason: booking.decision_reason, suggested_alternative: booking.suggested_alternative,
        },
      }),
    }).catch(() => undefined);
    return send(response, 200, booking);
  }

  // SCRUM-18: tentative holds, mirroring venueService. A hold protects its time
  // (see protecting), padded like a booking; converting creates a pending
  // booking linked to the hold.
  const holdsPath = url.pathname.match(/^\/venues\/([^/]+)\/holds$/);
  if (holdsPath && request.method === "POST") {
    if (role !== "event_coordinator") return send(response, 403, { detail: "Insufficient permissions" });
    const target = venues.get(decodeURIComponent(holdsPath[1]));
    if (!target) return send(response, 404, { detail: "Venue not found" });
    const body = await readJson(request);
    const expires = new Date(body?.expires_at ?? "").getTime();
    if (!validTimes(body?.start_minute, body?.end_minute) || !(expires > Date.now()) || expires > Date.now() + 7 * 864e5) {
      return send(response, 422, { detail: "Invalid hold" });
    }
    const setup = target.setup_minutes ?? 0;
    const turnaround = target.turnaround_minutes ?? 0;
    const wanted = { start_date: body.start_date, end_date: body.end_date, start_minute: body.start_minute - setup, end_minute: body.end_minute + turnaround };
    const pad = (item) => ({ ...item, start_minute: item.start_minute - setup, end_minute: item.end_minute + turnaround });
    const clashBookings = [...bookings.values()].filter((b) => b.venue_id === target.id && b.status === "approved" && overlaps(pad(b), wanted));
    const clashHolds = [...holds.values()].filter((h) => h.venue_id === target.id && protecting(h) && overlaps(pad(h), wanted));
    if (clashBookings.length || clashHolds.length) {
      return send(response, 409, { detail: {
        refusal_codes: [...(clashBookings.length ? ["booking_conflict"] : []), ...(clashHolds.length ? ["hold_conflict"] : [])],
        conflicting_block_ids: [], conflicting_booking_ids: clashBookings.map((b) => b.id), conflicting_hold_ids: clashHolds.map((h) => h.id),
      } });
    }
    const hold = {
      id: randomUUID(), venue_id: target.id, event_request_id: body.event_request_id, start_date: body.start_date,
      end_date: body.end_date, start_minute: body.start_minute, end_minute: body.end_minute, expires_at: body.expires_at,
      status: "active", booking_request_id: null, placed_by: "playwright-coordinator", placed_at: new Date().toISOString(), closed_at: null,
    };
    holds.set(hold.id, hold);
    return send(response, 201, hold);
  }
  if (url.pathname === "/venue-holds" && request.method === "GET") {
    if (role !== "event_coordinator") return send(response, 403, { detail: "Insufficient permissions" });
    const eventId = url.searchParams.get("event_request_id");
    return send(response, 200, [...holds.values()].filter((h) => h.event_request_id === eventId));
  }
  const holdAction = url.pathname.match(/^\/venue-holds\/([^/]+)\/(release|convert)$/);
  if (holdAction && request.method === "POST") {
    if (role !== "event_coordinator") return send(response, 403, { detail: "Insufficient permissions" });
    const hold = holds.get(decodeURIComponent(holdAction[1]));
    if (!hold) return send(response, 404, { detail: "Venue hold not found" });
    if (!protecting(hold)) return send(response, 409, { detail: "Hold is no longer active" });
    if (holdAction[2] === "release") {
      Object.assign(hold, { status: "released", closed_at: new Date().toISOString() });
      return send(response, 200, hold);
    }
    const booking = withTimes({
      id: randomUUID(), venue_id: hold.venue_id, event_request_id: hold.event_request_id, requested_by: "playwright-coordinator",
      event_name: null, expected_attendance: null, requirements_note: null, start_date: hold.start_date, end_date: hold.end_date,
      start_minute: hold.start_minute, end_minute: hold.end_minute, status: "pending", decision_reason: null,
      suggested_alternative: null, decided_by: null, decided_at: null, created_at: new Date().toISOString(),
    });
    bookings.set(booking.id, booking);
    hold.booking_request_id = booking.id;
    return send(response, 201, { hold, booking });
  }

  // Mirrors venueService's GET /venues/{id}/calendar (SCRUM-31, on times by SCRUM-69) so the
  // availability page can be driven in a browser. Each date is a partition of 07:00-24:00 into
  // blocked, booked and free ranges: an active block wins over an approved booking (which is split
  // around it), touching ranges of one state merge, and a venue blocked in the catalogue marks the
  // date unavailable with no free time. It returns times only.
  const calendarPath = url.pathname.match(/^\/venues\/([^/]+)\/calendar$/);
  if (calendarPath && request.method === "GET") {
    if (!["event_coordinator", "venue_staff", "safety_officer"].includes(role)) return send(response, 403, { detail: "Insufficient permissions" });
    const target = venues.get(decodeURIComponent(calendarPath[1]));
    if (!target) return send(response, 404, { detail: "Venue not found" });
    const month = url.searchParams.get("month") ?? "";
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) return send(response, 422, { detail: "Invalid month" });
    const [year, number] = month.split("-").map(Number);
    const count = new Date(Date.UTC(year, number, 0)).getUTCDate();
    const merge = (ranges) => {
      const out = [];
      for (const [start, end] of [...ranges].sort((a, b) => a[0] - b[0])) {
        if (out.length && start <= out[out.length - 1][1]) out[out.length - 1][1] = Math.max(out[out.length - 1][1], end);
        else out.push([start, end]);
      }
      return out;
    };
    const subtract = (ranges, cuts) => {
      const out = [];
      for (const [start, end] of ranges) {
        let cursor = start;
        for (const [cutStart, cutEnd] of cuts) {
          if (cutEnd <= cursor || cutStart >= end) continue;
          if (cutStart > cursor) out.push([cursor, cutStart]);
          cursor = Math.max(cursor, cutEnd);
        }
        if (cursor < end) out.push([cursor, end]);
      }
      return out;
    };
    const clip = (item) => [Math.max(item.start_minute, 420), Math.min(item.end_minute, 1440)];
    const days = Array.from({ length: count }, (_, index) => {
      const date = `${month}-${String(index + 1).padStart(2, "0")}`;
      const on = (item) => item.start_date <= date && date <= item.end_date;
      const blocked = merge([...blocks.values()].filter((b) => b.venue_id === target.id && b.status === "active" && on(b)).map(clip).filter(([a, b]) => a < b));
      // SCRUM-66: a booking occupies the venue's setup before it and turnaround after it.
      const padded = (b) => ({ start_minute: b.start_minute - (target.setup_minutes ?? 0), end_minute: b.end_minute + (target.turnaround_minutes ?? 0) });
      const booked = subtract(merge([...bookings.values()].filter((b) => b.venue_id === target.id && b.status === "approved" && on(b)).map((b) => clip(padded(b))).filter(([a, b]) => a < b)), blocked);
      // SCRUM-18: active holds show as held where no block or booking is.
      const held = subtract(merge([...holds.values()].filter((h) => h.venue_id === target.id && protecting(h) && on(h)).map((h) => clip(padded(h))).filter(([a, b]) => a < b)), merge([...blocked, ...booked]));
      const unavailable = target.status !== "available";
      const entries = [...blocked.map(([a, b]) => ({ state: "blocked", start_minute: a, end_minute: b })), ...booked.map(([a, b]) => ({ state: "booked", start_minute: a, end_minute: b })), ...held.map(([a, b]) => ({ state: "held", start_minute: a, end_minute: b }))]
        .sort((x, y) => x.start_minute - y.start_minute);
      const free = unavailable ? [] : subtract([[420, 1440]], merge([...blocked, ...booked, ...held])).map(([a, b]) => ({ start_minute: a, end_minute: b }));
      return { date, unavailable, entries, free };
    });
    return send(response, 200, { venue_id: target.id, month, days });
  }

  const match = url.pathname.match(/^\/venues\/([^/]+)$/);
  const venue = match ? venues.get(decodeURIComponent(match[1])) : undefined;
  if (match && request.method === "GET") return venue ? send(response, 200, venue) : send(response, 404, { detail: "Venue not found" });
  if (match && request.method === "PATCH") {
    if (role !== "venue_staff") return send(response, 403, { detail: "Insufficient permissions" });
    if (!venue) return send(response, 404, { detail: "Venue not found" });
    const changes = await readJson(request);
    if (invalidPrep(changes.setup_minutes) || invalidPrep(changes.turnaround_minutes)) return send(response, 422, { detail: "Invalid venue" });
    if (invalidHours(changes.operating_start_minute ?? venue.operating_start_minute, changes.operating_end_minute ?? venue.operating_end_minute)) return send(response, 422, { detail: "Invalid operating hours" });
    const updated = { ...venue, ...changes, updated_at: new Date().toISOString() };
    venues.set(venue.id, updated);
    return send(response, 200, updated);
  }
  send(response, 404, { detail: "Not found" });
}).listen(8105, "127.0.0.1");
