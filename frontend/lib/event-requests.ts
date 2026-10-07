import { redirect } from "next/navigation";
import { requireAccessToken } from "./auth";

export const EVENT_REQUEST_STATUSES = [
  "Draft",
  "Submitted",
  "Under Review",
  "Changes Requested",
  "Approved",
  "Planning",
  "Confirmed",
  "Completed",
  "Cancelled",
  "Rejected",
] as const;

export type EventRequestStatus = (typeof EVENT_REQUEST_STATUSES)[number];

export type RequestFilter =
  | "all"
  | "draft"
  | "submitted"
  | "in-progress"
  | "completed";

// One status belongs to exactly one filtered tab; Cancelled and Rejected are
// reachable only through "all" so they stay visible without a Closed tab.
export const STATUS_GROUPS: Record<
  Exclude<RequestFilter, "all">,
  readonly EventRequestStatus[]
> = {
  draft: ["Draft"],
  submitted: ["Submitted"],
  "in-progress": [
    "Under Review",
    "Changes Requested",
    "Approved",
    "Planning",
    "Confirmed",
  ],
  completed: ["Completed"],
};

// Matches the coordinator assignment service's terminal set.
export const COORDINATOR_TERMINAL_STATUSES = [
  "Completed",
  "Cancelled",
  "Rejected",
] as const;

export function isTerminalStatus(status: EventRequestStatus): boolean {
  return (COORDINATOR_TERMINAL_STATUSES as readonly string[]).includes(status);
}

// One badge palette for every workspace so a status looks the same everywhere.
export function statusBadgeClass(status: EventRequestStatus): string {
  if (status === "Cancelled" || status === "Rejected") {
    return "bg-[#fdecea] text-[#8c3a2b]";
  }
  if (status === "Completed") return "bg-[#e3f2ea] text-[#145c40]";
  if (status === "Draft") return "bg-[#eef4f1] text-[#315047]";
  return "bg-[#fff3dc] text-[#80520d]";
}

export type CoordinatorTransition = "review" | "cancellation" | "completion";

// The actions a coordinator may take per status — mirrors the transition
// windows the backend enforces, so the UI never offers an action that 409s.
export function coordinatorActions(
  status: EventRequestStatus,
): CoordinatorTransition[] {
  if (isTerminalStatus(status)) return [];
  const actions: CoordinatorTransition[] = [];
  if (status === "Submitted") actions.push("review");
  if (status === "Confirmed") actions.push("completion");
  actions.push("cancellation");
  return actions;
}

export interface EventRequest {
  id: string;
  organiser_id: string;
  status: EventRequestStatus;
  event_name: string | null;
  purpose: string | null;
  description: string | null;
  proposed_date_times: string[];
  expected_attendance: number | null;
  venue_requirements: string | null;
  accessibility_needs: string | null;
  equipment_requirements: string | null;
  registration_needs: string | null;
  created_at: string;
  updated_at: string;
}

export interface CoordinatorAssignment {
  id: number;
  event_request_id: string;
  coordinator_id: string;
  assigned_by: string;
  assigned_at: string;
}

export interface EventReviewDecision {
  id: number;
  event_request_id: string;
  coordinator_id: string;
  decision_status: "Changes Requested" | "Approved" | "Rejected";
  reason: string | null;
  decided_at: string;
  organiser_response: string | null;
  responded_at: string | null;
}

export type EventChangeRequestStatus = "Pending" | "Approved" | "Rejected";

export interface EventChangeRequest {
  id: string;
  event_request_id: string;
  organiser_id: string;
  status: EventChangeRequestStatus;
  explanation: string;
  proposed_changes: Partial<
    Pick<
      EventRequest,
      | "proposed_date_times"
      | "expected_attendance"
      | "venue_requirements"
      | "equipment_requirements"
      | "registration_needs"
    >
  >;
  base_event_updated_at: string;
  coordinator_id: string | null;
  decision_reason: string | null;
  created_at: string;
  decided_at: string | null;
}

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

async function request(path: string): Promise<Response> {
  const token = await requireAccessToken();
  const response = await fetch(`${apiUrl}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (response.status === 401) redirect("/auth");
  if (!response.ok && response.status !== 404) {
    throw new Error("Event request service unavailable");
  }
  return response;
}

export async function listEventRequests(): Promise<EventRequest[]> {
  const response = await request("/event-requests");
  return response.json() as Promise<EventRequest[]>;
}

export async function listAssignedEventRequests(): Promise<EventRequest[]> {
  const response = await request("/event-requests/assigned-to-me");
  return response.json() as Promise<EventRequest[]>;
}

export async function getEventRequest(id: string): Promise<EventRequest | null> {
  const response = await request(`/event-requests/${encodeURIComponent(id)}`);
  return response.status === 404 ? null : response.json() as Promise<EventRequest>;
}

export async function getCoordinatorAssignment(
  eventRequestId: string,
): Promise<CoordinatorAssignment | null> {
  const response = await request(
    `/event-requests/${encodeURIComponent(eventRequestId)}/coordinator`,
  );
  return response.status === 404
    ? null
    : response.json() as Promise<CoordinatorAssignment>;
}

export async function listReviewDecisions(
  eventRequestId: string,
): Promise<EventReviewDecision[]> {
  const response = await request(
    `/event-requests/${encodeURIComponent(eventRequestId)}/decisions`,
  );
  return response.status === 404
    ? []
    : response.json() as Promise<EventReviewDecision[]>;
}

export async function listEventChangeRequests(
  eventRequestId: string,
): Promise<EventChangeRequest[]> {
  const response = await request(
    `/event-requests/${encodeURIComponent(eventRequestId)}/change-requests`,
  );
  return response.status === 404
    ? []
    : response.json() as Promise<EventChangeRequest[]>;
}

export function groupRequests(
  requests: EventRequest[],
): Record<RequestFilter, EventRequest[]> {
  const groups: Record<RequestFilter, EventRequest[]> = {
    all: [],
    draft: [],
    submitted: [],
    "in-progress": [],
    completed: [],
  };
  for (const request of requests) {
    groups.all.push(request);
    for (const filter of Object.keys(STATUS_GROUPS) as Array<
      Exclude<RequestFilter, "all">
    >) {
      if (STATUS_GROUPS[filter].includes(request.status)) {
        groups[filter].push(request);
      }
    }
  }
  return groups;
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Singapore",
  }).format(new Date(value));
}
