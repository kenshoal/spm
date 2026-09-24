import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const venues = new Map();
const SESSIONS = {
  "test-session": "event_organiser",
  "coordinator-session": "event_coordinator",
  "ops-session": "event_operations_manager",
  "venue-session": "venue_staff",
  "tech-session": "technical_support",
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

function invalid(body) {
  return !body.name || !body.location || !Number.isInteger(body.max_capacity) || body.max_capacity <= 0;
}

function makeVenue(body) {
  const now = new Date().toISOString();
  return {
    facilities: [], accessibility_features: [], supported_layouts: [], operating_slots: ["AM", "PM", "NIGHT"],
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
    return send(response, 200, [...venues.values()].filter((v) =>
      v.status === "available"
      && (!capacity || v.max_capacity >= Number(capacity))
      && (!location || v.location.toLowerCase().includes(location.toLowerCase()))
      && (!slot || v.operating_slots.includes(slot))
      && (!layout || v.supported_layouts.includes(layout))
      && facilities.every((f) => v.facilities.map((x) => x.toLowerCase()).includes(f))
      && access.every((a) => v.accessibility_features.map((x) => x.toLowerCase()).includes(a))));
  }

  const match = url.pathname.match(/^\/venues\/([^/]+)$/);
  const venue = match ? venues.get(decodeURIComponent(match[1])) : undefined;
  if (match && request.method === "GET") return venue ? send(response, 200, venue) : send(response, 404, { detail: "Venue not found" });
  if (match && request.method === "PATCH") {
    if (role !== "venue_staff") return send(response, 403, { detail: "Insufficient permissions" });
    if (!venue) return send(response, 404, { detail: "Venue not found" });
    const updated = { ...venue, ...(await readJson(request)), updated_at: new Date().toISOString() };
    venues.set(venue.id, updated);
    return send(response, 200, updated);
  }
  send(response, 404, { detail: "Not found" });
}).listen(8105, "127.0.0.1");
