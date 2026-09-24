import { ROOM_LAYOUTS, SLOTS, type RoomLayout, type Slot, type VenueStatus } from "./venues";

export interface VenuePayload {
  name: string;
  location: string;
  max_capacity: number | null;
  facilities: string[];
  accessibility_features: string[];
  supported_layouts: RoomLayout[];
  operating_slots: Slot[];
  status?: VenueStatus;
}

// Comma-separated free text → trimmed, non-empty values, de-duplicated
// case-insensitively (first spelling wins).
export function splitList(value: string): string[] {
  const seen = new Set<string>();
  const items: string[] = [];
  for (const raw of value.split(",")) {
    const item = raw.trim();
    const key = item.toLowerCase();
    if (item && !seen.has(key)) {
      seen.add(key);
      items.push(item);
    }
  }
  return items;
}

function text(formData: FormData, field: string): string {
  return String(formData.get(field) ?? "").trim();
}

// Keeps submission order (tests assert on it) while filtering out values
// outside the backend enum and de-duplicating repeats.
function pick<T extends string>(formData: FormData, field: string, allowed: readonly T[]): T[] {
  const allowedSet = new Set<string>(allowed);
  const seen = new Set<string>();
  const result: T[] = [];
  for (const value of formData.getAll(field).map(String)) {
    if (allowedSet.has(value) && !seen.has(value)) {
      seen.add(value);
      result.push(value as T);
    }
  }
  return result;
}

export function parseVenueForm(
  formData: FormData,
  { includeStatus }: { includeStatus: boolean },
): { payload: VenuePayload; errors: Record<string, string> } {
  const capacityText = text(formData, "max_capacity");
  const capacity = /^\d+$/.test(capacityText) ? Number(capacityText) : null;
  const payload: VenuePayload = {
    name: text(formData, "name"),
    location: text(formData, "location"),
    max_capacity: capacity,
    facilities: splitList(text(formData, "facilities")),
    accessibility_features: splitList(text(formData, "accessibility_features")),
    supported_layouts: pick(formData, "supported_layouts", ROOM_LAYOUTS),
    operating_slots: pick(formData, "operating_slots", SLOTS),
  };
  if (includeStatus) {
    payload.status = text(formData, "status") === "blocked" ? "blocked" : "available";
  }

  const errors: Record<string, string> = {};
  if (!payload.name) errors.name = "Enter the venue name.";
  if (!payload.location) errors.location = "Enter the venue location.";
  if (capacity === null || capacity <= 0) errors.max_capacity = "Enter a whole number greater than zero.";
  if (payload.operating_slots.length === 0) errors.operating_slots = "Choose at least one operating slot.";
  return { payload, errors };
}
