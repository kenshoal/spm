"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
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
