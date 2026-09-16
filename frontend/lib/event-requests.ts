import { redirect } from "next/navigation";
import { requireAccessToken } from "./auth";

export interface EventRequest {
  id: string;
  organiser_id: string;
  status: "Draft" | "Submitted";
  event_name: string | null;
  purpose: string | null;
  description: string | null;
  proposed_date_times: string[];
  expected_attendance: number | null;
  venue_requirements: string | null;
  accessibility_needs: string | null;
  equipment_requirements: string | null;
  registration_needs: string | null;
  created_at: string;
  updated_at: string;
}

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

async function request(path: string): Promise<Response> {
  const token = await requireAccessToken();
  const response = await fetch(`${apiUrl}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (response.status === 401) redirect("/auth");
  if (!response.ok && response.status !== 404) {
    throw new Error("Event request service unavailable");
  }
  return response;
}

export async function listEventRequests(): Promise<EventRequest[]> {
  const response = await request("/event-requests");
  return response.json() as Promise<EventRequest[]>;
}

export async function getEventRequest(id: string): Promise<EventRequest | null> {
  const response = await request(`/event-requests/${encodeURIComponent(id)}`);
  return response.status === 404 ? null : response.json() as Promise<EventRequest>;
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Singapore",
  }).format(new Date(value));
}
