import { createServer } from "node:http";

function send(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
}

createServer(async (request, response) => {
  if (request.method === "GET" && request.url === "/health") {
    send(response, 200, { status: "ok" });
    return;
  }
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  if (request.method === "GET" && url.pathname === "/auth/users") {
    if (request.headers.authorization !== "Bearer ops-session" || url.searchParams.get("role") !== "event_coordinator") {
      send(response, 403, { detail: "Insufficient permissions" });
      return;
    }
    send(response, 200, [
      { id: "playwright-coordinator", email: "coordinator@example.com" },
      { id: "other-coordinator", email: "other.coordinator@example.com" },
    ]);
    return;
  }
  if (request.method === "GET" && request.url === "/auth/me") {
    if (request.headers.authorization === "Bearer test-session") {
      send(response, 200, { id: "playwright-user", email: "playwright@example.com", role: "event_organiser", roles: ["event_organiser"] });
      return;
    }
    if (request.headers.authorization === "Bearer coordinator-session") {
      send(response, 200, { id: "playwright-coordinator", email: "coordinator@example.com", role: "event_coordinator", roles: ["event_coordinator"] });
      return;
    }
    if (request.headers.authorization === "Bearer other-coordinator-session") {
      send(response, 200, { id: "other-coordinator", email: "other.coordinator@example.com", role: "event_coordinator", roles: ["event_coordinator"] });
      return;
    }
    if (request.headers.authorization === "Bearer ops-session") {
      send(response, 200, { id: "playwright-ops", email: "ops@example.com", role: "event_operations_manager", roles: ["event_operations_manager"] });
      return;
    }
    if (request.headers.authorization === "Bearer non-organiser-session") {
      send(response, 200, { id: "admin-user", email: "admin@example.com", role: "admin", roles: ["admin"] });
      return;
    }
    if (request.headers.authorization === "Bearer venue-session") {
      send(response, 200, { id: "playwright-venue", email: "venue@example.com", role: "venue_staff", roles: ["venue_staff"] });
      return;
    }
    if (request.headers.authorization === "Bearer tech-session") {
      send(response, 200, { id: "playwright-tech", email: "tech@example.com", role: "technical_support", roles: ["technical_support"] });
      return;
    }
    send(response, 401, { detail: "Invalid session" });
    return;
  }
  if (request.method === "POST" && request.url === "/auth/login") {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const credentials = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    const LOGINS = {
      "playwright@example.com": "test-session",
      "coordinator@example.com": "coordinator-session",
      "ops@example.com": "ops-session",
      "venue@example.com": "venue-session",
      "tech@example.com": "tech-session",
    };
    const token = credentials.password === "test-password-123" ? LOGINS[credentials.email] ?? null : null;
    send(response, token ? 200 : 401, token ? { access_token: token, refresh_token: "unused", expires_in: 3600, token_type: "bearer" } : { detail: "Invalid email or password" });
    return;
  }
  send(response, 404, { detail: "Not found" });
}).listen(8104, "127.0.0.1");
