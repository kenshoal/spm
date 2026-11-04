"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";

export interface AttendeeActionState {
  message?: string;
  done?: boolean;
}

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

// Every refusal the API codes, in words an attendee can act on (SCRUM-21, 22, 24).
const messages: Record<string, string> = {
  registration_not_open: "Registration is not open for this event.",
  event_full: "This event is full. You can join the waiting list.",
  already_registered: "You are already registered for this event.",
  event_not_found: "This event is no longer open for registration.",
  already_withdrawn: "You have already withdrawn.",
  already_checked_in: "You have already been checked in, so you can no longer withdraw.",
  withdrawal_not_permitted: "This registration can no longer be withdrawn.",
  places_available: "There are places left, so you can register instead.",
  already_waitlisted: "You are already on the waiting list.",
  offer_expired: "This offer has expired. The place went to the next person.",
  entry_not_found: "This offer is no longer available.",
  not_offered: "There is no offer to act on for this entry.",
};

async function post(path: string): Promise<AttendeeActionState> {
  await requireRole("attendee");
  let response: Response;
  try {
    response = await sendJson(apiUrl, path, "POST", {});
  } catch {
    return { message: "That could not be done. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    const code = await response.json().then((body) => body?.code as string | undefined).catch(() => undefined);
    return { message: (code && messages[code]) || "That could not be done. Please try again." };
  }
  // "layout" also re-renders /events/[id], where join and register are clicked;
  // a plain "/events" refreshes the list page only, leaving the old button.
  revalidatePath("/events", "layout");
  return { done: true };
}

export async function registerForEvent(eventId: string): Promise<AttendeeActionState> {
  return post(`/attendee/events/${encodeURIComponent(eventId)}/registrations`);
}

export async function withdrawRegistration(registrationId: string): Promise<AttendeeActionState> {
  return post(`/attendee/registrations/${encodeURIComponent(registrationId)}/withdrawal`);
}

export async function joinWaitlist(eventId: string): Promise<AttendeeActionState> {
  return post(`/attendee/events/${encodeURIComponent(eventId)}/waitlist`);
}

export async function acceptWaitlistOffer(entryId: string): Promise<AttendeeActionState> {
  return post(`/attendee/waitlist/${encodeURIComponent(entryId)}/acceptance`);
}

export async function withdrawFromWaitlist(entryId: string): Promise<AttendeeActionState> {
  return post(`/attendee/waitlist/${encodeURIComponent(entryId)}/withdrawal`);
}
