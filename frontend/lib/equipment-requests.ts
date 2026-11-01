import { getJson } from "./api";
import { equipmentApiUrl } from "./equipment";

export type RequirementStatus = "requested" | "in_progress" | "arranged";

export const REQUIREMENT_STATUS_LABELS: Record<RequirementStatus, string> = {
  requested: "Requested",
  in_progress: "In progress",
  arranged: "Arranged",
};

// An event's equipment requirement as equipmentService returns it (SCRUM-33).
export interface EquipmentRequirement {
  id: string;
  event_request_id: string;
  equipment_type: string;
  quantity: number;
  technical_requirements: string | null;
  status: RequirementStatus;
  support_note: string | null;
  event_name: string | null;
  event_date_times: string[];
}

export interface EquipmentReservation {
  id: string;
  requirement_id: string;
  equipment_id: string;
  quantity: number;
  collection_date: string;
  return_date: string;
}

export interface VenueLocation {
  id: string;
  name: string;
}

export async function listEquipmentRequirements(): Promise<EquipmentRequirement[]> {
  return (await getJson<EquipmentRequirement[]>(equipmentApiUrl, "/equipment-requirements")) ?? [];
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
  return (
    (await getJson<EquipmentReservation[]>(
      equipmentApiUrl,
      `/equipment-reservations/by-event/${encodeURIComponent(eventRequestId)}`,
    )) ?? []
  );
}

// The event's first date in Singapore, as a date input needs it (Q&A #36).
export function singaporeDate(instant: string | undefined): string {
  if (!instant) return "";
  const shifted = new Date(new Date(instant).getTime() + 8 * 60 * 60 * 1000);
  return Number.isNaN(shifted.getTime()) ? "" : shifted.toISOString().slice(0, 10);
}

export async function listVenueLocations(): Promise<VenueLocation[]> {
  const { venueApiUrl } = await import("./venues");
  return (await getJson<VenueLocation[]>(venueApiUrl, "/venues/locations")) ?? [];
}
