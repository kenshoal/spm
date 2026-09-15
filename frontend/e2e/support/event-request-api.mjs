import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const records = new Map();
const port = 8103;

function send(response, status, body) {
  response.writeHead(status, body === undefined ? {} : { "Content-Type": "application/json" });
  response.end(body === undefined ? undefined : JSON.stringify(body));
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
}

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://${request.headers.host}`);
  const organiserId = String(request.headers["x-organiser-id"] ?? "");

  if (request.method === "GET" && url.pathname === "/health") {
    send(response, 200, { status: "ok" });
    return;
  }

  if (!organiserId) {
    send(response, 422, { detail: "Missing organiser identity" });
    return;
  }

  if (url.pathname === "/event-requests" && request.method === "POST") {
    const now = new Date().toISOString();
    const record = {
      ...(await readJson(request)),
      id: randomUUID(),
      organiser_id: organiserId,
      status: "Draft",
      created_at: now,
      updated_at: now,
    };
    records.set(record.id, record);
    send(response, 201, record);
    return;
  }

  if (url.pathname === "/event-requests" && request.method === "GET") {
    send(
      response,
      200,
      [...records.values()].filter((record) => record.organiser_id === organiserId),
    );
    return;
  }

  const match = url.pathname.match(/^\/event-requests\/([^/]+)$/);
  const id = match ? decodeURIComponent(match[1]) : null;
  const record = id ? records.get(id) : undefined;
  if (!id || !record || record.organiser_id !== organiserId) {
    send(response, 404, { detail: "Draft not found" });
    return;
  }

  if (request.method === "GET") {
    send(response, 200, record);
    return;
  }

  if (request.method === "PATCH") {
    const updated = {
      ...record,
      ...(await readJson(request)),
      id: record.id,
      organiser_id: record.organiser_id,
      status: "Draft",
      created_at: record.created_at,
      updated_at: new Date().toISOString(),
    };
    records.set(id, updated);
    send(response, 200, updated);
    return;
  }

  if (request.method === "DELETE") {
    records.delete(id);
    send(response, 204);
    return;
  }

  send(response, 405, { detail: "Method not allowed" });
}).listen(port, "127.0.0.1");
