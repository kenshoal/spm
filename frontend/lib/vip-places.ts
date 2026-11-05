// Client-safe (no session code), so a component can use it without the registration-info fetch.

/** Hotfix 23 (Q&A #99): how many more people a Coordinator may add above normal registration. */
export function vipPlaces(info: {
  registered: number;
  registration_capacity: number | null;
  venue_capacity?: number | null;
}): number {
  if (info.registration_capacity === null || info.registration_capacity === undefined) return 0;
  if (info.registered < info.registration_capacity) return 0;
  return Math.max((info.venue_capacity ?? 0) - info.registered, 0);
}
