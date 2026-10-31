import { redirect } from "next/navigation";
import { requireAccessToken } from "./auth";

/** SCRUM-34: what an event's organiser or coordinator sees of its registrations. */
export interface EventRegistration {
  id: string;
  attendee_id: string;
  status: string;
  created_at: string;
  /** SCRUM-41: the coordinator who entered it; null when self-registered. */
  registered_by: string | null;
  /** SCRUM-25: null until checked in. */
  attended_at: string | null;
  checked_in_by: string | null;
}

export interface RegistrationInfo {
  event_request_id: string;
  registration_capacity: number | null;
  registered: number;
  withdrawn: number;
  places_available: number | null;
  attended: number;
  absent: number;
  registrations: EventRegistration[];
}

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

export async function getRegistrationInfo(eventRequestId: string): Promise<RegistrationInfo> {
  const token = await requireAccessToken();
  const response = await fetch(`${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}/registrations`, {
    headers: { Authorization: `Bearer ${token}` }, cache: "no-store",
  });
  if (response.status === 401) redirect("/auth");
  if (!response.ok) throw new Error("Registration information unavailable");
  return response.json() as Promise<RegistrationInfo>;
}

const singaporeDay = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Singapore" });

/** SCRUM-25 D2: the same Asia/Singapore calendar-day rule check_in_attendee applies. */
export function isEventDay(dates: string[], now: Date = new Date()): boolean {
  const today = singaporeDay.format(now);
  return dates.some((date) => singaporeDay.format(new Date(date)) === today);
}
