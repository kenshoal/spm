import { splitList } from "./venue-form";
import { ROOM_LAYOUTS, timeRangeFrom, type RoomLayout } from "./venue-options";

export type SuitabilityAttribute = "capacity" | "layout" | "facilities" | "accessibility";

export interface SuitabilityResult {
  venue_id: string;
  suitable: boolean;
  mismatches: { attribute: SuitabilityAttribute; reason: string }[];
}

// Raw text as typed on the check form, one field per requirement.
export interface SuitabilityFormValues {
  expected_attendance: string;
  required_layout: string;
  // SCRUM-65: an optional "HH:MM" time range instead of a slot.
  start_time: string;
  end_time: string;
  required_facilities: string;
  required_accessibility: string;
}

export interface SuitabilityPayload {
  expected_attendance: number;
  required_layout?: RoomLayout;
  required_start_minute?: number;
  required_end_minute?: number;
  required_facilities?: string[];
  required_accessibility?: string[];
}

export const ATTRIBUTE_LABELS: Record<SuitabilityAttribute, string> = {
  capacity: "Capacity",
  layout: "Layout",
  facilities: "Facilities",
  accessibility: "Accessibility",
};

// Builds the POST body for /venues/{id}/suitability from raw form text. Only
// requirements that were filled in are sent; a layout outside the backend
// enum is dropped (rather than 422ing); an invalid attendance or time range is
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
  const startTime = (input.start_time ?? "").trim();
  const endTime = (input.end_time ?? "").trim();
  if (startTime || endTime) {
    const times = timeRangeFrom(startTime, endTime);
    if (Object.keys(times.errors).length) return { payload: null, errors: times.errors };
    payload.required_start_minute = times.start_minute;
    payload.required_end_minute = times.end_minute;
  }
  const facilities = splitList(input.required_facilities ?? "");
  if (facilities.length) payload.required_facilities = facilities;
  const accessibility = splitList(input.required_accessibility ?? "");
  if (accessibility.length) payload.required_accessibility = accessibility;
  return { payload, errors: {} };
}
