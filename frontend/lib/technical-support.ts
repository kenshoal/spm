import { getJson } from "./api";
import type {
  Candidate,
  StaffOption,
  TechnicalSupportRequirement,
} from "./technical-support-options";

export * from "./technical-support-options";

const eventRequestApi = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";
const authServiceUrl = process.env.AUTH_SERVICE_URL ?? "http://127.0.0.1:8001";

export async function listEventTechnicalSupport(
  eventRequestId: string,
): Promise<TechnicalSupportRequirement[]> {
  return (
    (await getJson<TechnicalSupportRequirement[]>(
      eventRequestApi,
      `/event-requests/${encodeURIComponent(eventRequestId)}/technical-support`,
    )) ?? []
  );
}

export async function listCandidates(
  eventRequestId: string,
  requirementId: string,
): Promise<Candidate[]> {
  return (
    (await getJson<Candidate[]>(
      eventRequestApi,
      `/event-requests/${encodeURIComponent(eventRequestId)}/technical-support/requirements/${encodeURIComponent(requirementId)}/candidates`,
    )) ?? []
  );
}

// A coordinator the authService does not let list technical_support (or any
// other listing failure) still gets a usable panel: labels fall back to ids.
export async function listTechnicalSupportStaff(): Promise<StaffOption[]> {
  try {
    return (
      (await getJson<StaffOption[]>(authServiceUrl, "/auth/users?role=technical_support")) ??
      []
    );
  } catch {
    return [];
  }
}
