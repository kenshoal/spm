import { splitList } from "./venue-form";
import { ROOM_LAYOUTS, SLOTS, type RoomLayout, type Slot } from "./venue-options";

export type SuitabilityAttribute = "capacity" | "layout" | "operating_slot" | "facilities" | "accessibility";

export interface SuitabilityResult {
  venue_id: string;
  suitable: boolean;
  mismatches: { attribute: SuitabilityAttribute; reason: string }[];
}

// Raw text as typed on the check form, one field per requirement.
export interface SuitabilityFormValues {
  expected_attendance: string;
  required_layout: string;
  required_slot: string;
  required_facilities: string;
  required_accessibility: string;
}

export interface SuitabilityPayload {
  expected_attendance: number;
  required_layout?: RoomLayout;
  required_slot?: Slot;
  required_facilities?: string[];
  required_accessibility?: string[];
}

export const ATTRIBUTE_LABELS: Record<SuitabilityAttribute, string> = {
  capacity: "Capacity",
  layout: "Layout",
  operating_slot: "Operating slot",
  facilities: "Facilities",
  accessibility: "Accessibility",
};

// Builds the POST body for /venues/{id}/suitability from raw form text. Only
// requirements that were filled in are sent; a layout or slot outside the
// backend enums is dropped (rather than 422ing); an invalid attendance is
// reported instead of sent.
export function buildSuitabilityRequest(input: Partial<SuitabilityFormValues>): {
  payload: SuitabilityPayload | null;
  errors: Record<string, string>;
} {
  const attendance = (input.expected_attendance ?? "").trim();
  if (!/^\d+$/.test(attendance) || Number(attendance) <= 0) {
    return { payload: null, errors: { expected_attendance: "Enter a whole number greater than zero." } };
  }
  const payload: SuitabilityPayload = { expected_attendance: Number(attendance) };
  const layout = input.required_layout ?? "";
  if ((ROOM_LAYOUTS as readonly string[]).includes(layout)) payload.required_layout = layout as RoomLayout;
  const slot = input.required_slot ?? "";
  if ((SLOTS as readonly string[]).includes(slot)) payload.required_slot = slot as Slot;
  const facilities = splitList(input.required_facilities ?? "");
  if (facilities.length) payload.required_facilities = facilities;
  const accessibility = splitList(input.required_accessibility ?? "");
  if (accessibility.length) payload.required_accessibility = accessibility;
  return { payload, errors: {} };
}
