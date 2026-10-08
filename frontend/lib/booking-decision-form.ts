// Client-safe booking-request types and decision-form rules (SCRUM-15): no
// import of ./api or ./auth, so the "use client" decision form can use them.
import type { Slot } from "./venue-options";

export const BOOKING_STATUSES = ["pending", "approved", "rejected"] as const;
export type BookingStatus = (typeof BOOKING_STATUSES)[number];

// A venue booking request as venueService returns it (SCRUM-32 model).
export interface BookingRequestItem {
  id: string;
  venue_id: string;
  requested_by: string;
  event_request_id: string;
  event_name: string | null;
  expected_attendance: number | null;
  requirements_note: string | null;
  start_date: string;
  end_date: string;
  slots: Slot[];
  status: BookingStatus;
  decision_reason: string | null;
  suggested_alternative: string | null;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
}

export interface DecisionPayload {
  decision: "approved" | "rejected";
  reason?: string;
  suggested_alternative?: string;
}

// Raw rejection text, echoed back after a failed submission.
export interface DecisionFormValues {
  reason: string;
  suggested_alternative: string;
}

export function readDecisionFormValues(formData: FormData): DecisionFormValues {
  return {
    reason: String(formData.get("reason") ?? ""),
    suggested_alternative: String(formData.get("suggested_alternative") ?? ""),
  };
}

// An approval sends only the decision; a rejection needs a reason and may
// suggest an alternative (SCRUM-15 AC2). Blank optional text is not sent.
export function parseDecisionForm(formData: FormData): { payload: DecisionPayload; errors: Record<string, string> } {
  const decision = String(formData.get("decision") ?? "");
  if (decision === "approved") return { payload: { decision }, errors: {} };
  if (decision !== "rejected") {
    return { payload: { decision: "approved" }, errors: { decision: "Choose approve or reject." } };
  }
  const reason = String(formData.get("reason") ?? "").trim();
  const alternative = String(formData.get("suggested_alternative") ?? "").trim();
  const payload: DecisionPayload = { decision, reason };
  if (alternative) payload.suggested_alternative = alternative;
  return reason ? { payload, errors: {} } : { payload, errors: { reason: "Enter a reason for rejecting." } };
}

const REFUSAL_TEXT: Record<string, string> = {
  venue_unavailable: "The venue is blocked in the catalogue.",
  outside_operating_slots: "The venue does not operate one of the requested slots.",
  active_block: "The venue is blocked for part of this period.",
  booking_conflict: "Another approved booking already holds part of this period.",
};

export function refusalMessages(codes: readonly string[]): string[] {
  return codes.map((code) => REFUSAL_TEXT[code] ?? "The venue is not available for this period.");
}
