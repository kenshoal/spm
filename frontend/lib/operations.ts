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

export interface CoordinatorGroup {
  coordinatorId: string;
  label: string;
  assignments: CurrentAssignment[];
}

// The Lead's view of who holds what (SCRUM-62 AC3): every coordinator in the
// directory gets a group, even with nothing assigned, so the Lead can see who is
// free. A coordinator missing from the directory still gets a group under their
// id, so no event disappears. Groups sort by name; events oldest first.
export function groupByCoordinator(
  assignments: CurrentAssignment[],
  coordinators: CoordinatorOption[],
): CoordinatorGroup[] {
  const groups = new Map<string, CoordinatorGroup>();
  const groupFor = (id: string) => {
    let group = groups.get(id);
    if (!group) {
      group = { coordinatorId: id, label: coordinatorLabel(id, coordinators), assignments: [] };
      groups.set(id, group);
    }
    return group;
  };
  for (const coordinator of coordinators) groupFor(coordinator.id);
  for (const current of assignments) groupFor(current.assignment.coordinator_id).assignments.push(current);

  const byOldest = (a: CurrentAssignment, b: CurrentAssignment) =>
    a.event_request.created_at.localeCompare(b.event_request.created_at)
    || a.event_request.id.localeCompare(b.event_request.id);
  return [...groups.values()]
    .map((group) => ({ ...group, assignments: [...group.assignments].sort(byOldest) }))
    .sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: "base" })
      || a.coordinatorId.localeCompare(b.coordinatorId));
}
