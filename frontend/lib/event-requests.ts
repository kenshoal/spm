import { redirect, unstable_rethrow } from "next/navigation";
import { requireAccessToken } from "./auth";

export const EVENT_REQUEST_STATUSES = [
  "Draft",
  "Submitted",
  "Under Review",
  "Changes Requested",
  "Approved",
  "Planning",
  "Safety Review",
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
    "Safety Review",
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

export type CoordinatorTransition =
  | "review"
  | "planning"
  | "safety-review"
  | "cancellation"
  | "completion";

// The actions a coordinator may take per status — mirrors the transition
// windows the backend enforces, so the UI never offers an action that 409s.
export function coordinatorActions(
  status: EventRequestStatus,
): CoordinatorTransition[] {
  if (isTerminalStatus(status)) return [];
  const actions: CoordinatorTransition[] = [];
  if (status === "Submitted") actions.push("review");
  if (status === "Approved") actions.push("planning");
  if (status === "Planning") actions.push("safety-review");
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
  final_event_end_at?: string | null;
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

export interface EventChangeBookingPlanItem {
  booking_id: string;
  start_date: string;
  end_date: string;
  start_minute: number;
  end_minute: number;
}

export interface EventChangeBookingConflict {
  booking_id: string;
  refusal_codes: string[];
  conflicting_booking_ids: string[];
  conflicting_block_ids: string[];
}

export interface EventChangeBookingPlan {
  event_request_id: string;
  change_request_id: string;
  event_updated_at: string;
  bookings: (EventChangeBookingPlanItem & { venue_id: string; status: "pending" | "approved" })[];
  automatic_plan: EventChangeBookingPlanItem[] | null;
  automatic_plan_error: "unsupported_date_mapping" | "no_op_date_mapping" | null;
}

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
  applied_booking_plan?: EventChangeBookingPlanItem[] | null;
}

/** A read-only snapshot; these candidates are not availability or approval. */
export interface EventChangeDatePlan {
  event_request_id: string;
  change_request_id: string;
  advisory: true;
  bookings: {
    booking_id: string;
    venue_id: string;
    status: "pending" | "approved";
    current_start_date: string;
    current_end_date: string;
    proposed_start_date: string;
    proposed_end_date: string;
    start_minute: number;
    end_minute: number;
  }[];
}

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

export interface EventStatusHistory {
  id: number;
  event_request_id: string;
  previous_status: EventRequestStatus | null;
  new_status: EventRequestStatus;
  actor_id: string | null;
  actor_role: string;
  source: string;
  entry_kind: 'created' | 'transition' | 'baseline';
  occurred_at: string;
}

async function request(path: string, signal?: AbortSignal): Promise<Response> {
  const token = await requireAccessToken();
  const response = await fetch(`${apiUrl}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
    ...(signal ? { signal } : {}),
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

export async function getEventRequest(id: string, signal?: AbortSignal): Promise<EventRequest | null> {
  const response = await request(`/event-requests/${encodeURIComponent(id)}`, signal);
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

export async function listStatusHistory(eventRequestId: string, signal?: AbortSignal): Promise<EventStatusHistory[]> {
  const response = await request(`/event-requests/${encodeURIComponent(eventRequestId)}/status-history`, signal);
  // A revoked relationship is not a successful empty audit trail.
  if (response.status === 404) throw new Error('Status history is not accessible');
  return response.json() as Promise<EventStatusHistory[]>;
}

export interface EventRequestStatusView {
  request: EventRequest | null;
  history: EventStatusHistory[];
  historyUnavailable: boolean;
  statusUnsettled: boolean;
}

/** Reconcile separate reads before details, timeline and status actions render. */
export async function getEventRequestStatusView(id: string): Promise<EventRequestStatusView> {
  let current = await getEventRequest(id);
  if (!current) {
    return { request: null, history: [], historyUnavailable: false, statusUnsettled: false };
  }

  let statusUnsettled = false;
  try {
    let history = await listStatusHistory(id);
    if (history.length > 0 && history[history.length - 1].new_status !== current.status) {
      // Retry once: a transition can commit between the event and history reads.
      statusUnsettled = true;
      // Signals bypass Next render-pass memoisation so the retry is genuinely fresh.
      const { signal } = new AbortController();
      current = await getEventRequest(id, signal);
      if (!current) {
        return { request: null, history: [], historyUnavailable: false, statusUnsettled: false };
      }
      history = await listStatusHistory(id, signal);
      statusUnsettled = history.length > 0 && history[history.length - 1].new_status !== current.status;
    }
    return {
      request: current,
      history: statusUnsettled ? [] : history,
      historyUnavailable: statusUnsettled,
      statusUnsettled,
    };
  } catch (error: unknown) {
    unstable_rethrow(error);
    return { request: current, history: [], historyUnavailable: true, statusUnsettled };
  }
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

/** Fetch the saved proposal's advisory plan using the verified server session. */
export async function getEventChangeDatePlan(
  eventRequestId: string,
  changeRequestId: string,
): Promise<EventChangeDatePlan | null> {
  const token = await requireAccessToken();
  const response = await fetch(
    `${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}/change-requests/${encodeURIComponent(changeRequestId)}/date-plan`,
    { method: "GET", headers: { Authorization: `Bearer ${token}` }, cache: "no-store" },
  );
  if (response.status === 401) redirect("/auth");
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("Date change plan unavailable");
  return response.json() as Promise<EventChangeDatePlan>;
}

/** Complete advisory input for the exact saved proposal, never a write lease. */
export async function getEventChangeBookingPlan(eventRequestId: string, changeRequestId: string): Promise<EventChangeBookingPlan | null> {
  const token = await requireAccessToken();
  const response = await fetch(`${apiUrl}/event-requests/${encodeURIComponent(eventRequestId)}/change-requests/${encodeURIComponent(changeRequestId)}/booking-plan`, {
    method: "GET", headers: { Authorization: `Bearer ${token}` }, cache: "no-store",
  });
  if (response.status === 401) redirect("/auth");
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("Booking plan unavailable");
  return response.json() as Promise<EventChangeBookingPlan>;
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
