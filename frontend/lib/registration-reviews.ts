import { redirect } from "next/navigation";
import { requireAccessToken } from "./auth";

/** Event-level requirements evidence; never attendee registrations or settings. */
export interface RegistrationReview {
  id: string;
  event_request_id: string;
  event_updated_at: string;
  changed_fields: string[];
  reason: string;
  raised_at: string;
  cleared_at: string | null;
  cleared_by: string | null;
}

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

export async function listRegistrationReviews(eventRequestId: string): Promise<RegistrationReview[]> {
  const token = await requireAccessToken();
  const response = await fetch(`${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}/registration-reviews`, {
    headers: { Authorization: `Bearer ${token}` }, cache: "no-store",
  });
  if (response.status === 401) redirect("/auth");
  if (!response.ok) throw new Error("Registration reviews unavailable");
  return response.json() as Promise<RegistrationReview[]>;
}
