import {
  CLOSE_MINUTE,
  MAX_PREP_MINUTES,
  OPEN_MINUTE,
  PREP_MINUTES_STEP,
  ROOM_LAYOUTS,
  TIME_STEP,
  timeRangeFrom,
  type RoomLayout,
  type VenueStatus,
} from "./venue-options";

export interface VenuePayload {
  name: string;
  location: string;
  max_capacity: number | null;
  facilities: string[];
  accessibility_features: string[];
  supported_layouts: RoomLayout[];
  setup_minutes: number | null;
  turnaround_minutes: number | null;
  operating_start_minute: number | null;
  operating_end_minute: number | null;
  status?: VenueStatus;
  layout_capacities: Partial<Record<RoomLayout, number>>;
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
  setup_minutes: string;
  turnaround_minutes: string;
  operating_start_minute: string;
  operating_end_minute: string;
  status?: string;
  layout_capacities: Record<string, string>;
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

// An opening or closing time as minutes after midnight: blank means the edge of the day
// (the whole 07:00 to 24:00 day), otherwise a whole multiple of 15 inside it, or null when invalid.
function operatingMinute(value: string, blank: number): number | null {
  if (!value) return blank;
  if (!/^\d+$/.test(value)) return null;
  const minutes = Number(value);
  return minutes >= OPEN_MINUTE && minutes <= CLOSE_MINUTE && minutes % TIME_STEP === 0 ? minutes : null;
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
    layout_capacities: Object.fromEntries(
      ROOM_LAYOUTS.map((layout) => [layout, text(formData, `layout_capacity_${layout}`)]),
    ),
    setup_minutes: text(formData, "setup_minutes"),
    turnaround_minutes: text(formData, "turnaround_minutes"),
    operating_start_minute: text(formData, "operating_start_minute"),
    operating_end_minute: text(formData, "operating_end_minute"),
  };
  if (formData.has("status")) values.status = text(formData, "status");
  return values;
}

// Hotfix 12 (Q&A #112): blank means the layout uses the maximum capacity. Anything
// that is not a positive whole number stays out, and the field error below says so.
function layoutCapacities(formData: FormData): Partial<Record<RoomLayout, number>> {
  const capacities: Partial<Record<RoomLayout, number>> = {};
  for (const layout of ROOM_LAYOUTS) {
    const value = text(formData, `layout_capacity_${layout}`);
    if (/^\d+$/.test(value) && Number(value) > 0) capacities[layout] = Number(value);
  }
  return capacities;
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
    layout_capacities: layoutCapacities(formData),
    setup_minutes: prepMinutes(text(formData, "setup_minutes")),
    turnaround_minutes: prepMinutes(text(formData, "turnaround_minutes")),
    operating_start_minute: operatingMinute(text(formData, "operating_start_minute"), OPEN_MINUTE),
    operating_end_minute: operatingMinute(text(formData, "operating_end_minute"), CLOSE_MINUTE),
  };
  if (includeStatus) {
    payload.status = text(formData, "status") === "blocked" ? "blocked" : "available";
  }

  const errors: Record<string, string> = {};
  if (!payload.name) errors.name = "Enter the venue name.";
  if (!payload.location) errors.location = "Enter the venue location.";
  if (capacity === null || capacity <= 0) errors.max_capacity = "Enter a whole number greater than zero.";
  const badLayoutCapacity = ROOM_LAYOUTS.some((layout) => {
    const value = text(formData, `layout_capacity_${layout}`);
    return value !== "" && !(/^\d+$/.test(value) && Number(value) > 0);
  });
  if (badLayoutCapacity) errors.layout_capacities = "Enter a whole number greater than zero, or leave it blank.";
  const prepError = `Enter minutes in steps of ${PREP_MINUTES_STEP}, from 0 to ${MAX_PREP_MINUTES}.`;
  if (payload.setup_minutes === null) errors.setup_minutes = prepError;
  if (payload.turnaround_minutes === null) errors.turnaround_minutes = prepError;
  const { operating_start_minute: opens, operating_end_minute: closes } = payload;
  if (opens === null || closes === null || opens >= closes) {
    errors.operating_hours = "Choose an opening time before the closing time, from 07:00 to 24:00 in steps of 15 minutes.";
  }
  return { payload, errors };
}

export interface VenueSearchInput {
  required_capacity?: string;
  location?: string;
  date?: string;
  start_time?: string;
  end_time?: string;
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
// layout values are dropped (rather than 422ing the backend); an
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
  // SCRUM-65: an optional time range, which needs a date.
  const startTime = (input.start_time ?? "").trim();
  const endTime = (input.end_time ?? "").trim();
  if (startTime || endTime) {
    const times = timeRangeFrom(startTime, endTime);
    if (Object.keys(times.errors).length) Object.assign(errors, times.errors);
    else if (!params.has("date")) errors.date = "Choose a date to search by time.";
    else {
      params.set("start_minute", String(times.start_minute));
      params.set("end_minute", String(times.end_minute));
    }
  }
  const layout = input.layout ?? "";
  if ((ROOM_LAYOUTS as readonly string[]).includes(layout)) params.set("layout", layout);
  for (const item of splitList(input.facility ?? "")) params.append("facility", item);
  for (const item of splitList(input.accessibility ?? "")) params.append("accessibility", item);

  if (Object.keys(errors).length) return { query: null, errors };
  const query = params.toString();
  return { query: query || null, errors };
}
