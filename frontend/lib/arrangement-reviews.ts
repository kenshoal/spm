import { redirect } from "next/navigation";
import { requireAccessToken } from "./auth";

export type Arrangement = "venue_booking" | "equipment_reservation";
export const arrangementRoles: Record<Arrangement, string> = {
  venue_booking: "venue_staff",
  equipment_reservation: "technical_support",
};
export const arrangementLabels: Record<Arrangement, string> = {
  venue_booking: "Venue booking",
  equipment_reservation: "Equipment reservation",
};
export interface ArrangementReview {
  id: string;
  event_request_id: string;
  arrangement: Arrangement;
  arrangement_id: string;
  trigger_id: string;
  trigger_type: "event_change" | "equipment_unavailable" | "safety_recheck" | "venue_timing_change" | "venue_block";
  changed_fields: string[];
  reason: string;
  raised_at: string;
  cleared_at: string | null;
  cleared_by: string | null;
}
const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

async function readReviews(path: string): Promise<ArrangementReview[]> {
  const token = await requireAccessToken();
  const response = await fetch(`${apiUrl}${path}`, {
    headers: { Authorization: `Bearer ${token}` }, cache: "no-store",
  });
  if (response.status === 401) redirect("/auth");
  // A revoked assignment or domain is not an apparently clear queue.
  if (!response.ok) throw new Error("Arrangement reviews unavailable");
  return response.json() as Promise<ArrangementReview[]>;
}
export function listEventArrangementReviews(id: string): Promise<ArrangementReview[]> {
  return readReviews(`/event-requests/${encodeURIComponent(id)}/arrangement-reviews`);
}
export function listDomainArrangementReviews(arrangement: Arrangement): Promise<ArrangementReview[]> {
  return readReviews(`/arrangement-reviews?arrangement=${arrangement}`);
}
export async function clearArrangementReview(id: string): Promise<Response> {
  const token = await requireAccessToken();
  // Bodyless: actor and authorised domain scope are derived by the backend.
  return fetch(`${apiUrl}/arrangement-reviews/${encodeURIComponent(id)}/clear`, {
    method: "POST", headers: { Authorization: `Bearer ${token}` },
  });
}
