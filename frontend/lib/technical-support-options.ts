// Pure technical-support vocabulary and types. Client components import from
// here; the loaders that need the bearer token live in technical-support.ts.

// The fixed skill vocabulary mirrors the API model and the database CHECK
// constraints; a single source of truth belongs to the future
// maintain-staff-skills story (test matrix, open question 7).
export const SKILL_TAGS = [
  "audio_visual",
  "lighting",
  "it_network",
  "livestream",
] as const;

export type SkillTag = (typeof SKILL_TAGS)[number];

// Written out everywhere they are shown; the select offers these four only.
export const SKILL_TAG_LABELS: Record<SkillTag, string> = {
  audio_visual: "Audio-visual",
  lighting: "Lighting",
  it_network: "IT and network",
  livestream: "Livestream",
};

export function skillLabel(skillTag: string): string {
  return SKILL_TAG_LABELS[skillTag as SkillTag] ?? skillTag;
}

// Requirements may be recorded and staff assigned only in these statuses. The
// API rechecks inside the locked database function; this only hides controls
// that could no longer succeed.
export const SUPPORT_STATUSES = ["Approved", "Planning", "Confirmed"] as const;

export function supportsTechnicalSupport(status: string): boolean {
  return (SUPPORT_STATUSES as readonly string[]).includes(status);
}

export interface AssignedStaff {
  staff_id: string;
  assigned_by: string;
  assigned_at: string;
}

// Mirrors EventTechnicalSupportResponse: one requirement with everyone
// assigned to it, in stable order.
export interface TechnicalSupportRequirement {
  id: string;
  event_request_id: string;
  description: string;
  skill_tag: SkillTag;
  recorded_by: string;
  recorded_at: string;
  assigned_staff: AssignedStaff[];
}

export interface Candidate {
  staff_id: string;
  already_assigned: boolean;
}

export interface StaffOption {
  id: string;
  email: string | null;
}

export function staffLabel(staffId: string, staff: StaffOption[]): string {
  return staff.find((person) => person.id === staffId)?.email ?? staffId;
}

export const DESCRIPTION_MAX = 2000;

// Counts the description the way the API (Python len) and the database
// (char_length) do: after trimming, in characters, so an emoji counts once.
export function descriptionLength(text: string): number {
  return Array.from(text.trim()).length;
}

export function validateDescription(text: FormDataEntryValue | null): string | null {
  const trimmed = typeof text === "string" ? text.trim() : "";
  const length = descriptionLength(trimmed);
  return length >= 1 && length <= DESCRIPTION_MAX ? trimmed : null;
}

// Names a person on the panel: the signed-in coordinator is "you", staff by
// email, anyone else by id.
export function personLabel(
  personId: string,
  staff: StaffOption[],
  currentUserId?: string,
): string {
  return currentUserId !== undefined && personId === currentUserId
    ? "you"
    : staffLabel(personId, staff);
}
