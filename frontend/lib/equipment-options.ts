// Client-safe equipment constants and types: no import of ./api, ./auth or
// anything else that touches next/headers. lib/equipment.ts re-exports these
// so its public surface is unchanged, but a "use client" component (like
// app/equipment/equipment-form.tsx) can import the runtime values straight
// from here without dragging server-only code into the browser bundle.
export const OPERATIONAL_STATUSES = ["AVAILABLE", "DAMAGED", "UNDER_REPAIR", "UNDER_MAINTENANCE", "RETIRED"] as const;
export type OperationalStatus = (typeof OPERATIONAL_STATUSES)[number];

const LABELS: Record<OperationalStatus, string> = {
  AVAILABLE: "Available",
  DAMAGED: "Damaged",
  UNDER_REPAIR: "Under repair",
  UNDER_MAINTENANCE: "Under maintenance",
  RETIRED: "Retired",
};

export function statusLabel(status: OperationalStatus): string {
  return LABELS[status];
}

export function isOperationalStatus(value: string): value is OperationalStatus {
  return (OPERATIONAL_STATUSES as readonly string[]).includes(value);
}
