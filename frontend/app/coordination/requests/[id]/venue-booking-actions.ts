"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { timeRangeFrom } from "@/lib/venue-options";
import { requireRole } from "@/lib/auth";
import { venueApiUrl } from "@/lib/venues";

export interface CancelBookingState {
  message?: string;
}

const retryMessage = "The booking could not be cancelled. Please try again.";
const failureMessages: Record<number, string> = {
  403: "Only the event's coordinator can cancel a booking.",
  404: "This booking could not be found, or the event is no longer assigned to you.",
  409: "This booking can no longer be cancelled.",
};

// Cancels one booking of an event. It makes a single POST; the event's other
// bookings are untouched, and the API rechecks that the caller is the event's
// current coordinator.
export async function cancelVenueBooking(
  previousState: CancelBookingState,
  formData: FormData,
): Promise<CancelBookingState> {
  void previousState;
  const bookingId = String(formData.get("booking_id") ?? "").trim();
  const eventRequestId = String(formData.get("event_request_id") ?? "").trim();
  if (!bookingId || !eventRequestId) return { message: retryMessage };

  await requireRole("event_coordinator");
  let response: Response;
  try {
    response = await sendJson(venueApiUrl, `/booking-requests/${encodeURIComponent(bookingId)}/cancel`, "POST", {});
  } catch {
    return { message: retryMessage };
  }
  // redirect() throws, so it stays outside the try above.
  if (response.status === 401) redirect("/auth");
  if (!response.ok) return { message: failureMessages[response.status] ?? retryMessage };
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  return {};
}

export interface ReplacementConflict {
  start_date: string;
  end_date: string;
  start_minute: number;
  end_minute: number;
}

export interface ReplacementState {
  message?: string;
  // SCRUM-67: approved bookings the new request overlaps; a warning, not a refusal.
  conflicts?: ReplacementConflict[];
}

function readConflicts(body: unknown): ReplacementConflict[] {
  const list = (body as { conflicts?: unknown } | null)?.conflicts;
  if (!Array.isArray(list)) return [];
  return list.filter(
    (item): item is ReplacementConflict =>
      typeof item === "object" && item !== null &&
      typeof item.start_date === "string" && typeof item.end_date === "string" &&
      typeof item.start_minute === "number" && typeof item.end_minute === "number",
  );
}

const replacementRetry = "The replacement could not be requested. Please try again.";
const replacementMessages: Record<number, string> = {
  403: "Only the event's coordinator can request a replacement.",
  404: "This booking could not be found, or the event is no longer assigned to you.",
  422: "Choose a different venue from the one that is blocked.",
};
const replacementConflicts: [RegExp, string][] = [
  [/not flagged/i, "This booking no longer needs a new venue."],
  [/not approved/i, "Only an approved booking can be replaced."],
  [/already been requested/i, "A replacement has already been requested for this booking."],
  [/event request changed/i, "The event changed. Refresh the page and try again."],
];

// Asks for another venue for a booking that a venue block flagged. One POST with
// the chosen venue; the API keeps the event, dates and times, links the new request
// to the old booking and rechecks that the caller is the event's current coordinator.
export async function requestReplacementVenue(
  previousState: ReplacementState,
  formData: FormData,
): Promise<ReplacementState> {
  void previousState;
  const bookingId = String(formData.get("booking_id") ?? "").trim();
  const eventRequestId = String(formData.get("event_request_id") ?? "").trim();
  const venueId = String(formData.get("venue_id") ?? "").trim();
  if (!bookingId || !eventRequestId) return { message: replacementRetry };
  if (!venueId) return { message: "Choose a venue for the replacement." };

  await requireRole("event_coordinator");
  let response: Response;
  try {
    response = await sendJson(venueApiUrl, `/booking-requests/${encodeURIComponent(bookingId)}/replacement`, "POST", { venue_id: venueId });
  } catch {
    return { message: replacementRetry };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    if (response.status === 409) {
      const detail = await response.json().then((body) => String(body?.detail ?? ""), () => "");
      return { message: replacementConflicts.find(([pattern]) => pattern.test(detail))?.[1] ?? replacementRetry };
    }
    return { message: replacementMessages[response.status] ?? replacementRetry };
  }
  const conflicts = readConflicts(await response.json().catch(() => null));
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  return conflicts.length > 0 ? { conflicts } : {};
}

export interface RequestVenueState extends ReplacementState {
  venueName?: string;
  submitted?: boolean;
}

// Hotfix 6 (SCRUM-32, SCRUM-61): request a venue for the event. The API checks the
// assignment and the event; a clash comes back as a warning (SCRUM-67), and Venue
// Staff still decide the request.
export async function requestVenueBooking(
  eventRequestId: string,
  previousState: RequestVenueState,
  formData: FormData,
): Promise<RequestVenueState> {
  void previousState;
  const venueId = String(formData.get("venue_id") ?? "");
  const startDate = String(formData.get("start_date") ?? "");
  const endDate = String(formData.get("end_date") ?? "") || startDate;
  const range = timeRangeFrom(String(formData.get("start_time") ?? ""), String(formData.get("end_time") ?? ""));
  if (!venueId || !startDate) return { message: "Choose a venue and a date." };
  if (range.start_minute === null || range.end_minute === null || Object.keys(range.errors).length) {
    return { message: "Choose a start time and a later end time." };
  }
  await requireRole("event_coordinator");
  let response: Response;
  try {
    response = await sendJson(venueApiUrl, "/booking-requests", "POST", {
      venue_id: venueId,
      event_request_id: eventRequestId,
      start_date: startDate,
      end_date: endDate,
      start_minute: range.start_minute,
      end_minute: range.end_minute,
    });
  } catch {
    return { message: "The venue could not be requested. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    const messages: Record<number, string> = {
      403: "Only the event's coordinator can request a venue.",
      404: "This event or venue could not be found, or the event is no longer assigned to you.",
      409: "This event changed. Refresh the page and try again.",
      422: "Check the dates and times, then try again.",
    };
    return { message: messages[response.status] ?? "The venue could not be requested. Please try again." };
  }
  const conflicts = readConflicts(await response.json().catch(() => null));
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  return { submitted: true, conflicts };
}
