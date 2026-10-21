import { getJson } from "./api";
import { equipmentApiUrl } from "./equipment";
import type { EventRequest } from "./event-requests";
import type { VenueBlock } from "./venue-block-options";

// SCRUM-60: the Safety Officer's check of an event in Safety Review.
const eventRequestApiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

export type SafetyArrangement = "venue_booking" | "equipment_reservation";

export interface SafetyTarget {
  arrangement: SafetyArrangement;
  id: string;
}

export interface SafetyDecisionPayload {
  decision: "approved" | "changes_requested";
  reason?: string;
  targets: SafetyTarget[];
}

export interface SafetyReview {
  id: string;
  event_request_id: string;
  decision: "approved" | "changes_requested";
  reason: string | null;
  targets: SafetyTarget[];
  decided_by: string;
  decided_at: string;
}

export interface EquipmentRequirement {
  id: string;
  equipment_type: string;
  quantity: number;
  technical_requirements: string | null;
  status: string;
}

export interface EquipmentReservation {
  id: string;
  requirement_id: string;
  equipment_id: string;
  quantity: number;
  collection_date: string;
  return_date: string;
}

const ARRANGEMENTS: readonly string[] = ["venue_booking", "equipment_reservation"];
const MAX_REASON = 2000;

// Approval sends only the decision, and is refused if a reason was typed or an
// arrangement ticked, so that input is never silently dropped. Asking for
// changes needs a reason and sends the ticked arrangements, each submitted as
// "<arrangement>:<id>".
export function parseSafetyDecisionForm(formData: FormData): {
  payload: SafetyDecisionPayload;
  errors: Record<string, string>;
} {
  const decision = String(formData.get("decision") ?? "");
  if (decision === "approved") {
    const filledIn = String(formData.get("reason") ?? "").trim() !== "" || formData.getAll("target").length > 0;
    const errors: Record<string, string> = filledIn
      ? { decision: "You typed a reason or ticked arrangements. Clear them to approve, or choose Ask for changes." }
      : {};
    return { payload: { decision, targets: [] }, errors };
  }
  if (decision !== "changes_requested") {
    return { payload: { decision: "approved", targets: [] }, errors: { decision: "Choose approve or ask for changes." } };
  }
  const reason = String(formData.get("reason") ?? "").trim();
  const targets = formData
    .getAll("target")
    .map((value) => String(value).split(":"))
    .filter(([arrangement, id]) => ARRANGEMENTS.includes(arrangement) && Boolean(id))
    .map(([arrangement, id]) => ({ arrangement: arrangement as SafetyArrangement, id }));
  const errors: Record<string, string> = {};
  if (!reason) errors.reason = "Say what needs to change.";
  else if (reason.length > MAX_REASON) errors.reason = "Keep the reason to 2000 characters or fewer.";
  return { payload: { decision, reason, targets }, errors };
}

// An active block is a restriction on a booking when they share a date and
// overlap in time (SCRUM-65).
export function overlappingBlocks(
  blocks: VenueBlock[],
  booking: { start_date: string; end_date: string; start_minute: number; end_minute: number },
): VenueBlock[] {
  return blocks.filter(
    (block) =>
      block.status === "active" &&
      block.start_date <= booking.end_date &&
      block.end_date >= booking.start_date &&
      block.start_minute < booking.end_minute &&
      booking.start_minute < block.end_minute,
  );
}

// Events waiting for a check, longest-waiting first. Any failure throws so the
// page shows an outage, never an empty queue that looks like "nothing to check".
export async function listSafetyQueue(): Promise<EventRequest[]> {
  const events = await getJson<EventRequest[]>(eventRequestApiUrl, "/event-requests/safety-queue");
  if (events === null) throw new Error("The safety queue is not available");
  return events;
}

export async function listSafetyReviews(eventRequestId: string): Promise<SafetyReview[]> {
  const reviews = await getJson<SafetyReview[]>(
    eventRequestApiUrl,
    `/event-requests/${encodeURIComponent(eventRequestId)}/safety-reviews`,
  );
  return reviews ?? [];
}

export async function listEventRequirements(eventRequestId: string): Promise<EquipmentRequirement[]> {
  const rows = await getJson<EquipmentRequirement[]>(
    equipmentApiUrl,
    `/equipment-requirements/by-event/${encodeURIComponent(eventRequestId)}`,
  );
  if (rows === null) throw new Error("Equipment requirements are not available for this event");
  return rows;
}

export async function listEventReservations(eventRequestId: string): Promise<EquipmentReservation[]> {
  const rows = await getJson<EquipmentReservation[]>(
    equipmentApiUrl,
    `/equipment-reservations/by-event/${encodeURIComponent(eventRequestId)}`,
  );
  if (rows === null) throw new Error("Equipment reservations are not available for this event");
  return rows;
}
