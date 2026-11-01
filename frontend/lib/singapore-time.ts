// All venues are in Singapore, so event times are entered and shown in Singapore
// time (Q&A #36), whatever the viewer's or server's own time zone is.
export function singaporeInstant(localValue: string): string | null {
  const value = localValue.trim();
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null;
  return `${value}:00+08:00`;
}

// The value a datetime-local input needs for a stored instant, in Singapore time.
export function singaporeLocalValue(instant: string | null | undefined): string {
  if (!instant) return "";
  const shifted = new Date(new Date(instant).getTime() + 8 * 60 * 60 * 1000);
  return Number.isNaN(shifted.getTime()) ? "" : shifted.toISOString().slice(0, 16);
}

// A client-safe date and time for Singapore (lib/event-requests pulls in the server-only
// session code, which a client component must not import).
export function formatSingaporeDateTime(value: string): string {
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Singapore",
  }).format(new Date(value));
}
