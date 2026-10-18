import {
  MAX_PREP_MINUTES,
  PREP_MINUTES_STEP,
  ROOM_LAYOUTS,
  SLOTS,
  type RoomLayout,
  type Slot,
  type VenueStatus,
} from "./venue-options";

export interface VenuePayload {
  name: string;
  location: string;
  max_capacity: number | null;
  facilities: string[];
  accessibility_features: string[];
  supported_layouts: RoomLayout[];
  operating_slots: Slot[];
  setup_minutes: number | null;
  turnaround_minutes: number | null;
  status?: VenueStatus;
}

// Raw text as typed/checked on the form — no parsing, no filtering against
// the backend enums. Used to echo a failed submission back into the form so
// an invalid field (e.g. a non-numeric capacity) shows exactly what the user
// typed instead of silently reverting to a stale stored value.
export interface VenueFormValues {
  name: string;
  location: string;
  max_capacity: string;
  facilities: string;
  accessibility_features: string;
  supported_layouts: string[];
  operating_slots: string[];
  setup_minutes: string;
  turnaround_minutes: string;
  status?: string;
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

// Setup or turnaround minutes: blank means none (0); otherwise a whole multiple
// of 15 from 0 to 1020, or null when invalid.
function prepMinutes(value: string): number | null {
  if (!value) return 0;
  if (!/^\d+$/.test(value)) return null;
  const minutes = Number(value);
  return minutes <= MAX_PREP_MINUTES && minutes % PREP_MINUTES_STEP === 0 ? minutes : null;
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

// Reads the form's raw text/checkbox state, untouched by validation or the
// backend enums — the counterpart to parseVenueForm's typed, filtered
// payload. Status is included only when the field is actually present
// (the create form never renders it).
export function readVenueFormValues(formData: FormData): VenueFormValues {
  const values: VenueFormValues = {
    name: text(formData, "name"),
    location: text(formData, "location"),
    max_capacity: text(formData, "max_capacity"),
    facilities: text(formData, "facilities"),
    accessibility_features: text(formData, "accessibility_features"),
    supported_layouts: formData.getAll("supported_layouts").map(String),
    operating_slots: formData.getAll("operating_slots").map(String),
    setup_minutes: text(formData, "setup_minutes"),
    turnaround_minutes: text(formData, "turnaround_minutes"),
  };
  if (formData.has("status")) values.status = text(formData, "status");
  return values;
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
    setup_minutes: prepMinutes(text(formData, "setup_minutes")),
    turnaround_minutes: prepMinutes(text(formData, "turnaround_minutes")),
  };
  if (includeStatus) {
    payload.status = text(formData, "status") === "blocked" ? "blocked" : "available";
  }

  const errors: Record<string, string> = {};
  if (!payload.name) errors.name = "Enter the venue name.";
  if (!payload.location) errors.location = "Enter the venue location.";
  if (capacity === null || capacity <= 0) errors.max_capacity = "Enter a whole number greater than zero.";
  if (payload.operating_slots.length === 0) errors.operating_slots = "Choose at least one operating slot.";
  const prepError = `Enter minutes in steps of ${PREP_MINUTES_STEP}, from 0 to ${MAX_PREP_MINUTES}.`;
  if (payload.setup_minutes === null) errors.setup_minutes = prepError;
  if (payload.turnaround_minutes === null) errors.turnaround_minutes = prepError;
  return { payload, errors };
}

export interface VenueSearchInput {
  required_capacity?: string;
  location?: string;
  date?: string;
  slot?: string;
  layout?: string;
  facility?: string;
  accessibility?: string;
}

// Rejects a string that matches YYYY-MM-DD but isn't a real calendar date
// (e.g. 2026-13-45 or 2026-02-30, which Date silently rolls over into March).
function isRealCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return false;
  return parsed.toISOString().slice(0, 10) === value;
}

// Builds the query string for GET /venues/search from raw form text. Unknown
// slot/layout values are dropped (rather than 422ing the backend); an
// invalid capacity is reported instead of sent; an empty result (nothing
// filled in, or an error) yields a null query so the page knows not to search.
export function buildVenueSearch(input: VenueSearchInput): { query: string | null; errors: Record<string, string> } {
  const params = new URLSearchParams();
  const errors: Record<string, string> = {};
  const capacity = (input.required_capacity ?? "").trim();
  if (capacity) {
    if (/^\d+$/.test(capacity) && Number(capacity) > 0) params.set("required_capacity", String(Number(capacity)));
    else errors.required_capacity = "Enter a whole number greater than zero.";
  }
  const location = (input.location ?? "").trim();
  if (location) params.set("location", location);
  const date = (input.date ?? "").trim();
  if (isRealCalendarDate(date)) params.set("date", date);
  const slot = input.slot ?? "";
  if ((SLOTS as readonly string[]).includes(slot)) params.set("slot", slot);
  const layout = input.layout ?? "";
  if ((ROOM_LAYOUTS as readonly string[]).includes(layout)) params.set("layout", layout);
  for (const item of splitList(input.facility ?? "")) params.append("facility", item);
  for (const item of splitList(input.accessibility ?? "")) params.append("accessibility", item);

  if (Object.keys(errors).length) return { query: null, errors };
  const query = params.toString();
  return { query: query || null, errors };
}
