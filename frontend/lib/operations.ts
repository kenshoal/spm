import { getJson } from "./api";
import type { EventRequest } from "./event-requests";

export interface CoordinatorAssignment {
  id: number;
  event_request_id: string;
  coordinator_id: string;
  assigned_by: string;
  assigned_at: string;
}

export interface CurrentAssignment {
  event_request: EventRequest;
  assignment: CoordinatorAssignment;
}

export interface CoordinatorOption {
  id: string;
  email: string | null;
}

const eventRequestApi = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";
const authServiceUrl = process.env.AUTH_SERVICE_URL ?? "http://127.0.0.1:8001";

export async function listAwaitingAssignment(): Promise<EventRequest[]> {
  return (await getJson<EventRequest[]>(eventRequestApi, "/event-requests/awaiting-assignment")) ?? [];
}

export async function listCurrentAssignments(): Promise<CurrentAssignment[]> {
  return (await getJson<CurrentAssignment[]>(eventRequestApi, "/event-requests/assignments")) ?? [];
}

export async function listCoordinators(): Promise<CoordinatorOption[]> {
  return (await getJson<CoordinatorOption[]>(authServiceUrl, "/auth/users?role=event_coordinator")) ?? [];
}

export function coordinatorLabel(id: string, coordinators: CoordinatorOption[]): string {
  return coordinators.find((coordinator) => coordinator.id === id)?.email ?? id;
}
