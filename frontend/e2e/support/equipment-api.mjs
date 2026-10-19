import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const items = new Map();
const history = [];
let nextHistoryId = 1;
const SESSIONS = {
  "test-session": { id: "playwright-user", role: "event_organiser" },
  "tech-session": { id: "playwright-tech", role: "technical_support" },
  "safety-session": { id: "playwright-safety", role: "safety_officer" },
};
// SCRUM-33/13 reads by event, seeded by the SCRUM-60 journey.
const requirements = [];
const reservations = [];

function send(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
}

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  if (request.method === "GET" && url.pathname === "/health") return send(response, 200, { status: "ok" });
  if (request.method === "POST" && url.pathname === "/__seed_requirement") {
    const row = { id: randomUUID(), technical_requirements: null, status: "arranged", ...(await readJson(request)) };
    requirements.push(row);
    return send(response, 201, row);
  }
  if (request.method === "POST" && url.pathname === "/__seed_reservation") {
    const row = { id: randomUUID(), ...(await readJson(request)) };
    reservations.push(row);
    return send(response, 201, row);
  }
  const user = SESSIONS[(request.headers.authorization ?? "").replace(/^Bearer /, "")];
  if (!user) return send(response, 401, { detail: "Authentication required" });
  const staffOnly = () => user.role !== "technical_support" && (send(response, 403, { detail: "Insufficient permissions" }), true);

  const byEvent = url.pathname.match(/^\/equipment-(requirements|reservations)\/by-event\/([^/]+)$/);
  if (byEvent && request.method === "GET") {
    if (!["technical_support", "safety_officer"].includes(user.role)) return send(response, 403, { detail: "Insufficient permissions" });
    const rows = byEvent[1] === "requirements" ? requirements : reservations;
    return send(response, 200, rows.filter((row) => row.event_request_id === decodeURIComponent(byEvent[2])));
  }
  if (url.pathname === "/equipment" && request.method === "GET") {
    const status = url.searchParams.get("operational_status");
    return send(response, 200, [...items.values()].filter((item) => !status || item.operational_status === status));
  }
  if (url.pathname === "/equipment" && request.method === "POST") {
    if (staffOnly()) return;
    const body = await readJson(request);
    if (!body.type || !body.home_location || !Number.isInteger(body.total_owned_quantity) || body.total_owned_quantity < 0) {
      return send(response, 422, { detail: "Invalid equipment" });
    }
    const now = new Date().toISOString();
    const item = { description: null, operational_status: "AVAILABLE", ...body, id: randomUUID(), created_by: user.id, created_at: now, updated_at: now };
    items.set(item.id, item);
    history.push({ id: nextHistoryId++, equipment_id: item.id, old_status: null, new_status: item.operational_status, reason: "Created", changed_by: user.id, changed_at: now });
    return send(response, 201, item);
  }

  const match = url.pathname.match(/^\/equipment\/([^/]+)(\/quantity|\/status|\/status\/history)?$/);
  if (!match) return send(response, 404, { detail: "Not found" });
  const item = items.get(decodeURIComponent(match[1]));
  const suffix = match[2] ?? "";
  // A mutating route (PATCH /quantity, PATCH /status) checks the caller's role
  // before looking up the id, mirroring the real backend: FastAPI's `StaffDep`
  // dependency runs before the handler ever queries for the record, so a
  // non-technical_support caller gets 403 even for an id that doesn't exist.
  // GET routes stay id-first, so any authenticated caller gets 404 for a
  // missing item.
  const isMutating = request.method === "PATCH" && (suffix === "/quantity" || suffix === "/status");
  if (isMutating && staffOnly()) return;
  if (!item) return send(response, 404, { detail: "Equipment not found" });

  if (suffix === "" && request.method === "GET") return send(response, 200, item);
  if (suffix === "/quantity" && request.method === "PATCH") {
    const body = await readJson(request);
    const updated = { ...item, total_owned_quantity: body.total_owned_quantity, updated_at: new Date().toISOString() };
    items.set(item.id, updated);
    return send(response, 200, updated);
  }
  if (suffix === "/status" && request.method === "GET") {
    const available = item.operational_status === "AVAILABLE";
    return send(response, 200, { equipment_id: item.id, operational_status: item.operational_status, available, available_quantity: available ? item.total_owned_quantity : 0 });
  }
  if (suffix === "/status" && request.method === "PATCH") {
    const body = await readJson(request);
    const now = new Date().toISOString();
    history.push({ id: nextHistoryId++, equipment_id: item.id, old_status: item.operational_status, new_status: body.new_status, reason: body.reason ?? null, changed_by: user.id, changed_at: now });
    items.set(item.id, { ...item, operational_status: body.new_status, updated_at: now });
    return send(response, 200, { equipment_id: item.id, new_status: body.new_status, changed_by: user.id, reason: body.reason ?? null });
  }
  if (suffix === "/status/history" && request.method === "GET") {
    return send(response, 200, history.filter((entry) => entry.equipment_id === item.id).sort((a, b) => b.id - a.id));
  }
  send(response, 405, { detail: "Method not allowed" });
}).listen(8106, "127.0.0.1");
