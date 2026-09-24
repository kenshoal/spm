import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const items = new Map();
const history = [];
let nextHistoryId = 1;
const SESSIONS = {
  "test-session": { id: "playwright-user", role: "event_organiser" },
  "tech-session": { id: "playwright-tech", role: "technical_support" },
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

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  if (request.method === "GET" && url.pathname === "/health") return send(response, 200, { status: "ok" });
  const user = SESSIONS[(request.headers.authorization ?? "").replace(/^Bearer /, "")];
  if (!user) return send(response, 401, { detail: "Authentication required" });
  const staffOnly = () => user.role !== "technical_support" && (send(response, 403, { detail: "Insufficient permissions" }), true);

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
  const item = match ? items.get(decodeURIComponent(match[1])) : undefined;
  if (!match) return send(response, 404, { detail: "Not found" });
  if (!item) return send(response, 404, { detail: "Equipment not found" });
  const suffix = match[2] ?? "";

  if (suffix === "" && request.method === "GET") return send(response, 200, item);
  if (suffix === "/quantity" && request.method === "PATCH") {
    if (staffOnly()) return;
    const body = await readJson(request);
    const updated = { ...item, total_owned_quantity: body.total_owned_quantity, updated_at: new Date().toISOString() };
    items.set(item.id, updated);
    return send(response, 200, updated);
  }
  send(response, 405, { detail: "Method not allowed" });
}).listen(8106, "127.0.0.1");
