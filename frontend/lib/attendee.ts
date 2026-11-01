import { getJson } from "./api";

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

// What an attendee may see of an event (SCRUM-21 D4, hotfix 5): never anything internal.
export interface PublicEvent {
  id: string;
  event_name: string | null;
  purpose: string | null;
  description: string | null;
  proposed_date_times: string[];
  registration_opens_at: string | null;
  registration_closes_at: string | null;
  registration_capacity: number | null;
  places_remaining: number | null;
  venues: {
    name: string;
    location: string;
    start_date: string;
    end_date: string;
    start_minute: number;
    end_minute: number;
  }[];
}

export interface MyRegistration {
  id: string;
  event_request_id: string;
  status: "Registered" | "Withdrawn";
  created_at: string;
  attended_at?: string | null;
  event: PublicEvent;
}

export interface MyWaitlistEntry {
  id: string;
  event_request_id: string;
  event_name?: string | null;
  status: "Waiting" | "Offered" | "Closed";
  position: number | null;
  offered_at: string | null;
  expires_at: string | null;
}

export async function listOpenEvents(): Promise<PublicEvent[]> {
  return (await getJson<PublicEvent[]>(apiUrl, "/attendee/events")) ?? [];
}

export async function getOpenEvent(id: string): Promise<PublicEvent | null> {
  return getJson<PublicEvent>(apiUrl, `/attendee/events/${encodeURIComponent(id)}`);
}

export async function listMyRegistrations(): Promise<MyRegistration[]> {
  return (await getJson<MyRegistration[]>(apiUrl, "/attendee/registrations")) ?? [];
}

export async function listMyWaitlist(): Promise<MyWaitlistEntry[]> {
  return (await getJson<MyWaitlistEntry[]>(apiUrl, "/attendee/waitlist")) ?? [];
}

// An event is full once no place remains; the waiting list is offered then.
export function isFull(event: Pick<PublicEvent, "places_remaining">): boolean {
  return event.places_remaining !== null && event.places_remaining <= 0;
}

// Registration is open from its start up to, but not including, its end (SCRUM-21).
export function isRegistrationOpen(
  event: Pick<PublicEvent, "registration_opens_at" | "registration_closes_at">,
  at: number = Date.now(),
): boolean {
  if (!event.registration_opens_at || !event.registration_closes_at) return false;
  return at >= Date.parse(event.registration_opens_at) && at < Date.parse(event.registration_closes_at);
}
