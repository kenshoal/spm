import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const records = new Map();
const assignments = [];
const reviewDecisions = [];
const changeRequests = [];
const statusHistory = [];
// SCRUM-19 UI fixtures only; the real rules live in eventRequestService's own tests.
const technicalSupportRequirements = new Map();
const technicalSupportAssignments = new Map();
const SKILL_TAGS = new Set(["audio_visual", "lighting", "it_network", "livestream"]);
const SUPPORT_STATUSES = new Set(["Approved", "Planning", "Confirmed"]);
// Mirrors the technical_support session defined in auth-api.mjs.
const TECHNICAL_SUPPORT_STAFF = [
  { id: "playwright-tech", email: "technical_support@example.com", tags: ["audio_visual", "it_network"] },
];
// Prepared UI fixture storage only; real permissions and clear atomicity have separate API/PG tests.
const arrangementReviews = new Map();
// AC3-X20: prepared registration evidence/outcomes only; native callers own authorisation and atomicity.
const registrationReviews = new Map();
const registrationAcknowledgements = new Map();
// AC3-X11: prepared advisory response only; the real planner is tested outside this browser double.
const datePlanBookings = new Map();
// AC3-X32: prepared date editor context/outcomes only; no planner or transaction rules in the browser fixture.
const bookingPlanOutcomes = new Map();
let nextHistoryId = 1;
let nextAssignmentId = 1;
let nextDecisionId = 1;
const port = 8103;

// Mirrors the sessions defined in auth-api.mjs — one identity each, with the
// role the authService would report for it.
const SESSIONS = {
  // AC4-X4: isolate rejection journey state from the parallel default-owner inbox.
  "change-request-owner-session": { id: "playwright-change-request-owner", role: "event_organiser" },
  "test-session": { id: "playwright-user", role: "event_organiser" },
  "colleague-session": { id: "playwright-colleague", role: "event_organiser" },
  "coordinator-session": { id: "playwright-coordinator", role: "event_coordinator" },
  "other-coordinator-session": { id: "other-coordinator", role: "event_coordinator" },
  "ops-session": { id: "playwright-ops", role: "event_operations_manager" },
  "venue-session": { id: "playwright-venue", role: "venue_staff" },
  "tech-session": { id: "playwright-tech", role: "technical_support" },
  "safety-session": { id: "playwright-safety", role: "safety_officer" },
};
const safetyReviews = [];

const CANCEL_SOURCES = new Set([
  "Submitted",
  "Under Review",
  "Changes Requested",
  "Approved",
  "Planning",
  "Confirmed",
]);

const COORDINATOR_IDS = new Set(["playwright-coordinator", "other-coordinator", "reassign-coordinator"]);
const TERMINAL = new Set(["Completed", "Cancelled", "Rejected"]);

// SCRUM-39: organisers in one client organisation view each other's
// non-Draft requests, mirroring EventRequestService.get_viewable.
const ORGANISATIONS = { "playwright-user": "acme", "playwright-colleague": "acme" };

function organiserCanView(user, record) {
  if (user.role !== "event_organiser") return false;
  if (record.organiser_id === user.id) return true;
  const organisation = ORGANISATIONS[record.organiser_id];
  return record.status !== "Draft" && organisation !== undefined
    && organisation === ORGANISATIONS[user.id];
}

function send(response, status, body) {
  response.writeHead(status, body === undefined ? {} : { "Content-Type": "application/json" });
  response.end(body === undefined ? undefined : JSON.stringify(body));
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
}

function caller(request) {
  const token = (request.headers.authorization ?? "").replace(/^Bearer /, "");
  return SESSIONS[token] ?? null;
}

function latestAssignmentFor(eventRequestId) {
  const matches = assignments.filter((row) => row.event_request_id === eventRequestId);
  return matches.reduce(
    (latest, row) => (latest === null || row.id > latest.id ? row : latest),
    null,
  );
}

function requestsAssignedTo(coordinatorId) {
  return [...records.values()]
    .filter((record) => latestAssignmentFor(record.id)?.coordinator_id === coordinatorId)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}

function recordFields(overrides = {}) {
  const now = new Date().toISOString();
  return {
    event_name: null,
    purpose: null,
    description: null,
    proposed_date_times: [],
    expected_attendance: null,
    venue_requirements: null,
    accessibility_needs: null,
    equipment_requirements: null,
    registration_needs: null,
    ...overrides,
    id: overrides.id ?? randomUUID(),
    created_at: overrides.created_at ?? now,
    updated_at: overrides.updated_at ?? now,
  };
}

// Mirrors the persisted history contract; real transaction behaviour is verified in Postgres.
function recordHistory(record, previousStatus, actor, source, entryKind = "transition") {
  statusHistory.push({
    id: nextHistoryId++, event_request_id: record.id,
    previous_status: previousStatus, new_status: record.status,
    actor_id: actor?.id ?? null, actor_role: actor?.role ?? "system",
    source, entry_kind: entryKind, occurred_at: new Date().toISOString(),
  });
}

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://${request.headers.host}`);
  const user = caller(request);

  if (request.method === "GET" && url.pathname === "/health") {
    send(response, 200, { status: "ok" });
    return;
  }

  // AC3-X32: install exact responses for one known proposal without recalculating dates, writing lifecycle history or faking conflict decisions.
  if (url.pathname === "/__prepare_change_plan" && request.method === "POST") {
    const prepared = await readJson(request);
    const change = changeRequests.find(row => row.id === prepared.change_request_id && row.event_request_id === prepared.event_request_id);
    if (!change || !records.has(prepared.event_request_id)) {
      send(response, 404, { detail: "Unknown prepared proposal" }); return;
    }
    bookingPlanOutcomes.set(change.id, structuredClone(prepared));
    send(response, 201, { prepared: true }); return;
  }

  // Test-only seed for statuses no implemented story writes yet (e.g.
  // Confirmed, which the venue/ops stories own on other branches).
  if (url.pathname === "/__seed" && request.method === "POST") {
    const body = await readJson(request);
    const { coordinator_id, review_decision, arrangement_reviews, date_plan_bookings, registration_reviews, registration_acknowledgements, ...recordOverrides } = body;
    const record = recordFields({ ...recordOverrides, status: body.status ?? "Submitted" });
    records.set(record.id, record);
    if (date_plan_bookings) datePlanBookings.set(record.id, structuredClone(date_plan_bookings));
    for (const row of registration_reviews ?? []) registrationReviews.set(row.id, { ...row, event_request_id: record.id });
    for (const row of registration_acknowledgements ?? []) registrationAcknowledgements.set(row.id, { ...row, event_request_id: record.id });
    for (const review of arrangement_reviews ?? []) {
      arrangementReviews.set(review.id, { ...review, event_request_id: record.id, cleared_at: null, cleared_by: null });
    }
    recordHistory(record, null, null, "history.recording_started", "baseline");
    if (coordinator_id) {
      assignments.push({
        id: nextAssignmentId++,
        event_request_id: record.id,
        coordinator_id,
        assigned_by: "seed",
        assigned_at: new Date().toISOString(),
      });
    }
    if (review_decision) {
      reviewDecisions.push({
        id: nextDecisionId++,
        event_request_id: record.id,
        coordinator_id: review_decision.coordinator_id ?? coordinator_id,
        decision_status: review_decision.decision_status,
        reason: review_decision.reason ?? null,
        decided_at: review_decision.decided_at ?? new Date().toISOString(),
        organiser_response: review_decision.organiser_response ?? null,
        responded_at: review_decision.responded_at ?? null,
      });
    }
    send(response, 201, record);
    return;
  }

  if (!user) {
    send(response, 401, { detail: "Authentication required" });
    return;
  }

  if (url.pathname === "/event-requests" && request.method === "POST") {
    if (user.role !== "event_organiser") {
      send(response, 403, { detail: "Insufficient permissions" });
      return;
    }
    const record = recordFields({
      ...(await readJson(request)),
      organiser_id: user.id,
      status: "Draft",
    });
    records.set(record.id, record);
    recordHistory(record, null, user, "event_request.created", "created");
    send(response, 201, record);
    return;
  }

  if (url.pathname === "/event-requests/submissions" && request.method === "POST") {
    if (user.role !== "event_organiser") {
      send(response, 403, { detail: "Insufficient permissions" });
      return;
    }
    const record = recordFields({
      ...(await readJson(request)),
      organiser_id: user.id,
      status: "Submitted",
    });
    records.set(record.id, record);
    recordHistory(record, null, user, "event_request.created", "created");
    send(response, 201, record);
    return;
  }

  // AC3-X20: return seeded records and a predeclared acknowledgement response; no review producer or role rules are duplicated here.
  const registrationReadMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/registration-reviews$/);
  const registrationAckMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/registration-reviews\/([^/]+)\/acknowledge$/);
  if (request.method === "GET" && registrationReadMatch) {
    send(response, 200, [...registrationReviews.values()].filter((row) => row.event_request_id === registrationReadMatch[1]));
    return;
  }
  if (request.method === "POST" && registrationAckMatch) {
    const row = registrationAcknowledgements.get(registrationAckMatch[2]);
    if (!row || row.event_request_id !== registrationAckMatch[1]) {
      send(response, 404, { detail: { code: "REGISTRATION_REVIEW_NOT_FOUND" } }); return;
    }
    registrationReviews.set(row.id, structuredClone(row));
    send(response, 200, row);
    return;
  }

  // AC5-X9 UI canned endpoints: these simple query/storage responses do not establish backend authorisation.
  const arrangementEventMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/arrangement-reviews$/);
  if (request.method === "GET" && arrangementEventMatch) {
    send(response, 200, [...arrangementReviews.values()].filter((row) => row.event_request_id === arrangementEventMatch[1] && row.cleared_at === null));
    return;
  }
  if (request.method === "GET" && url.pathname === "/arrangement-reviews") {
    send(response, 200, [...arrangementReviews.values()].filter((row) => row.arrangement === url.searchParams.get("arrangement") && row.cleared_at === null));
    return;
  }
  const arrangementClearMatch = url.pathname.match(/^\/arrangement-reviews\/([^/]+)\/clear$/);
  if (request.method === "POST" && arrangementClearMatch) {
    const row = arrangementReviews.get(arrangementClearMatch[1]);
    if (!row) { send(response, 404, { detail: { code: "ARRANGEMENT_REVIEW_NOT_FOUND" } }); return; }
    const cleared = { ...row, cleared_at: "2026-10-16T03:00:00Z", cleared_by: user.id };
    arrangementReviews.set(row.id, cleared);
    send(response, 200, cleared);
    return;
  }

  if (url.pathname === "/event-requests" && request.method === "GET") {
    if (user.role === "event_organiser") {
      send(
        response,
        200,
        [...records.values()]
          .filter((record) => organiserCanView(user, record))
          .sort((a, b) => b.created_at.localeCompare(a.created_at)),
      );
      return;
    }
    if (user.role === "event_coordinator") {
      send(response, 200, requestsAssignedTo(user.id));
      return;
    }
    send(response, 403, { detail: "Insufficient permissions" });
    return;
  }

  if (url.pathname === "/event-requests/assigned-to-me" && request.method === "GET") {
    if (user.role !== "event_coordinator") {
      send(response, 403, { detail: "Insufficient permissions" });
      return;
    }
    send(response, 200, requestsAssignedTo(user.id));
    return;
  }

  if (url.pathname === "/event-requests/awaiting-assignment" && request.method === "GET") {
    if (user.role !== "event_operations_manager") {
      send(response, 403, { detail: "Insufficient permissions" });
      return;
    }
    send(response, 200, [...records.values()]
      .filter((record) => record.status === "Submitted" && latestAssignmentFor(record.id) === null)
      .sort((a, b) => b.created_at.localeCompare(a.created_at)));
    return;
  }

  if (url.pathname === "/event-requests/assignments" && request.method === "GET") {
    if (user.role !== "event_operations_manager") {
      send(response, 403, { detail: "Insufficient permissions" });
      return;
    }
    send(response, 200, [...records.values()]
      .filter((record) => record.status !== "Draft" && !TERMINAL.has(record.status) && latestAssignmentFor(record.id) !== null)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map((record) => ({ event_request: record, assignment: latestAssignmentFor(record.id) })));
    return;
  }

  // SCRUM-60: mirrors eventRequestService's safety queue and decision. The real
  // rules (role re-check, P0004/P0005, SCRUM-64 flags) are covered by its own
  // tests and the database verification.
  if (url.pathname === "/event-requests/safety-queue" && request.method === "GET") {
    if (user.role !== "safety_officer") return send(response, 403, { detail: "Insufficient permissions" });
    send(response, 200, [...records.values()].filter((r) => r.status === "Safety Review")
      .sort((a, b) => a.updated_at.localeCompare(b.updated_at)));
    return;
  }
  const safetyDecisionMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/safety-decision$/);
  if (safetyDecisionMatch && request.method === "POST") {
    if (user.role !== "safety_officer") return send(response, 403, { detail: "Insufficient permissions" });
    const target = records.get(decodeURIComponent(safetyDecisionMatch[1]));
    if (!target) return send(response, 404, { detail: "Event request not found" });
    if (target.status !== "Safety Review") return send(response, 409, { detail: "Not waiting for a safety check" });
    const body = await readJson(request);
    const previous = target.status;
    target.status = body.decision === "approved" ? "Confirmed" : "Planning";
    target.updated_at = new Date().toISOString();
    safetyReviews.unshift({
      id: randomUUID(), event_request_id: target.id, decision: body.decision, reason: body.reason ?? null,
      targets: body.targets ?? [], decided_by: user.id, decided_at: target.updated_at,
    });
    recordHistory(target, previous, user, `safety.${body.decision === "approved" ? "approval" : "changes_requested"}`);
    send(response, 200, target);
    return;
  }
  const safetyReviewsMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/safety-reviews$/);
  if (safetyReviewsMatch && request.method === "GET") {
    const eventId = decodeURIComponent(safetyReviewsMatch[1]);
    send(response, 200, safetyReviews.filter((review) => review.event_request_id === eventId));
    return;
  }

  // SCRUM-19: mirrors eventRequestService's technical support endpoints. The
  // real rules (locked rechecks inside the database functions, notification
  // emission) are covered by its own API and database tests; this only
  // prepares the UI fixtures the panel needs. Additive to the routes above.
  const techViewMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/technical-support$/);
  const techReqMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/technical-support\/requirements$/);
  const techCandMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/technical-support\/requirements\/([^/]+)\/candidates$/);
  const techAssignMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/technical-support\/requirements\/([^/]+)\/assignments$/);
  if (techViewMatch || techReqMatch || techCandMatch || techAssignMatch) {
    const eventId = decodeURIComponent(
      techViewMatch?.[1] ?? techReqMatch?.[1] ?? techCandMatch?.[1] ?? techAssignMatch?.[1] ?? "",
    );
    const requirementId = techCandMatch ? decodeURIComponent(techCandMatch[2]) : techAssignMatch ? decodeURIComponent(techAssignMatch[2]) : null;
    const event = records.get(eventId);
    const requirements = technicalSupportRequirements.get(eventId) ?? [];
    const latestCoordinator = latestAssignmentFor(eventId)?.coordinator_id;
    const isAssignedCoordinator = user.role === "event_coordinator" && latestCoordinator === user.id;
    const isTechnicalSupport = user.role === "technical_support";
    const requirement = requirementId ? requirements.find((row) => row.id === requirementId) : null;

    if (techViewMatch && request.method === "GET") {
      if (!isAssignedCoordinator && !isTechnicalSupport) {
        send(response, 403, { detail: "Insufficient permissions" });
        return;
      }
      if (!event) {
        send(response, 404, { detail: { code: "event_request_not_found", message: "Event request not found" } });
        return;
      }
      if (user.role === "event_coordinator" && latestCoordinator !== user.id) {
        send(response, 404, { detail: { code: "event_request_not_found", message: "Event request not found" } });
        return;
      }
      send(response, 200, requirements.map((row) => ({
        ...row,
        assigned_staff: (technicalSupportAssignments.get(row.id) ?? [])
          .sort((a, b) => a.assigned_at.localeCompare(b.assigned_at) || a.staff_id.localeCompare(b.staff_id)),
      })));
      return;
    }

    if (techReqMatch && request.method === "POST") {
      if (!isAssignedCoordinator) {
        send(response, isTechnicalSupport ? 403 : 404, { detail: { code: "event_request_not_found", message: "Event request not found" } });
        return;
      }
      if (!event || !SUPPORT_STATUSES.has(event.status)) {
        send(response, 409, { detail: { code: "support_not_allowed", message: "Technical support is not allowed in this status" } });
        return;
      }
      const body = await readJson(request);
      const description = typeof body.description === "string" ? body.description.trim() : "";
      if (description.length < 1 || description.length > 2000 || !SKILL_TAGS.has(body.skill_tag)) {
        send(response, 422, { detail: "Invalid requirement" });
        return;
      }
      const row = {
        id: randomUUID(),
        event_request_id: eventId,
        description,
        skill_tag: body.skill_tag,
        recorded_by: user.id,
        recorded_at: new Date().toISOString(),
      };
      requirements.push(row);
      technicalSupportRequirements.set(eventId, requirements);
      send(response, 201, { ...row, assigned_staff: [] });
      return;
    }

    if (!event) {
      send(response, 404, { detail: { code: "event_request_not_found", message: "Event request not found" } });
      return;
    }
    if (!isAssignedCoordinator) {
      send(response, isTechnicalSupport ? 403 : 404, { detail: { code: "event_request_not_found", message: "Event request not found" } });
      return;
    }
    if (!requirement) {
      send(response, 404, { detail: { code: "requirement_not_found", message: "Technical support requirement not found" } });
      return;
    }

    if (techCandMatch && request.method === "GET") {
      const assigned = new Set((technicalSupportAssignments.get(requirementId) ?? []).map((row) => row.staff_id));
      send(response, 200, TECHNICAL_SUPPORT_STAFF
        .filter((staff) => staff.tags.includes(requirement.skill_tag))
        .map((staff) => ({ staff_id: staff.id, already_assigned: assigned.has(staff.id) })));
      return;
    }

    if (techAssignMatch && request.method === "POST") {
      if (!SUPPORT_STATUSES.has(event.status)) {
        send(response, 409, { detail: { code: "support_not_allowed", message: "Technical support is not allowed in this status" } });
        return;
      }
      const body = await readJson(request);
      const staff = TECHNICAL_SUPPORT_STAFF.find((person) => person.id === body.staff_id);
      if (!staff || !staff.tags.includes(requirement.skill_tag)) {
        send(response, 409, { detail: { code: "staff_not_suitable", message: "The staff member does not hold the required skill" } });
        return;
      }
      const assignments = technicalSupportAssignments.get(requirementId) ?? [];
      if (assignments.some((row) => row.staff_id === body.staff_id)) {
        send(response, 409, { detail: { code: "already_assigned", message: "Already assigned to this requirement" } });
        return;
      }
      const row = {
        staff_id: body.staff_id,
        assigned_by: user.id,
        assigned_at: new Date().toISOString(),
      };
      assignments.push(row);
      technicalSupportAssignments.set(requirementId, assignments);
      send(response, 201, { id: randomUUID(), requirement_id: requirementId, event_request_id: eventId, ...row });
      return;
    }

    send(response, 405, { detail: "Method not allowed" });
    return;
  }
  const historyMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/status-history$/);
  const coordinatorMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/coordinator$/);
  const transitionMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/(review|resume-review|cancellation|completion)$/);
  const decisionMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/decision$/);
  const decisionsMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/decisions$/);
  const clarificationMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/clarification-response$/);
  const bookingPlanMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/change-requests\/([^/]+)\/booking-plan$/);
  const datePlanMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/change-requests\/([^/]+)\/date-plan$/);
  const changeDecisionMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/change-requests\/([^/]+)\/decision$/);
  const changeRequestsMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/change-requests$/);
  const submitMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/submit$/);
  const match = url.pathname.match(/^\/event-requests\/([^/]+)$/);
  const id = decodeURIComponent(
    historyMatch?.[1] ?? coordinatorMatch?.[1] ?? transitionMatch?.[1] ?? decisionMatch?.[1]
      ?? decisionsMatch?.[1] ?? clarificationMatch?.[1] ?? bookingPlanMatch?.[1] ?? datePlanMatch?.[1] ?? changeDecisionMatch?.[1]
      ?? changeRequestsMatch?.[1] ?? submitMatch?.[1] ?? match?.[1] ?? "",
  );
  const record = records.get(id);

  if (coordinatorMatch) {
    if (request.method === "POST") {
      // Assignment is an Event Coordinator Lead command.
      if (user.role !== "event_operations_manager") {
        send(response, 403, { detail: "Only an Event Coordinator Lead can assign a Coordinator" });
        return;
      }
      if (!record) {
        send(response, 404, { detail: "Event request not found" });
        return;
      }
      const body = await readJson(request);
      if (record.status === "Draft" || TERMINAL.has(record.status)) {
        send(response, 409, { detail: `Cannot assign a Coordinator to a ${record.status} request` });
        return;
      }
      if (!COORDINATOR_IDS.has(body.coordinator_id)) {
        send(response, 409, { detail: "The selected user is not an Event Coordinator" });
        return;
      }
      const row = {
        id: nextAssignmentId++,
        event_request_id: id,
        coordinator_id: body.coordinator_id,
        assigned_by: user.id,
        assigned_at: new Date().toISOString(),
      };
      assignments.push(row);
      send(response, 201, row);
      return;
    }

    if (request.method === "GET") {
      if (!record) {
        send(response, 404, { detail: "Event request not found" });
        return;
      }

      const assignment = latestAssignmentFor(id);
      const canRead =
        user.role === "event_operations_manager" ||
        organiserCanView(user, record) ||
        (user.role === "event_coordinator" && assignment?.coordinator_id === user.id);

      if (!canRead) {
        const eligibleRole =
          user.role === "event_organiser" || user.role === "event_coordinator";
        send(response, eligibleRole ? 404 : 403, {
          detail: eligibleRole ? "Event request not found" : "Insufficient permissions",
        });
        return;
      }

      send(
        response,
        assignment ? 200 : 404,
        assignment ?? { detail: "Coordinator assignment not found" },
      );
      return;
    }
  }

  if (!id || !record) {
    send(response, 404, { detail: "Event request not found" });
    return;
  }

  if (historyMatch) {
    if (request.method !== "GET") {
      send(response, 405, { detail: "Method not allowed" });
      return;
    }
    const canRead = organiserCanView(user, record)
      || (user.role === "event_coordinator" && latestAssignmentFor(id)?.coordinator_id === user.id);
    if (!canRead) {
      const eligibleRole = ["event_organiser", "event_coordinator"].includes(user.role);
      send(response, eligibleRole ? 404 : 403, { detail: {
        code: eligibleRole ? "HISTORY_NOT_FOUND" : "HISTORY_FORBIDDEN",
        message: "Status history is not accessible",
      } });
      return;
    }
    if (record.history_unavailable) {
      send(response, 502, { detail: "Status history unavailable" });
      return;
    }
    // Test-only competing writer: the details read has finished before this history lookup.
    // A one-shot real-looking transition makes the two valid responses disagree in time.
    if (record.history_read_transition === "Under Review" && record.status === "Submitted") {
      delete record.history_read_transition;
      const previous = record.status;
      record.status = "Under Review";
      record.updated_at = new Date().toISOString();
      recordHistory(record, previous, { id: "playwright-coordinator", role: "event_coordinator" }, "coordinator.review");
    }
    send(response, 200, statusHistory.filter((entry) => entry.event_request_id === id)
      .sort((a, b) => a.occurred_at.localeCompare(b.occurred_at) || a.id - b.id));
    return;
  }

  if (bookingPlanMatch && request.method === "GET") {
    const prepared = bookingPlanOutcomes.get(decodeURIComponent(bookingPlanMatch[2]));
    if (!prepared || prepared.event_request_id !== id) { send(response, 404, { detail: "Change request not found" }); return; }
    send(response, 200, structuredClone(prepared.context)); return;
  }

  // AC3-X11: read a frozen response; do not calculate shifts, mutate bookings or approve the Pending proposal here.
  if (datePlanMatch && request.method === "GET") {
    if (user.role !== "event_coordinator" || latestAssignmentFor(id)?.coordinator_id !== user.id) {
      send(response, 403, { detail: "Only the assigned coordinator can access this change" });
      return;
    }
    const changeId = decodeURIComponent(datePlanMatch[2]);
    if (!changeRequests.some((change) => change.id === changeId && change.event_request_id === id)) {
      send(response, 404, { detail: "Change request not found" });
      return;
    }
    const prepared = datePlanBookings.get(id);
    if (!prepared) {
      send(response, 502, { detail: "Date change plan unavailable" });
      return;
    }
    send(response, 200, { event_request_id: id, change_request_id: changeId, advisory: true, bookings: structuredClone(prepared) });
    return;
  }

  if (changeRequestsMatch && request.method === "GET") {
    const assigned = latestAssignmentFor(id)?.coordinator_id === user.id;
    const canRead =
      (user.role === "event_organiser" && record.organiser_id === user.id)
      || (user.role === "event_coordinator" && assigned);
    if (!canRead) {
      send(response, ["event_organiser", "event_coordinator"].includes(user.role) ? 404 : 403, { detail: "Event request not found" });
      return;
    }
    send(response, 200, changeRequests.filter((change) => change.event_request_id === id).toReversed());
    return;
  }

  if (changeRequestsMatch && request.method === "POST") {
    if (user.role !== "event_organiser" || record.organiser_id !== user.id) {
      send(response, user.role === "event_organiser" ? 404 : 403, { detail: "Event request not found" });
      return;
    }
    if (!["Approved", "Planning"].includes(record.status)
      || changeRequests.some((change) => change.event_request_id === id && change.status === "Pending")) {
      send(response, 409, { detail: "Change request not allowed" });
      return;
    }
    const body = await readJson(request);
    const { explanation, ...proposed_changes } = body;
    if (!explanation?.trim() || Object.keys(proposed_changes).length === 0) {
      send(response, 422, { detail: "Invalid change request" });
      return;
    }
    const change = {
      id: randomUUID(), event_request_id: id, organiser_id: user.id,
      status: "Pending", explanation: explanation.trim(), proposed_changes,
      base_event_updated_at: record.updated_at, coordinator_id: null,
      decision_reason: null, created_at: new Date().toISOString(), decided_at: null,
    };
    changeRequests.push(change);
    send(response, 201, change);
    return;
  }

  if (changeDecisionMatch && request.method === "POST") {
    if (user.role !== "event_coordinator" || latestAssignmentFor(id)?.coordinator_id !== user.id) {
      send(response, 403, { detail: "Only the assigned Coordinator can decide this change" });
      return;
    }
    const changeId = decodeURIComponent(changeDecisionMatch[2]);
    const change = changeRequests.find((item) => item.id === changeId && item.event_request_id === id);
    const body = await readJson(request);
    if (!change) {
      send(response, 404, { detail: "Change request not found" });
      return;
    }
    if (!["Approved", "Rejected"].includes(body.decision)) {
      send(response, 422, { detail: "Invalid change decision" });
      return;
    }
    const prepared = bookingPlanOutcomes.get(change.id);
    if (prepared && body.decision === "Approved") {
      if (JSON.stringify(body.booking_plan) !== JSON.stringify(prepared.expected_booking_plan)) {
        send(response, 422, { detail: "Browser did not submit the prepared complete booking plan" }); return;
      }
      records.set(id, structuredClone(prepared.saved_event));
      Object.assign(change, structuredClone(prepared.saved_change));
      send(response, 200, change); return;
    }
    const fields = Object.keys(change.proposed_changes);
    if (body.decision === "Approved" && !fields.every((key) => ["expected_attendance", "venue_requirements", "equipment_requirements"].includes(key))) {
      send(response, 409, { detail: { code: "CHANGE_DECISIONS_UNAVAILABLE", message: "Date and registration changes remain unavailable." } });
      return;
    }
    if (body.decision === "Rejected" && (!body.reason?.trim() || body.reason.trim().length > 2000)) {
      send(response, 422, { detail: "Enter a rejection reason" });
      return;
    }
    if (change.status !== "Pending" || !["Approved", "Planning"].includes(record.status)
        || (body.decision === "Approved" && change.base_event_updated_at !== record.updated_at)) {
      send(response, 409, { detail: "The change cannot be decided in its current state" });
      return;
    }
    // AC3-X6: canned browser response only; native tests own actual atomic application/64 flags and locked authorisation.
    if (body.decision === "Approved") records.set(id, { ...record, ...change.proposed_changes, updated_at: new Date().toISOString() });
    change.status = body.decision;
    change.coordinator_id = user.id;
    change.decision_reason = body.reason?.trim() || null;
    change.decided_at = new Date().toISOString();
    send(response, 200, change);
    return;
  }

  if (request.method === "GET" && match) {
    if (user.role === "event_organiser") {
      const visible = organiserCanView(user, record);
      send(response, visible ? 200 : 404, visible ? record : { detail: "Event request not found" });
      return;
    }
    if (user.role === "event_coordinator") {
      const assigned = latestAssignmentFor(id)?.coordinator_id === user.id;
      send(
        response,
        assigned ? 200 : 404,
        assigned ? record : { detail: "Event request not found" },
      );
      return;
    }
    send(response, 403, { detail: "Insufficient permissions" });
    return;
  }

  if (request.method === "POST" && transitionMatch) {
    if (user.role !== "event_coordinator") {
      send(response, 403, { detail: "Insufficient permissions" });
      return;
    }
    if (latestAssignmentFor(id)?.coordinator_id !== user.id) {
      send(response, 403, { detail: "Only the assigned Coordinator can change this request" });
      return;
    }
    const [, , action] = transitionMatch;
    const allowed =
      (action === "review" && record.status === "Submitted") ||
      (action === "resume-review" && record.status === "Changes Requested"
        && reviewDecisions.some((decision) =>
          decision.event_request_id === id
          && decision.decision_status === "Changes Requested"
          && decision.organiser_response)) ||
      (action === "completion" && record.status === "Confirmed") ||
      (action === "cancellation" && CANCEL_SOURCES.has(record.status));
    if (!allowed) {
      send(response, 409, { detail: "Transition not allowed from the current status" });
      return;
    }
    const updated = {
      ...record,
      status: action === "review" || action === "resume-review" ? "Under Review" : action === "completion" ? "Completed" : "Cancelled",
      updated_at: new Date().toISOString(),
    };
    records.set(id, updated);
    recordHistory(updated, record.status, user, `coordinator.${action.replaceAll("-", "_")}`);
    send(response, 200, updated);
    return;
  }

  if (request.method === "POST" && decisionMatch) {
    if (user.role !== "event_coordinator") {
      send(response, 403, { detail: "Insufficient permissions" });
      return;
    }
    if (latestAssignmentFor(id)?.coordinator_id !== user.id) {
      send(response, 403, { detail: "Only the assigned Coordinator can decide this request" });
      return;
    }
    if (record.status !== "Under Review") {
      send(response, 409, { detail: "Request is not under review" });
      return;
    }
    const body = await readJson(request);
    if (!["Approved", "Changes Requested", "Rejected"].includes(body.decision)) {
      send(response, 422, { detail: "Invalid decision" });
      return;
    }
    if (["Changes Requested", "Rejected"].includes(body.decision) && !body.reason?.trim()) {
      send(response, 422, { detail: "Reason required" });
      return;
    }
    reviewDecisions.push({
      id: nextDecisionId++,
      event_request_id: id,
      coordinator_id: user.id,
      decision_status: body.decision,
      reason: body.reason ?? null,
      decided_at: new Date().toISOString(),
      organiser_response: null,
      responded_at: null,
    });
    const updated = {
      ...record,
      status: body.decision,
      updated_at: new Date().toISOString(),
    };
    records.set(id, updated);
    recordHistory(updated, record.status, user, "coordinator.decision");
    send(response, 200, updated);
    return;
  }

  if (request.method === "GET" && decisionsMatch) {
    if (record.review_history_unavailable) {
      send(response, 503, { detail: "Review activity unavailable" });
      return;
    }
    const assigned = latestAssignmentFor(id)?.coordinator_id === user.id;
    const canRead =
      organiserCanView(user, record)
      || (user.role === "event_coordinator" && assigned);
    if (!canRead) {
      send(response, ["event_organiser", "event_coordinator"].includes(user.role) ? 404 : 403, {
        detail: "Event request not found",
      });
      return;
    }
    send(response, 200, reviewDecisions
      .filter((decision) => decision.event_request_id === id)
      .sort((a, b) => b.decided_at.localeCompare(a.decided_at)));
    return;
  }

  if (user.role !== "event_organiser" || record.organiser_id !== user.id) {
    const forbidden = organiserCanView(user, record);
    send(response, forbidden ? 403 : 404, {
      detail: forbidden ? "Insufficient permissions" : "Event request not found",
    });
    return;
  }

  if (request.method === "POST" && submitMatch) {
    if (record.status !== "Draft") {
      send(response, 409, { detail: "Only Draft requests can be submitted" });
      return;
    }
    const updated = {
      ...record,
      ...(await readJson(request)),
      status: "Submitted",
      updated_at: new Date().toISOString(),
    };
    records.set(id, updated);
    recordHistory(updated, record.status, user, "event_request.submitted");
    send(response, 200, updated);
    return;
  }

  if (request.method === "POST" && clarificationMatch) {
    if (record.status !== "Changes Requested") {
      send(response, 409, { detail: "Request is not awaiting clarification" });
      return;
    }
    const latest = reviewDecisions
      .filter((decision) => decision.event_request_id === id && decision.decision_status === "Changes Requested")
      .sort((a, b) => b.id - a.id)[0];
    const body = await readJson(request);
    if (!latest || latest.organiser_response || !body.response?.trim()) {
      send(response, 409, { detail: "Clarification response not allowed" });
      return;
    }
    latest.organiser_response = body.response.trim();
    latest.responded_at = new Date().toISOString();
    send(response, 200, latest);
    return;
  }

  if (request.method === "PATCH") {
    if (record.status !== "Draft") {
      send(response, 409, { detail: "Only Draft requests can be updated" });
      return;
    }
    const updated = {
      ...record,
      ...(await readJson(request)),
      status: "Draft",
      updated_at: new Date().toISOString(),
    };
    records.set(id, updated);
    send(response, 200, updated);
    return;
  }

  if (request.method === "DELETE") {
    if (record.status !== "Draft") {
      send(response, 409, { detail: "Only Draft requests can be deleted" });
      return;
    }
    records.delete(id);
    for (let i = statusHistory.length - 1; i >= 0; i--) {
      if (statusHistory[i].event_request_id === id) statusHistory.splice(i, 1);
    }
    send(response, 204);
    return;
  }

  send(response, 405, { detail: "Method not allowed" });
}).listen(port, "127.0.0.1");
