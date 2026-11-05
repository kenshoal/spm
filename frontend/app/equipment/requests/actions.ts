"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";
import { equipmentApiUrl } from "@/lib/equipment";

export interface RequestActionState {
  message?: string;
  done?: boolean;
  lines?: string[];
}

const retry = "That could not be done. Please try again.";

async function call(
  method: "POST" | "PATCH",
  path: string,
  body: unknown,
  failures: Record<number, string>,
): Promise<{ state?: RequestActionState; response?: Response }> {
  await requireRole("technical_support");
  let response: Response;
  try {
    response = await sendJson(equipmentApiUrl, path, method, body);
  } catch {
    return { state: { message: retry } };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) return { state: { message: failures[response.status] ?? retry } };
  return { response };
}

const positive = (value: FormDataEntryValue | null): number | null => {
  const text = String(value ?? "").trim();
  return /^\d+$/.test(text) && Number(text) > 0 ? Number(text) : null;
};

// SCRUM-10: is enough suitable equipment free for the event's days at its venue?
export async function checkAvailability(
  requirementId: string,
  equipmentType: string,
  previousState: RequestActionState,
  formData: FormData,
): Promise<RequestActionState> {
  void previousState;
  const quantity = positive(formData.get("quantity"));
  const venueId = String(formData.get("venue_id") ?? "");
  const start = String(formData.get("start_date") ?? "");
  const end = String(formData.get("end_date") ?? "") || start;
  if (!quantity || !venueId || !start) return { message: "Choose a venue, the dates and a quantity." };
  const { state, response } = await call(
    "POST",
    "/equipment/availability-check",
    { start_date: start, end_date: end, venue_id: venueId, items: [{ type: equipmentType, quantity }] },
    { 404: "That venue was not found.", 422: "Check the dates and quantity." },
  );
  if (!response) return state ?? { message: retry };
  const result = (await response.json()) as Record<string, { requested: number; available: number; shortfall: number }>;
  return {
    lines: Object.entries(result).map(([type, row]) =>
      row.shortfall > 0
        ? `${type}: ${row.available} available, ${row.shortfall} short of ${row.requested}.`
        : `${type}: ${row.available} available, enough for ${row.requested}.`,
    ),
  };
}

// SCRUM-13: reserve units of one catalogue row against the requirement.
export async function reserveEquipment(
  requirementId: string,
  previousState: RequestActionState,
  formData: FormData,
): Promise<RequestActionState> {
  void previousState;
  const quantity = positive(formData.get("quantity"));
  const equipmentId = String(formData.get("equipment_id") ?? "");
  const venueId = String(formData.get("venue_id") ?? "");
  const start = String(formData.get("start_date") ?? "");
  const end = String(formData.get("end_date") ?? "") || start;
  if (!quantity || !equipmentId || !venueId || !start) {
    return { message: "Choose the equipment, a venue, the dates and a quantity." };
  }
  const { state } = await call(
    "POST",
    "/equipment-reservations",
    { requirement_id: requirementId, equipment_id: equipmentId, quantity, start_date: start, end_date: end, venue_id: venueId },
    {
      404: "That equipment or venue was not found.",
      409: "That much equipment is not available for those days, or exceeds what the event needs.",
      422: "Check the equipment, dates and quantity.",
    },
  );
  if (state) return state;
  revalidatePath("/equipment/requests");
  return { done: true };
}

// Hotfix 11 (Q&A #114): free a reservation so it can be replaced.
export async function releaseReservation(
  reservationId: string,
  previousState: RequestActionState,
  formData: FormData,
): Promise<RequestActionState> {
  void previousState;
  const reason = String(formData.get("reason") ?? "").trim();
  if (!reason) return { message: "Say why it is being released." };
  const { state } = await call(
    "POST",
    `/equipment-reservations/${encodeURIComponent(reservationId)}/release`,
    { reason },
    { 404: "This reservation no longer exists.", 422: "A reason is required." },
  );
  if (state) return state;
  revalidatePath("/equipment/requests");
  return { done: true };
}

// SCRUM-33 AC3: move the arrangement along, noting what was done.
export async function updateArrangement(
  requirementId: string,
  expectedStatus: string,
  previousState: RequestActionState,
  formData: FormData,
): Promise<RequestActionState> {
  void previousState;
  const status = String(formData.get("status") ?? "");
  const note = String(formData.get("support_note") ?? "").trim();
  if (!["requested", "in_progress", "arranged"].includes(status)) return { message: "Choose a status." };
  const { state } = await call(
    "PATCH",
    `/equipment-requirements/${encodeURIComponent(requirementId)}/arrangement`,
    { expected_status: expectedStatus, status, support_note: note || null },
    {
      409: "Someone else changed this requirement. Refresh and try again.",
      422: "That change is not allowed from the current status.",
    },
  );
  if (state) return state;
  revalidatePath("/equipment/requests");
  return { done: true };
}
