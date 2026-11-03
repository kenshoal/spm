// Client-safe: no import of ./api, ./auth or anything that touches next/headers.

// SCRUM-32 AC7: a venue booking can be requested only for these event statuses.
export const VENUE_REQUEST_STATUSES: ReadonlySet<string> = new Set(["Approved", "Planning", "Safety Review"]);

// SCRUM-33 AC6: equipment requirements can be recorded only in these event statuses.
export const EQUIPMENT_RECORDING_STATUSES: ReadonlySet<string> = new Set(["Approved", "Planning", "Safety Review"]);
