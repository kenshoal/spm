import { redirect } from "next/navigation";
import { requireAccessToken } from "./auth";

// Reads a JSON resource for a server component. A 404 is a normal "not found"
// outcome (null), and so is a 422 — the backends use it for a malformed id or
// query (e.g. a non-UUID equipment id, an invalid date) rather than a real
// outage; any other failure throws so the page can show an outage.
export async function getJson<T>(baseUrl: string, path: string): Promise<T | null> {
  const token = await requireAccessToken();
  const response = await fetch(`${baseUrl}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (response.status === 401) redirect("/auth");
  if (response.status === 404 || response.status === 422) return null;
  if (!response.ok) throw new Error(`${path} failed with status ${response.status}`);
  return response.json() as Promise<T>;
}

// Sends a JSON write for a server action. It never redirects: callers wrap it
// in try/catch for network failures, and redirect() inside that try would be
// swallowed — so the caller checks 401 after the try.
export async function sendJson(
  baseUrl: string,
  path: string,
  method: "POST" | "PATCH",
  body: unknown,
): Promise<Response> {
  const token = await requireAccessToken();
  return fetch(`${baseUrl}${path}`, {
    method,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
}

export async function readDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}
