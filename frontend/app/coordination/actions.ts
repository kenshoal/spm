"use server";

import { revalidatePath } from "next/cache";
import { redirect, unstable_rethrow } from "next/navigation";
import { requireAccessToken, requireRole } from "@/lib/auth";
import { parseFinalEndInput } from "@/lib/event-final-end";
import { getEventChangeBookingPlan, getEventChangeDatePlan, type EventChangeBookingConflict, type EventChangeBookingPlan, type EventChangeDatePlan } from "@/lib/event-requests";

export interface TransitionState {
  message?: string;
  errors?: { reason?: string };
  // SCRUM-58 AC3: what still blocks sending for safety review, one line each.
  outstanding?: string[];
  bookingConflicts?: EventChangeBookingConflict[];
}

export type ReviewDecision = "Approved" | "Changes Requested" | "Rejected";
export type ChangeDecision = "Approved" | "Rejected";

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

async function transition(
  eventRequestId: string,
  path: "review" | "planning" | "safety-review" | "resume-review" | "cancellation" | "completion",
): Promise<TransitionState> {
  await requireRole("event_coordinator");
  const token = await requireAccessToken();
  let response: Response;
  try {
    response = await fetch(
      `${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}/${path}`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      },
    );
  } catch {
    return { message: "That could not be done. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (response.status === 409) {
    // Only the safety-review refusal carries a list; any other 409 is a stale status.
    const outstanding = await outstandingMessages(response);
    if (outstanding.length > 0) {
      return { message: "This event isn't ready for safety review yet.", outstanding };
    }
  }
  if (!response.ok) {
    return {
      message:
        response.status === 403
          ? "Only the coordinator currently assigned to this request can do that."
          : response.status === 409
            ? "This request's status has already changed. Refresh the page to see where it stands."
            : "That could not be done. Please try again.",
    };
  }
  revalidatePath("/coordination/requests");
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  revalidatePath("/event-requests");
  return {};
}

async function outstandingMessages(response: Response): Promise<string[]> {
  try {
    const body = (await response.json()) as { outstanding?: unknown };
    if (!Array.isArray(body.outstanding)) return [];
    return body.outstanding
      .map((item) => String((item as { message?: unknown }).message ?? "").trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}

export async function startEventRequestReview(
  eventRequestId: string,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  void formData;
  return transition(eventRequestId, "review");
}

export async function startEventPlanning(
  eventRequestId: string,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  void formData;
  return transition(eventRequestId, "planning");
}

export async function sendForSafetyReview(
  eventRequestId: string,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  void formData;
  return transition(eventRequestId, "safety-review");
}

export async function resumeEventRequestReview(
  eventRequestId: string,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  void formData;
  return transition(eventRequestId, "resume-review");
}

export async function cancelEventRequest(
  eventRequestId: string,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  void formData;
  return transition(eventRequestId, "cancellation");
}

export async function completeEventRequest(
  eventRequestId: string,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  void formData;
  return transition(eventRequestId, "completion");
}

export async function decideEventRequest(
  eventRequestId: string,
  decision: ReviewDecision,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  await requireRole("event_coordinator");
  const reason = String(formData.get("reason") ?? "").trim();
  if ((decision === "Changes Requested" || decision === "Rejected") && !reason) {
    return {
      message: "Explain the decision before continuing.",
      errors: { reason: "Enter a reason for the organiser." },
    };
  }

  const token = await requireAccessToken();
  let response: Response;
  try {
    response = await fetch(
      `${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}/decision`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ decision, reason: reason || null }),
      },
    );
  } catch {
    return { message: "The decision could not be recorded. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    return {
      message:
        response.status === 403
          ? "Only the coordinator currently assigned to this request can decide it."
          : response.status === 409
            ? "This request is no longer under review. Refresh the page to see where it stands."
            : response.status === 422
              ? "Check the decision details and try again."
              : "The decision could not be recorded. Please try again.",
    };
  }

  revalidatePath("/coordination/requests");
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  revalidatePath("/event-requests");
  return {};
}

export async function decideEventChangeRequest(
  eventRequestId: string,
  changeRequestId: string,
  decision: ChangeDecision,
  previousState: TransitionState,
  formData: FormData,
): Promise<TransitionState> {
  void previousState;
  await requireRole("event_coordinator");
  const reason = String(formData.get("reason") ?? "").trim();
  if (decision === "Rejected" && !reason) {
    return { message: "Explain why the change is rejected.", errors: { reason: "Enter a reason for the organiser." } };
  }
  const rawPlan = formData.get("booking_plan");
  let bookingPlan: unknown;
  if (rawPlan !== null) {
    try {
      bookingPlan = JSON.parse(String(rawPlan));
      if (decision !== "Approved" || !Array.isArray(bookingPlan)) throw new Error("Invalid plan");
    } catch {
      return { message: "Check the complete booking plan and try again." };
    }
  }
  const token = await requireAccessToken();
  let response: Response;
  try {
    response = await fetch(
      `${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}/change-requests/${encodeURIComponent(changeRequestId)}/decision`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ decision, reason: reason || null, ...(rawPlan !== null ? { booking_plan: bookingPlan } : {}) }),
      },
    );
  } catch {
    return { message: "The change decision could not be recorded. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    if (response.status === 409) {
      const body = await response.json().catch(() => null);
      if (body?.detail?.code === "BOOKING_CONFLICT" && Array.isArray(body.detail.bookings)) {
        return { message: "One or more venue bookings conflict with this plan. Review the selected ranges.", bookingConflicts: body.detail.bookings };
      }
      if (body?.detail?.code === "CHANGE_DECISIONS_UNAVAILABLE") {
        return { message: "This proposal contains changes that cannot be applied together." };
      }
    }
    return {
      message: response.status === 403
        ? "Only the coordinator currently assigned to this request can decide the change."
        : response.status === 409
          ? "This change is already decided or the event plan has changed. Refresh before deciding."
          : response.status === 422
            ? "Check the decision details and try again."
            : "The change decision could not be recorded. Please try again.",
    };
  }
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  revalidatePath(`/event-requests/${eventRequestId}/edit`);
  revalidatePath("/event-requests");
  return {};
}


export interface PreviewDateChangeState {
  plan?: EventChangeDatePlan;
  message?: string;
}

/** Load on demand without applying a proposal, refreshing data or accepting form IDs. */
export async function previewEventChangeDatePlan(
  eventRequestId: string,
  changeRequestId: string,
  previousState: PreviewDateChangeState,
  formData: FormData,
): Promise<PreviewDateChangeState> {
  void previousState;
  void formData;
  await requireRole("event_coordinator");
  try {
    const plan = await getEventChangeDatePlan(eventRequestId, changeRequestId);
    return plan ? { plan } : { message: "Date change plan unavailable. Refresh the proposal and try again." };
  } catch (error: unknown) {
    unstable_rethrow(error);
    return { message: "Date change plan unavailable. Refresh the proposal and try again." };
  }
}

export interface RegistrationReviewState {
  acknowledged?: boolean;
  message?: string;
}

/** The API rechecks the verified coordinator and exact saved review under lock. */
export async function acknowledgeRegistrationReview(
  eventRequestId: string,
  reviewId: string,
  previousState: RegistrationReviewState,
  formData: FormData,
): Promise<RegistrationReviewState> {
  void previousState;
  void formData;
  await requireRole("event_coordinator");
  const token = await requireAccessToken();
  let response: Response;
  try {
    response = await fetch(`${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}/registration-reviews/${encodeURIComponent(reviewId)}/acknowledge`, {
      method: "POST", headers: { Authorization: `Bearer ${token}` },
    });
  } catch (error) {
    unstable_rethrow(error);
    return { message: "Registration reviews unavailable. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (response.status === 403) return { message: "You are no longer assigned to acknowledge this registration review." };
  if (response.status === 404) return { message: "This registration review is no longer available. Refresh the page." };
  if (response.status === 409) return { message: "This registration review has already been acknowledged. Refresh the page." };
  if (!response.ok) return { message: "Registration reviews unavailable. Please try again." };
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  revalidatePath(`/event-requests/${eventRequestId}/edit`);
  return { acknowledged: true };
}

export interface BookingPlanState {
  plan?: EventChangeBookingPlan;
  message?: string;
}

/** Load complete proposal-scoped editor data only when the coordinator asks. */
export async function loadEventChangeBookingPlan(
  eventRequestId: string, changeRequestId: string, previousState: BookingPlanState, formData: FormData,
): Promise<BookingPlanState> {
  void previousState;
  void formData;
  await requireRole("event_coordinator");
  try {
    const plan = await getEventChangeBookingPlan(eventRequestId, changeRequestId);
    return plan ? { plan } : { message: "Booking plan unavailable. Refresh the proposal and try again." };
  } catch (error) {
    unstable_rethrow(error);
    return { message: "Booking plan unavailable. Refresh the proposal and try again." };
  }
}

export interface ManualRegistrationState {
  message?: string;
  registered?: boolean;
}

export async function registerAttendee(
  eventRequestId: string,
  previousState: ManualRegistrationState,
  formData: FormData,
): Promise<ManualRegistrationState> {
  void previousState;
  const email = String(formData.get("attendee_email") ?? "").trim();
  if (!email) return { message: "Enter the attendee's email." };
  await requireRole("event_coordinator");
  const token = await requireAccessToken();
  let response: Response;
  try {
    response = await fetch(`${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}/registrations`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ attendee_email: email }),
    });
  } catch (error) {
    unstable_rethrow(error);
    return { message: "Registrations unavailable. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    const code = await response.json().then((body) => body?.code).catch(() => undefined);
    return { message: MANUAL_REGISTRATION_MESSAGES[code] ?? "Registrations unavailable. Please try again." };
  }
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  revalidatePath(`/event-requests/${eventRequestId}/edit`);
  return { registered: true };
}

const MANUAL_REGISTRATION_MESSAGES: Record<string, string> = {
  attendee_not_found: "No attendee account has that email. Ask the organiser to check it.",
  event_not_found: "You are no longer assigned to this event, or it is no longer confirmed. Refresh the page.",
  already_registered: "This attendee is already registered for this event.",
  event_full: "This event is full.",
  capacity_not_set: "This event has no registration capacity set yet.",
};

export interface FinalEndState {
  message?: string;
  saved?: true;
}

export async function setEventFinalEnd(
  eventRequestId: string,
  previousState: FinalEndState,
  formData: FormData,
): Promise<FinalEndState> {
  void previousState;
  await requireRole("event_coordinator");
  const token = await requireAccessToken();
  const finalEnd = parseFinalEndInput(formData.get("final_event_end_at"));
  if (!finalEnd) return { message: "Enter a valid final event end in Singapore time." };
  let response: Response;
  try {
    response = await fetch(`${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}/final-end`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ final_event_end_at: finalEnd }),
    });
  } catch {
    return { message: "The final event end could not be saved. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) return {
    message: response.status === 403
      ? "Only the currently assigned coordinator can record the final event end."
      : response.status === 409
        ? "The final event end can only be saved while Approved or Planning. Refresh to check the event."
        : "The final event end could not be saved. Please try again.",
  };
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  revalidatePath(`/event-requests/${eventRequestId}/edit`);
  revalidatePath("/coordination/requests");
  revalidatePath("/event-requests");
  return { saved: true };
}
