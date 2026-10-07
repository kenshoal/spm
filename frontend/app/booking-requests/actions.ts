"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";
import { parseDecisionForm, readDecisionFormValues, refusalMessages, type DecisionFormValues } from "@/lib/booking-decision-form";
import { venueApiUrl } from "@/lib/venues";

export interface DecisionFormState {
  message?: string;
  errors?: Record<string, string>;
  values?: DecisionFormValues;
}

const retryMessage = "The decision could not be saved. Please try again.";
const failureMessages: Record<number, string> = {
  403: "Only Venue Staff can decide booking requests.",
  404: "This booking request no longer exists.",
  422: "The venue service rejected this decision. Check it and try again.",
};

async function readBody(response: Response): Promise<{ detail?: unknown } | null> {
  try {
    return (await response.json()) as { detail?: unknown };
  } catch {
    return null;
  }
}

export async function decideBookingRequest(
  bookingId: string,
  previousState: DecisionFormState,
  formData: FormData,
): Promise<DecisionFormState> {
  void previousState;
  const { payload, errors } = parseDecisionForm(formData);
  if (Object.keys(errors).length) {
    return { message: "Check the highlighted fields.", errors, values: readDecisionFormValues(formData) };
  }

  await requireRole("venue_staff");
  let response: Response;
  try {
    response = await sendJson(venueApiUrl, `/booking-requests/${encodeURIComponent(bookingId)}/decision`, "POST", payload);
  } catch {
    return { message: retryMessage, values: readDecisionFormValues(formData) };
  }
  // redirect() throws, so it stays outside the try above.
  if (response.status === 401) redirect("/auth");
  if (response.status === 409) {
    const detail = (await readBody(response))?.detail;
    if (detail && typeof detail === "object" && "refusal_codes" in detail && Array.isArray(detail.refusal_codes)) {
      const reasons = refusalMessages(detail.refusal_codes.map(String));
      return {
        message: ["Approval refused.", ...reasons, "The refusal has been recorded."].join(" "),
        values: readDecisionFormValues(formData),
      };
    }
    return { message: "This request has already been decided. Refresh to see its status." };
  }
  if (!response.ok) {
    return { message: failureMessages[response.status] ?? retryMessage, values: readDecisionFormValues(formData) };
  }
  revalidatePath("/booking-requests");
  redirect(`/booking-requests?decided=${payload.decision}`);
}
