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
  if (request.method === "GET" && request.url === "/auth/me") {
    const valid = request.headers.authorization === "Bearer test-session";
    send(response, valid ? 200 : 401, valid ? { id: "playwright-user", email: "playwright@example.com" } : { detail: "Invalid session" });
    return;
  }
  if (request.method === "POST" && request.url === "/auth/login") {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const credentials = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    const valid = credentials.email === "playwright@example.com" && credentials.password === "test-password-123";
    send(response, valid ? 200 : 401, valid ? { access_token: "test-session", refresh_token: "unused", expires_in: 3600, token_type: "bearer" } : { detail: "Invalid email or password" });
    return;
  }
  send(response, 404, { detail: "Not found" });
}).listen(8104, "127.0.0.1");
