// Client-safe helpers for deciding a change request field by field (hotfix 20, Q&A #104):
// no import of ./api, ./auth or anything that touches next/headers.

export const CHANGE_FIELD_LABELS: Record<string, string> = {
  proposed_date_times: "Proposed date and time",
  expected_attendance: "Expected attendance",
  venue_requirements: "Venue requirements",
  equipment_requirements: "Equipment requirements",
  registration_needs: "Registration needs",
  accessibility_needs: "Accessibility needs",
};

export interface PartialDecision {
  accepted_fields: string[];
  rejected_reasons: Record<string, string>;
}

export interface PartialDecisionResult {
  decision?: PartialDecision;
  /** One message for the form; nothing is sent when it is set. */
  message?: string;
  /** Field name -> what is missing, so the form can mark the input. */
  errors?: Record<string, string>;
}

/**
 * Reads the Coordinator's choices: each proposed field is accepted (an `accept` entry with its
 * name) or refused with a reason in `reason__<field>`. At least one field must be accepted and at
 * least one refused, and every refused field needs a reason: a decision that accepts everything or
 * nothing is the ordinary approval or rejection.
 */
export function parsePartialDecision(formData: FormData, proposedFields: string[]): PartialDecisionResult {
  const accepted = new Set(formData.getAll("accept").map(String));
  const unknown = [...accepted].filter((field) => !proposedFields.includes(field));
  if (unknown.length > 0) return { message: "Choose only fields from this request." };
  const acceptedFields = proposedFields.filter((field) => accepted.has(field));
  const refused = proposedFields.filter((field) => !accepted.has(field));
  if (acceptedFields.length === 0) {
    return { message: "Accept at least one field, or reject the whole change." };
  }
  if (refused.length === 0) {
    return { message: "Every field is accepted. Use “Approve change” instead." };
  }
  const rejectedReasons: Record<string, string> = {};
  const errors: Record<string, string> = {};
  for (const field of refused) {
    const reason = String(formData.get(`reason__${field}`) ?? "").trim();
    if (!reason) errors[field] = "Say why this is not accepted.";
    else if (reason.length > 2000) errors[field] = "Keep the reason under 2,000 characters.";
    else rejectedReasons[field] = reason;
  }
  if (Object.keys(errors).length > 0) return { message: "Give a reason for every field you do not accept.", errors };
  return { decision: { accepted_fields: acceptedFields, rejected_reasons: rejectedReasons } };
}
