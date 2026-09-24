import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const records = new Map();
const assignments = [];
let nextAssignmentId = 1;
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
    const record = recordFields({ ...body, status: body.status ?? "Submitted" });
    records.set(record.id, record);
    if (body.coordinator_id) {
      assignments.push({
        id: nextAssignmentId++,
        event_request_id: record.id,
        coordinator_id: body.coordinator_id,
        assigned_by: "seed",
        assigned_at: new Date().toISOString(),
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

  const coordinatorMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/coordinator$/);
  const transitionMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/(review|cancellation|completion)$/);
  const submitMatch = url.pathname.match(/^\/event-requests\/([^/]+)\/submit$/);
  const match = url.pathname.match(/^\/event-requests\/([^/]+)$/);
  const id = decodeURIComponent(
    coordinatorMatch?.[1] ?? transitionMatch?.[1] ?? submitMatch?.[1] ?? match?.[1] ?? "",
  );
  const record = records.get(id);

  if (coordinatorMatch) {
    if (request.method === "POST") {
      // Assignment is an Operations Manager command; the UI for it belongs to
      // another story, so tests drive this endpoint directly.
      if (user.role !== "event_operations_manager") {
        send(response, 403, { detail: "Only an Event Operations Manager can assign a Coordinator" });
        return;
      }
      if (!record) {
        send(response, 404, { detail: "Event request not found" });
        return;
      }
      const body = await readJson(request);
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
      (action === "completion" && record.status === "Confirmed") ||
      (action === "cancellation" && CANCEL_SOURCES.has(record.status));
    if (!allowed) {
      send(response, 409, { detail: "Transition not allowed from the current status" });
      return;
    }
    const updated = {
      ...record,
      status: action === "review" ? "Under Review" : action === "completion" ? "Completed" : "Cancelled",
      updated_at: new Date().toISOString(),
    };
    records.set(id, updated);
    send(response, 200, updated);
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
