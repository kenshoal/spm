import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { StatusProgress } from "@/app/components/status-progress";
import {
  EVENT_REQUEST_STATUSES,
  groupRequests,
  isTerminalStatus,
  type EventRequest,
  type EventRequestStatus,
} from "@/lib/event-requests";

afterEach(cleanup);

function makeRequest(status: EventRequestStatus): EventRequest {
  return {
    id: `request-${status.replace(" ", "-").toLowerCase()}`,
    organiser_id: "organiser-1",
    status,
    event_name: `${status} event`,
    purpose: "Mark the anniversary",
    description: null,
    proposed_date_times: [],
    expected_attendance: null,
    venue_requirements: null,
    accessibility_needs: null,
    equipment_requirements: null,
    registration_needs: null,
    created_at: "2026-09-13T03:00:00Z",
    updated_at: "2026-09-14T03:00:00Z",
  };
}

// Purpose: Every backend status is representable — the UI never drops a workflow state.
test("covers all ten event request statuses", () => {
  expect(EVENT_REQUEST_STATUSES).toEqual([
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
  ]);
});

// Purpose: Each status lands in exactly one tab — or only under All once closed.
test("groups every status into exactly one tab plus all", () => {
  const requests = EVENT_REQUEST_STATUSES.map(makeRequest);
  const groups = groupRequests(requests);

  expect(groups.all).toHaveLength(EVENT_REQUEST_STATUSES.length);
  const tabbed = [...groups.draft, ...groups.submitted, ...groups["in-progress"], ...groups.completed];
  expect(tabbed).toHaveLength(EVENT_REQUEST_STATUSES.length - 2);
  expect(new Set(tabbed.map((request) => request.status))).toEqual(
    new Set([
      "Draft",
      "Submitted",
      "Under Review",
      "Changes Requested",
      "Approved",
      "Planning",
      "Confirmed",
      "Completed",
    ]),
  );
});

// Purpose: A completed event shows under Completed without a hard-coded empty list.
test("files Completed requests under the completed tab", () => {
  const groups = groupRequests([makeRequest("Completed")]);

  expect(groups.completed.map((request) => request.status)).toEqual(["Completed"]);
  expect(groups["in-progress"]).toEqual([]);
});

// Purpose: Requests stay visible as they advance past Submitted into coordination.
test("keeps in-progress statuses visible after leaving Submitted", () => {
  const inProgress = ["Under Review", "Changes Requested", "Approved", "Planning", "Confirmed"] as const;
  const groups = groupRequests(inProgress.map(makeRequest));

  expect(groups.submitted).toEqual([]);
  expect(groups["in-progress"].map((request) => request.status)).toEqual([
    ...inProgress,
  ]);
});

// Purpose: Cancelled and Rejected stay reachable through All only — no Closed tab.
test("shows closed statuses only under all", () => {
  const groups = groupRequests([makeRequest("Cancelled"), makeRequest("Rejected")]);

  expect(groups.all).toHaveLength(2);
  expect(groups.draft).toEqual([]);
  expect(groups.submitted).toEqual([]);
  expect(groups["in-progress"]).toEqual([]);
  expect(groups.completed).toEqual([]);
});

// Purpose: The coordinator action window excludes terminal statuses.
test("treats only Completed, Cancelled and Rejected as terminal", () => {
  const terminal = EVENT_REQUEST_STATUSES.filter(isTerminalStatus);

  expect(terminal).toEqual(["Completed", "Cancelled", "Rejected"]);
});

// Purpose: The progress stepper marks the request's current milestone for screen readers.
test("marks the current stage for an in-flight request", () => {
  render(<StatusProgress status="Under Review" />);

  const current = screen.getByRole("listitem", { current: "step" });
  expect(current.textContent).toContain("Under Review");
});

// Purpose: Submitted copy reflects a known assignment without changing workflow status.
test("shows that a submitted request has an assigned coordinator", () => {
  render(<StatusProgress status="Submitted" coordinatorAssigned />);

  expect(screen.getByText(/coordinator has been assigned/i)).toBeDefined();
  expect(screen.queryByText(/waiting for an Event Operations Manager/i)).toBeNull();
  expect(screen.getByRole("listitem", { current: "step" }).textContent).toContain(
    "Submitted",
  );
});

// Purpose: An unassigned submission still tells the organiser what it is waiting for.
test("shows that a submitted request is waiting when no coordinator is assigned", () => {
  render(<StatusProgress status="Submitted" coordinatorAssigned={false} />);

  expect(screen.getByText(/waiting for an Event Operations Manager/i)).toBeDefined();
});

// Purpose: Approval and completion stages are announced as done as the event advances.
test("marks Confirmed as current with earlier stages done", () => {
  render(<StatusProgress status="Confirmed" />);

  expect(screen.getByRole("listitem", { current: "step" }).textContent).toContain(
    "Confirmed",
  );
  const stages = screen.getAllByRole("listitem").map((item) => item.textContent);
  expect(stages[0]).toContain("Completed stage: Submitted");
  expect(stages[1]).toContain("Completed stage: Under Review");
});

// Purpose: A draft shows no milestones — nothing has entered the workflow yet.
test("shows description only for a draft", () => {
  render(<StatusProgress status="Draft" />);

  expect(screen.queryByRole("list")).toBeNull();
  expect(screen.getByText(/Not submitted yet/)).toBeDefined();
});

// Purpose: A changes-requested request points the organiser at resubmission, not later stages.
test("stops the stepper at Under Review with a changes-requested notice", () => {
  render(<StatusProgress status="Changes Requested" />);

  const stages = screen.getAllByRole("listitem").map((item) => item.textContent);
  expect(stages).toHaveLength(2);
  expect(stages[1]).toContain("Current stage: Under Review");
  expect(screen.getByText(/update and resubmit/i)).toBeDefined();
});

// Purpose: A rejected request explains the outcome instead of implying later stages exist.
test("shows an explicit notice without a stepper for rejected", () => {
  render(<StatusProgress status="Rejected" />);

  expect(screen.queryByRole("list")).toBeNull();
  expect(screen.getByText(/No further stages will follow/)).toBeDefined();
});

// Purpose: A cancelled request explains the outcome instead of implying later stages exist.
test("shows an explicit notice without a stepper for cancelled", () => {
  render(<StatusProgress status="Cancelled" />);

  expect(screen.queryByRole("list")).toBeNull();
  expect(screen.getByText(/was cancelled/i)).toBeDefined();
});

// Purpose: Completion reads as an end state with the final milestone reached.
test("marks Completed as the final reached stage", () => {
  render(<StatusProgress status="Completed" />);

  expect(screen.getByRole("listitem", { current: "step" }).textContent).toContain(
    "Completed",
  );
  expect(screen.getByText(/has finished/i)).toBeDefined();
});
