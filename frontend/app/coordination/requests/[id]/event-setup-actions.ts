"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";
import { singaporeInstant } from "@/lib/singapore-time";

export interface SetupState {
  message?: string;
  saved?: boolean;
}

const eventApi = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";
const equipmentApi = process.env.EQUIPMENT_API_URL ?? "http://127.0.0.1:8002";

async function bodyOf(response: Response): Promise<{ code?: string; detail?: string }> {
  const body = await response.json().catch(() => null);
  return {
    code: typeof body?.code === "string" ? body.code : undefined,
    detail: typeof body?.detail === "string" ? body.detail : undefined,
  };
}

async function send(
  eventRequestId: string,
  baseUrl: string,
  path: string,
  method: "POST" | "PATCH" | "PUT",
  body: unknown,
  messages: Record<string, string>,
  // Hotfix 24: some refusals carry a sentence written for the Coordinator; show it as is.
  showDetailFor: readonly number[] = [],
): Promise<SetupState> {
  await requireRole("event_coordinator");
  let response: Response;
  try {
    response = await sendJson(baseUrl, path, method, body);
  } catch {
    return { message: "That could not be saved. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    const { code, detail } = await bodyOf(response);
    return {
      message:
        (showDetailFor.includes(response.status) && detail) ||
        (code && messages[code]) ||
        messages[String(response.status)] ||
        "That could not be saved. Please try again.",
    };
  }
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  revalidatePath(`/event-requests/${eventRequestId}/edit`);
  return { saved: true };
}

// Hotfix 4 (Q&A #30, #42, #127): opens, closes and capacity, also to extend or reopen.
export async function saveRegistrationSettings(
  eventRequestId: string,
  previousState: SetupState,
  formData: FormData,
): Promise<SetupState> {
  void previousState;
  const opens = singaporeInstant(String(formData.get("registration_opens_at") ?? ""));
  const closes = singaporeInstant(String(formData.get("registration_closes_at") ?? ""));
  const capacityText = String(formData.get("registration_capacity") ?? "").trim();
  if (!opens || !closes) return { message: "Choose when registration opens and closes." };
  if (closes <= opens) return { message: "Registration must close after it opens." };
  if (!/^\d+$/.test(capacityText) || Number(capacityText) <= 0) {
    return { message: "Enter a capacity of at least 1." };
  }
  return send(
    eventRequestId,
    eventApi,
    `/event-requests/${encodeURIComponent(eventRequestId)}/registration-settings`,
    "PUT",
    {
      registration_opens_at: opens,
      registration_closes_at: closes,
      registration_capacity: Number(capacityText),
    },
    {
      capacity_below_taken: "Capacity cannot be lower than the places already taken.",
      registration_settings_not_allowed: "Registration cannot be set up at this stage.",
      "403": "Only the event's coordinator can set up registration.",
      "404": "This event could not be found, or is no longer assigned to you.",
      "422": "Check the dates and capacity, then try again.",
    },
  );
}

const DETAIL_TEXT_FIELDS = [
  "event_name",
  "purpose",
  "description",
  "venue_requirements",
  "accessibility_needs",
  "equipment_requirements",
  "registration_needs",
] as const;

// Hotfix 8 (SCRUM-29, Q&A #102). Only what changed is sent; the database flags
// arrangements when a significant field changes.
export async function saveEventDetails(
  eventRequestId: string,
  previousState: SetupState,
  formData: FormData,
): Promise<SetupState> {
  void previousState;
  const changes: Record<string, unknown> = {};
  for (const field of DETAIL_TEXT_FIELDS) {
    const value = String(formData.get(field) ?? "").trim();
    if (value !== String(formData.get(`original_${field}`) ?? "").trim()) {
      if (!value) return { message: "Details cannot be left blank." };
      changes[field] = value;
    }
  }
  const attendance = String(formData.get("expected_attendance") ?? "").trim();
  if (attendance !== String(formData.get("original_expected_attendance") ?? "").trim()) {
    if (!/^\d+$/.test(attendance) || Number(attendance) <= 0) {
      return { message: "Enter an expected attendance of at least 1." };
    }
    changes.expected_attendance = Number(attendance);
  }
  const dates = formData.getAll("proposed_date_times").map(String).filter(Boolean);
  if (dates.join("|") !== formData.getAll("original_proposed_date_times").map(String).join("|")) {
    if (dates.length === 0) return { message: "Keep at least one date and time." };
    changes.proposed_date_times = dates.map(singaporeInstant);
  }
  if (Object.keys(changes).length === 0) return { message: "Nothing has changed." };
  return send(
    eventRequestId,
    eventApi,
    `/event-requests/${encodeURIComponent(eventRequestId)}/details`,
    "PATCH",
    { expected_updated_at: String(formData.get("expected_updated_at") ?? ""), ...changes },
    {
      event_details_conflict: "This event changed since you opened it. Refresh and try again.",
      "403": "Only the event's coordinator can change its details.",
      "404": "This event could not be found, or is no longer assigned to you.",
      "422": "Check the details and try again.",
    },
  );
}

// Hotfix 7 (SCRUM-33): what the event needs, for Technical Support to arrange.
export async function recordEquipmentRequirement(
  eventRequestId: string,
  previousState: SetupState,
  formData: FormData,
): Promise<SetupState> {
  void previousState;
  const type = String(formData.get("equipment_type") ?? "").trim();
  const quantity = String(formData.get("quantity") ?? "").trim();
  const technical = String(formData.get("technical_requirements") ?? "").trim();
  if (!type) return { message: "Enter the equipment type." };
  if (!/^\d+$/.test(quantity) || Number(quantity) <= 0) return { message: "Enter a quantity of at least 1." };
  return send(
    eventRequestId,
    equipmentApi,
    "/equipment-requirements",
    "POST",
    {
      event_request_id: eventRequestId,
      equipment_type: type,
      quantity: Number(quantity),
      technical_requirements: technical || null,
    },
    {
      "403": "Only the event's coordinator can record equipment.",
      "404": "This event could not be found, or is no longer assigned to you.",
      "409": "Equipment can't be recorded for this event at this stage.",
      "422": "No catalogue equipment matches that type, or the details are invalid.",
    },
  );
}

// SCRUM-24 AC3: the Coordinator overrides FIFO for an open place (Q&A #26).
export async function offerWaitlistPlace(eventRequestId: string, entryId: string): Promise<SetupState> {
  return send(
    eventRequestId,
    eventApi,
    `/event-requests/${encodeURIComponent(eventRequestId)}/waitlist/${encodeURIComponent(entryId)}/offer`,
    "POST",
    {},
    {
      "403": "Only the event's coordinator can choose who gets a place.",
      "404": "This person is no longer on the waiting list.",
      "409": "There is no open place to offer right now.",
    },
  );
}

// Hotfix 22 (Q&A #69, #121): postpone with no new date; bookings and reservations are released.
export async function postponeEvent(
  eventRequestId: string,
  previousState: SetupState,
  formData: FormData,
): Promise<SetupState> {
  void previousState;
  const reason = String(formData.get("reason") ?? "").trim();
  if (!reason) return { message: "Say why the event is being postponed." };
  return send(
    eventRequestId,
    eventApi,
    `/event-requests/${encodeURIComponent(eventRequestId)}/postponement`,
    "POST",
    { reason },
    {
      "403": "Only the event's coordinator can postpone it.",
      "404": "This event could not be found, or is no longer assigned to you.",
      "409": "This event can't be postponed from its current status. Refresh the page.",
      "422": "Give a reason of up to 2,000 characters.",
    },
  );
}

// Hotfix 22: the new date for a postponed event; it goes back to Planning.
export async function resumeEvent(
  eventRequestId: string,
  previousState: SetupState,
  formData: FormData,
): Promise<SetupState> {
  void previousState;
  const instant = singaporeInstant(String(formData.get("new_date") ?? ""));
  if (!instant) return { message: "Choose the new date and time." };
  if (new Date(instant).getTime() <= Date.now()) return { message: "Choose a date and time in the future." };
  return send(
    eventRequestId,
    eventApi,
    `/event-requests/${encodeURIComponent(eventRequestId)}/resumption`,
    "POST",
    { proposed_date_times: [instant] },
    {
      "403": "Only the event's coordinator can set the new date.",
      "404": "This event could not be found, or is no longer assigned to you.",
      "409": "This event is no longer postponed. Refresh the page.",
      "422": "Choose a date and time in the future.",
    },
  );
}

// Hotfix 24 (Q&A #59, #61): hand the event to another Event Organiser.
export async function changeOrganiser(
  eventRequestId: string,
  previousState: SetupState,
  formData: FormData,
): Promise<SetupState> {
  void previousState;
  const email = String(formData.get("organiser_email") ?? "").trim();
  const reason = String(formData.get("reason") ?? "").trim();
  if (!email) return { message: "Enter the new Event Organiser's email address." };
  if (!reason) return { message: "Say why the Event Organiser is being changed." };
  return send(
    eventRequestId,
    eventApi,
    `/event-requests/${encodeURIComponent(eventRequestId)}/organiser`,
    "POST",
    { organiser_email: email, reason },
    {
      "403": "Only the event's coordinator can change its Event Organiser.",
      "404": "This event could not be found, or is no longer assigned to you.",
      "409": "The Event Organiser can't be changed at this stage.",
      "422": "Check the email address and the reason, then try again.",
    },
    [409, 422],
  );
}

// Hotfix 25 (Q&A #80, #106): an equipment requirement the event can go ahead without.
export async function setRequirementEssential(
  eventRequestId: string,
  requirementId: string,
  previousState: SetupState,
  formData: FormData,
): Promise<SetupState> {
  void previousState;
  const essential = String(formData.get("essential") ?? "") === "true";
  const note = String(formData.get("note") ?? "").trim();
  if (!essential && !note) return { message: "Say what was agreed with Technical Support." };
  return send(
    eventRequestId,
    equipmentApi,
    `/equipment-requirements/${encodeURIComponent(requirementId)}/essential`,
    "PATCH",
    { essential, note: essential ? null : note },
    {
      "403": "Only the event's coordinator can decide this.",
      "404": "This requirement could not be found, or its event is no longer assigned to you.",
      "409": "This event is closed, so its requirements can't be changed.",
      "422": "Add a note of up to 2,000 characters.",
    },
  );
}
