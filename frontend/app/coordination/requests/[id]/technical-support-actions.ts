"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { readErrorCode, sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";
import { SKILL_TAGS, validateDescription } from "@/lib/technical-support";

export interface TechnicalSupportActionState {
  message?: string;
}

const eventRequestApi = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

const retryMessage = "The assignment could not be saved. Please try again.";
const failureMessages: Record<number, string> = {
  403: "Only the event's coordinator can arrange technical support.",
  404: "This event or requirement could not be found, or the event is no longer assigned to you.",
  422: "The event request service rejected the details. Check them and try again.",
};

// The database rules' refusal codes (SCRUM-19 D12), in the wording agreed in
// the test catalogue (AC2-X6).
const refusalMessages: Record<string, string> = {
  support_not_allowed:
    "Technical support can only be arranged for approved, planning or confirmed events",
  staff_not_suitable: "This person doesn't hold the required skill",
  already_assigned: "Already assigned to this requirement",
};
const unknownRefusalMessage = "This assignment was refused. Refresh and try again.";

// One POST per action; the API rechecks role, relationship and status inside
// the locked database function, so a stale page can still be refused here.
async function post(
  eventRequestId: string,
  path: string,
  body: unknown,
): Promise<TechnicalSupportActionState> {
  await requireRole("event_coordinator");
  let response: Response;
  try {
    response = await sendJson(eventRequestApi, path, "POST", body);
  } catch {
    return { message: retryMessage };
  }
  // redirect() throws, so it stays outside the try above.
  if (response.status === 401) redirect("/auth");
  if (response.status === 409) {
    const code = await readErrorCode(response);
    return { message: (code && refusalMessages[code]) || unknownRefusalMessage };
  }
  if (!response.ok) {
    return { message: failureMessages[response.status] ?? retryMessage };
  }
  revalidatePath(`/coordination/requests/${eventRequestId}`);
  return {};
}

// Records one requirement: free text plus one skill tag (SCRUM-19 AC1).
export async function recordSupportRequirement(
  previousState: TechnicalSupportActionState,
  formData: FormData,
): Promise<TechnicalSupportActionState> {
  void previousState;
  const eventRequestId = String(formData.get("event_request_id") ?? "").trim();
  const description = validateDescription(formData.get("description"));
  const skillTag = formData.get("skill_tag");
  if (!eventRequestId) return { message: retryMessage };
  if (description === null) {
    return { message: "Describe the support needed (1 to 2000 characters)." };
  }
  if (typeof skillTag !== "string" || !(SKILL_TAGS as readonly string[]).includes(skillTag)) {
    return { message: "Choose one of the four support skills." };
  }
  return post(
    eventRequestId,
    `/event-requests/${encodeURIComponent(eventRequestId)}/technical-support/requirements`,
    { description, skill_tag: skillTag },
  );
}

// Assigns one staff member to one requirement (SCRUM-19 AC2).
export async function assignSupportStaff(
  previousState: TechnicalSupportActionState,
  formData: FormData,
): Promise<TechnicalSupportActionState> {
  void previousState;
  const eventRequestId = String(formData.get("event_request_id") ?? "").trim();
  const requirementId = String(formData.get("requirement_id") ?? "").trim();
  const staffId = String(formData.get("staff_id") ?? "").trim();
  if (!eventRequestId || !requirementId || !staffId) return { message: retryMessage };
  return post(
    eventRequestId,
    `/event-requests/${encodeURIComponent(eventRequestId)}/technical-support/requirements/${encodeURIComponent(requirementId)}/assignments`,
    { staff_id: staffId },
  );
}
