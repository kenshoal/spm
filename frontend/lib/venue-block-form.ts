import { BLOCK_REASONS, REASON_DETAIL_MAX, type BlockReason } from "./venue-block-options";
import { SLOTS, type Slot } from "./venue-options";

export interface BlockPayload {
  start_date: string;
  end_date: string;
  slots: Slot[];
  reason_category: BlockReason;
  reason_detail?: string;
}

// Raw text as typed/checked, echoed back after a failed submission so the
// form keeps exactly what the staffer entered (see lib/venue-form.ts).
export interface BlockFormValues {
  venue_id: string;
  start_date: string;
  end_date: string;
  slots: string[];
  reason_category: string;
  reason_detail: string;
}

function raw(formData: FormData, field: string): string {
  return String(formData.get(field) ?? "");
}

// Rejects strings that look like YYYY-MM-DD but are not real dates
// (2026-02-30 would otherwise roll over into March).
function isRealDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

export function readBlockFormValues(formData: FormData): BlockFormValues {
  return {
    venue_id: raw(formData, "venue_id"),
    start_date: raw(formData, "start_date"),
    end_date: raw(formData, "end_date"),
    slots: formData.getAll("slots").map(String),
    reason_category: raw(formData, "reason_category"),
    reason_detail: raw(formData, "reason_detail"),
  };
}

export function parseBlockForm(formData: FormData): {
  venueId: string;
  payload: BlockPayload;
  errors: Record<string, string>;
} {
  const venueId = raw(formData, "venue_id").trim();
  const startDate = raw(formData, "start_date").trim();
  const endDate = raw(formData, "end_date").trim();
  const chosen = new Set(formData.getAll("slots").map(String));
  // Canonical AM, PM, NIGHT order; unknown values are dropped.
  const slots = SLOTS.filter((slot) => chosen.has(slot));
  const reason = raw(formData, "reason_category").trim();
  const detail = raw(formData, "reason_detail").trim();

  const errors: Record<string, string> = {};
  if (!venueId) errors.venue_id = "Choose a venue.";
  if (!isRealDate(startDate)) errors.start_date = "Enter a valid start date.";
  if (!isRealDate(endDate)) errors.end_date = "Enter a valid end date.";
  else if (isRealDate(startDate) && endDate < startDate) {
    errors.end_date = "The end date must be on or after the start date.";
  }
  if (slots.length === 0) errors.slots = "Choose at least one slot.";
  const isReason = (BLOCK_REASONS as readonly string[]).includes(reason);
  if (!isReason) errors.reason_category = "Choose a reason.";
  if (detail.length > REASON_DETAIL_MAX) {
    errors.reason_detail = `Keep the detail to ${REASON_DETAIL_MAX} characters or fewer.`;
  }

  const payload: BlockPayload = {
    start_date: startDate,
    end_date: endDate,
    slots,
    reason_category: reason as BlockReason,
  };
  if (detail) payload.reason_detail = detail;
  return { venueId, payload, errors };
}
