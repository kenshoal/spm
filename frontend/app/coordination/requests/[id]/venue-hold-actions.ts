"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";
import { refusalMessages } from "@/lib/booking-decision-form";
import { parsePlaceHoldForm, readPlaceHoldValues, type PlaceHoldValues } from "@/lib/venue-hold-form";
import { venueApiUrl } from "@/lib/venues";

export interface PlaceHoldState {
  message?: string;
  errors?: Record<string, string>;
  values?: PlaceHoldValues;
}

export interface HoldActionState {
  message?: string;
}

const retryMessage = "The hold could not be saved. Please try again.";
const notFound = "This venue or event could not be found, or the event is no longer assigned to you.";

async function readDetailObject(response: Response): Promise<unknown> {
  try {
    return (await response.json())?.detail;
  } catch {
    return null;
  }
}

// Holds a venue for the event (SCRUM-18). A clash is explained with the same
// wording as a refused booking approval; the API rechecks everything.
export async function placeVenueHold(
  eventRequestId: string,
  previousState: PlaceHoldState,
  formData: FormData,
): Promise<PlaceHoldState> {
  void previousState;
  const values = readPlaceHoldValues(formData);
  const { venueId, payload, errors } = parsePlaceHoldForm(formData, eventRequestId);
  if (Object.keys(errors).length) return { message: "Check the highlighted fields.", errors, values };

  await requireRole("event_coordinator");
  let response: Response;
  try {
    response = await sendJson(venueApiUrl, `/venues/${encodeURIComponent(venueId)}/holds`, "POST", payload);
  } catch {
    return { message: retryMessage, values };
  }
  if (response.status === 401) redirect("/auth");
  if (response.status === 409) {
    const detail = await readDetailObject(response);
    if (detail && typeof detail === "object" && "refusal_codes" in detail && Array.isArray(detail.refusal_codes)) {
      return {
        message: ["The venue could not be held.", ...refusalMessages(detail.refusal_codes.map(String))].join(" "),
        values,
      };
    }
    return { message: "Holds can only be placed while the event is being finalised.", values };
  }
  if (response.status === 404) return { message: notFound, values };
  if (response.status === 422) return { message: "Check the dates, times and expiry, then try again.", values };
  if (!response.ok) return { message: retryMessage, values };
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  return {};
}

const holdFailures: Record<number, string> = {
  403: "Only the event's coordinator can change a hold.",
  404: "This hold could not be found, or the event is no longer assigned to you.",
  409: "This hold has ended or expired, or its booking request is still pending.",
};

async function holdAction(path: string, formData: FormData, failure: string): Promise<HoldActionState> {
  const holdId = String(formData.get("hold_id") ?? "").trim();
  const eventRequestId = String(formData.get("event_request_id") ?? "").trim();
  if (!holdId || !eventRequestId) return { message: failure };

  await requireRole("event_coordinator");
  let response: Response;
  try {
    response = await sendJson(venueApiUrl, `/venue-holds/${encodeURIComponent(holdId)}/${path}`, "POST", {});
  } catch {
    return { message: failure };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) return { message: holdFailures[response.status] ?? failure };
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  return {};
}

// Frees the held time straight away.
export async function releaseVenueHold(previousState: HoldActionState, formData: FormData): Promise<HoldActionState> {
  void previousState;
  return holdAction("release", formData, "The hold could not be released. Please try again.");
}

// Turns the hold into a pending booking request for Venue Staff to decide.
export async function convertVenueHold(previousState: HoldActionState, formData: FormData): Promise<HoldActionState> {
  void previousState;
  return holdAction("convert", formData, "The booking request could not be created. Please try again.");
}
