import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const venues = new Map();
const blocks = new Map();
const bookings = new Map();
const NOTIFICATION_SEED = "http://127.0.0.1:8107/__seed";
const REASONS = ["maintenance", "renovation", "safety", "internal_use"];
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

function invalid(body) {
  return !body.name || !body.location || !Number.isInteger(body.max_capacity) || body.max_capacity <= 0
    || invalidPrep(body.setup_minutes) || invalidPrep(body.turnaround_minutes);
}

// Dates are inclusive YYYY-MM-DD strings; a shared slot on a shared date overlaps.
function overlaps(a, b) {
  return a.start_date <= b.end_date && b.start_date <= a.end_date && a.slots.some((slot) => b.slots.includes(slot));
}

function takenFor(venueId) {
  return [
    ...[...blocks.values()].filter((b) => b.venue_id === venueId && b.status === "active"),
    ...[...bookings.values()].filter((b) => b.venue_id === venueId && b.status === "approved"),
  ];
}

function makeVenue(body) {
  const now = new Date().toISOString();
  return {
    facilities: [], accessibility_features: [], supported_layouts: [], operating_slots: ["AM", "PM", "NIGHT"],
    setup_minutes: 0, turnaround_minutes: 0,
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
    const booking = {
      id: randomUUID(), event_request_id: randomUUID(), event_name: null, expected_attendance: null,
      requirements_note: null, status: "pending", decision_reason: null, suggested_alternative: null,
      decided_by: null, decided_at: null, created_at: new Date().toISOString(), ...body,
    };
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
    const slot = url.searchParams.get("slot");
    const layout = url.searchParams.get("layout");
    const facilities = url.searchParams.getAll("facility").map((f) => f.toLowerCase());
    const access = url.searchParams.getAll("accessibility").map((a) => a.toLowerCase());
    // SCRUM-23 / SCRUM-15: a dated search skips blocked and booked slots.
    const day = url.searchParams.get("date");
    const freeOn = (v) => {
      if (!day) return true;
      const taken = takenFor(v.id);
      const free = v.operating_slots.filter((s) => !taken.some((t) => overlaps(t, { start_date: day, end_date: day, slots: [s] })));
      return slot ? free.includes(slot) : free.length > 0;
    };
    return send(response, 200, [...venues.values()].filter((v) =>
      v.status === "available"
      && freeOn(v)
      && (!capacity || v.max_capacity >= Number(capacity))
      && (!location || v.location.toLowerCase().includes(location.toLowerCase()))
      && (!slot || v.operating_slots.includes(slot))
      && (!layout || v.supported_layouts.includes(layout))
      && facilities.every((f) => v.facilities.map((x) => x.toLowerCase()).includes(f))
      && access.every((a) => v.accessibility_features.map((x) => x.toLowerCase()).includes(a))));
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
    if (need.required_slot && !target.operating_slots.includes(need.required_slot)) mismatches.push({ attribute: "operating_slot", reason: `The venue does not operate in the ${need.required_slot} slot.` });
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
      if (!body.start_date || !body.end_date || body.end_date < body.start_date || !body.slots?.length || !REASONS.includes(body.reason_category)) {
        return send(response, 422, { detail: "Invalid block" });
      }
      const block = {
        ...body, slots: ["AM", "PM", "NIGHT"].filter((s) => body.slots.includes(s)), reason_detail: body.reason_detail ?? null,
        id: randomUUID(), venue_id: venueId, status: "active", created_by: "playwright-venue", created_at: new Date().toISOString(),
      };
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
              reason_category: block.reason_category, reason_detail: block.reason_detail,
              booking_start_date: booking.start_date, booking_end_date: booking.end_date, booking_slots: booking.slots,
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
      if (target && booking.slots.some((s) => !target.operating_slots.includes(s))) codes.push("outside_operating_slots");
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
    // Like venueService, hand the saved decision to notificationService; never fail on it.
    await fetch(NOTIFICATION_SEED, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_type: `venue_booking_${booking.status}`, recipient_id: booking.requested_by,
        payload: {
          booking_request_id: booking.id, event_request_id: booking.event_request_id, event_name: booking.event_name,
          venue_id: booking.venue_id, venue_name: venues.get(booking.venue_id)?.name ?? null,
          start_date: booking.start_date, end_date: booking.end_date, slots: booking.slots,
          decision_reason: booking.decision_reason, suggested_alternative: booking.suggested_alternative,
        },
      }),
    }).catch(() => undefined);
    return send(response, 200, booking);
  }

  // Mirrors venueService's SCRUM-31 GET /venues/{id}/calendar so the availability page can
  // be driven in a browser. An active block wins over an approved booking, then a slot the
  // venue does not operate, then a venue blocked in the catalogue; it returns states only.
  const calendarPath = url.pathname.match(/^\/venues\/([^/]+)\/calendar$/);
  if (calendarPath && request.method === "GET") {
    if (!["event_coordinator", "venue_staff", "safety_officer"].includes(role)) return send(response, 403, { detail: "Insufficient permissions" });
    const target = venues.get(decodeURIComponent(calendarPath[1]));
    if (!target) return send(response, 404, { detail: "Venue not found" });
    const month = url.searchParams.get("month") ?? "";
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) return send(response, 422, { detail: "Invalid month" });
    const [year, number] = month.split("-").map(Number);
    const count = new Date(Date.UTC(year, number, 0)).getUTCDate();
    const covers = (item, date, slot) => item.start_date <= date && date <= item.end_date && item.slots.includes(slot);
    const days = Array.from({ length: count }, (_, index) => {
      const date = `${month}-${String(index + 1).padStart(2, "0")}`;
      const slots = ["AM", "PM", "NIGHT"].map((slot) => {
        let state = "open";
        if ([...blocks.values()].some((b) => b.venue_id === target.id && b.status === "active" && covers(b, date, slot))) state = "blocked";
        else if ([...bookings.values()].some((b) => b.venue_id === target.id && b.status === "approved" && covers(b, date, slot))) state = "booked";
        else if (!target.operating_slots.includes(slot)) state = "not_offered";
        else if (target.status !== "available") state = "unavailable";
        return { slot, state };
      });
      return { date, slots };
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
    const updated = { ...venue, ...changes, updated_at: new Date().toISOString() };
    venues.set(venue.id, updated);
    return send(response, 200, updated);
  }
  send(response, 404, { detail: "Not found" });
}).listen(8105, "127.0.0.1");
