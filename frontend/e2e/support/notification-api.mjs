import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const notifications = [];
const port = 8107;

// Mirrors the sessions defined in auth-api.mjs — the user id notificationService
// would resolve each token to.
const SESSIONS = {
  // AC4-X4: isolate rejection journey state from the parallel default-owner inbox.
  "change-request-owner-session": "playwright-change-request-owner",
  "test-session": "playwright-user",
  "coordinator-session": "playwright-coordinator",
  "other-coordinator-session": "other-coordinator",
  "ops-session": "playwright-ops",
  "tech-session": "playwright-tech",
};

function send(response, status, body) {
  response.writeHead(status, body === undefined ? {} : { "Content-Type": "application/json" });
  response.end(body === undefined ? undefined : JSON.stringify(body));
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
}

// The API never returns recipient_id: the inbox only ever holds the caller's own rows.
function asInboxEntry({ id, event_type, payload, read_at, created_at }) {
  return { id, event_type, payload, read_at, created_at };
}

function caller(request) {
  const token = (request.headers.authorization ?? "").replace(/^Bearer /, "");
  return SESSIONS[token] ?? null;
}

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://127.0.0.1:${port}`);

  if (request.method === "GET" && url.pathname === "/health") {
    send(response, 200, { service: "notificationService", status: "ok" });
    return;
  }

  // Test-only: store a notification as if another service had sent the event.
  if (request.method === "POST" && url.pathname === "/__seed") {
    const body = await readJson(request);
    const notification = {
      id: randomUUID(),
      event_type: body.event_type,
      recipient_id: body.recipient_id,
      payload: body.payload ?? {},
      read_at: body.read_at ?? null,
      created_at: body.created_at ?? new Date().toISOString(),
    };
    notifications.push(notification);
    send(response, 201, notification);
    return;
  }

  const userId = caller(request);
  if (!userId) {
    send(response, 401, { detail: "Invalid session" });
    return;
  }

  if (request.method === "GET" && url.pathname === "/notifications") {
    const own = notifications
      .filter((notification) => notification.recipient_id === userId)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map(asInboxEntry);
    send(response, 200, own);
    return;
  }

  const readMatch = url.pathname.match(/^\/notifications\/([^/]+)\/read$/);
  if (request.method === "PATCH" && readMatch) {
    const notification = notifications.find(
      (row) => row.id === decodeURIComponent(readMatch[1]) && row.recipient_id === userId,
    );
    if (!notification) {
      send(response, 404, { detail: "Notification not found" });
      return;
    }
    notification.read_at ??= new Date().toISOString();
    send(response, 200, asInboxEntry(notification));
    return;
  }

  send(response, 404, { detail: "Not found" });
}).listen(port, "127.0.0.1");
