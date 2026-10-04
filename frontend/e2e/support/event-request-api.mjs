import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const records = new Map();
const assignments = [];
const reviewDecisions = [];
const changeRequests = [];
let nextAssignmentId = 1;
let nextDecisionId = 1;
const port = 8103;

// Mirrors the sessions defined in auth-api.mjs — one identity each, with the
// role the authService would report for it.
const SESSIONS = {
  "test-session": { id: "playwright-user", role: "event_organiser" },
  "coordinator-session": { id: "playwright-coordinator", role: "event_coordinator" },
  "other-coordinator-session": { id: "other-coordinator", role: "event_coordinator" },
  "ops-session": { id: "playwright-ops", role: "event_operations_manager" },
};

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

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://${request.headers.host}`);
  const user = caller(request);

  if (request.method === "GET" && url.pathname === "/health") {
    send(response, 200, { status: "ok" });
    return;
  }

  // Test-only seed for statuses no implemented story writes yet (e.g.
  // Confirmed, which the venue/ops stories own on other branches).
  if (url.pathname === "/__seed" && request.method === "POST") {
    const body = await readJson(request);
    const { coordinator_id, review_decision, ...recordOverrides } = body;
    const record = recordFields({ ...recordOverrides, status: body.status ?? "Submitted" });
    records.set(record.id, record);
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
    send(response, 201, record);
    return;
  }

  if (url.pathname === "/event-requests" && request.method === "GET") {
    if (user.role === "event_organiser") {
      send(
        response,
        200,
        [...records.values()]
          .filter((record) => record.organiser_id === user.id)
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

  const coordinatorMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/coordinator$/);
  const transitionMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/(review|resume-review|cancellation|completion)$/);
  const decisionMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/decision$/);
  const decisionsMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/decisions$/);
  const clarificationMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/clarification-response$/);
  const changeDecisionMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/change-requests\/([^/]+)\/decision$/);
  const changeRequestsMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/change-requests$/);
  const submitMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/submit$/);
  const match = url.pathname.match(/^\/event-requests\/([^/]+)$/);
  const id = decodeURIComponent(
    coordinatorMatch?.[1] ?? transitionMatch?.[1] ?? decisionMatch?.[1]
      ?? decisionsMatch?.[1] ?? clarificationMatch?.[1] ?? changeDecisionMatch?.[1]
      ?? changeRequestsMatch?.[1] ?? submitMatch?.[1] ?? match?.[1] ?? "",
  );
  const record = records.get(id);

  if (coordinatorMatch) {
    if (request.method === "POST") {
      // Assignment is an Operations Manager command.
      if (user.role !== "event_operations_manager") {
        send(response, 403, { detail: "Only an Event Operations Manager can assign a Coordinator" });
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
        (user.role === "event_organiser" && record.organiser_id === user.id) ||
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
    if (change.status !== "Pending" || (body.decision === "Approved" && record.updated_at !== change.base_event_updated_at)) {
      send(response, 409, { detail: "Change request already decided or stale" });
      return;
    }
    if (!["Approved", "Rejected"].includes(body.decision) || (body.decision === "Rejected" && !body.reason?.trim())) {
      send(response, 422, { detail: "Invalid decision" });
      return;
    }
    if (body.decision === "Approved") {
      Object.assign(record, change.proposed_changes, { updated_at: new Date().toISOString() });
    }
    Object.assign(change, {
      status: body.decision, coordinator_id: user.id,
      decision_reason: body.reason ?? null, decided_at: new Date().toISOString(),
    });
    send(response, 200, change);
    return;
  }

  if (request.method === "GET" && match) {
    if (user.role === "event_organiser") {
      send(
        response,
        record.organiser_id === user.id ? 200 : 404,
        record.organiser_id === user.id ? record : { detail: "Event request not found" },
      );
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
      (user.role === "event_organiser" && record.organiser_id === user.id)
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
    send(response, record.organiser_id === user.id ? 403 : 404, {
      detail: "Event request not found",
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
    send(response, 204);
    return;
  }

  send(response, 405, { detail: "Method not allowed" });
}).listen(port, "127.0.0.1");
