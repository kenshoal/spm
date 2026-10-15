import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { StatusProgress } from "@/app/components/status-progress";
import { ReviewDecisionHistory } from "@/app/components/review-decision-history";
import { RequestDetails } from "@/app/components/request-details";
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
  expect(screen.queryByText(/waiting for an Event Coordinator Lead/i)).toBeNull();
  expect(screen.getByRole("listitem", { current: "step" }).textContent).toContain(
    "Submitted",
  );
});

// AC1-H1 (happy): an unassigned submission tells the organiser it waits for the Event Coordinator Lead, not the old role name
test("shows that a submitted request is waiting when no coordinator is assigned", () => {
  render(<StatusProgress status="Submitted" coordinatorAssigned={false} />);

  expect(screen.getByText(/waiting for an Event Coordinator Lead/i)).toBeDefined();
  expect(screen.queryByText(/Operations Manager/i)).toBeNull();
});

// Purpose: Approval and completion stages are announced as done as the event advances.
test("marks Confirmed as current with earlier stages done", () => {
  render(<StatusProgress status="Confirmed" />);

  expect(screen.getByRole("listitem", { current: "step" }).textContent).toContain(
    "Confirmed",
  );
  const stages = screen.getAllByRole("listitem").map((item) => item.textContent);
  expect(stages[0]).toContain("Completed stage: Draft");
  expect(stages[1]).toContain("Completed stage: Submitted");
  expect(stages[2]).toContain("Completed stage: Under Review");
});

// Purpose: A draft still previews the entire journey before submission.
test("shows the full upcoming journey for a draft", () => {
  render(<StatusProgress status="Draft" />);

  expect(screen.getAllByRole("listitem")).toHaveLength(7);
  expect(screen.getByRole("listitem", { current: "step" }).textContent).toContain("Draft");
  expect(screen.getAllByRole("listitem")[6].textContent).toContain("Not reached yet: Completed");
  expect(screen.getByText(/Not submitted yet/)).toBeDefined();
});

// Purpose: Clarification keeps the current review stage and all later stages visible.
test("shows the full journey while clarification is requested", () => {
  render(<StatusProgress status="Changes Requested" />);

  const stages = screen.getAllByRole("listitem").map((item) => item.textContent);
  expect(stages).toHaveLength(7);
  expect(stages[2]).toContain("Current stage: Under Review");
  expect(stages[6]).toContain("Not reached yet: Completed");
  expect(screen.getByText(/clarification response/i)).toBeDefined();
});

// Purpose: A rejected outcome retains the whole journey and marks its stages as not reached.
test("shows the full journey and an explicit notice for rejected", () => {
  render(<StatusProgress status="Rejected" />);

  expect(screen.getAllByRole("listitem")).toHaveLength(7);
  expect(screen.getByText(/later stages shown below were not reached/i)).toBeDefined();
});

// Purpose: A cancelled outcome keeps the normal lifecycle visible for context.
test("shows the full journey and an explicit notice for cancelled", () => {
  render(<StatusProgress status="Cancelled" />);

  expect(screen.getAllByRole("listitem")).toHaveLength(7);
  expect(screen.getByText(/ended as cancelled/i)).toBeDefined();
});

// Purpose: Completion reads as an end state with the final milestone reached.
test("marks Completed as the final reached stage", () => {
  render(<StatusProgress status="Completed" />);

  expect(screen.getByRole("listitem", { current: "step" }).textContent).toContain(
    "Completed",
  );
  expect(screen.getByText(/reached the final stage/i)).toBeDefined();
});

// Purpose: The organiser can read the coordinator's retained clarification reason.
test("shows the review decision and reason", () => {
  render(
    <ReviewDecisionHistory
      decisions={[
        {
          id: 1,
          event_request_id: "request-1",
          coordinator_id: "coordinator-1",
          decision_status: "Changes Requested",
          reason: "Clarify the equipment requirements.",
          decided_at: "2026-09-25T10:00:00Z",
          organiser_response: null,
          responded_at: null,
        },
      ]}
    />,
  );

  expect(screen.getByRole("region", { name: "Review activity" })).toBeDefined();
  expect(screen.getByText("Changes Requested")).toBeDefined();
  expect(screen.getByText("Clarify the equipment requirements.")).toBeDefined();
});

// Purpose: A coordinator sees every submitted field needed for review without receiving edit controls.
test("renders every submitted request field as read-only details", () => {
  const request: EventRequest = {
    ...makeRequest("Under Review"),
    event_name: "Neighbourhood Showcase",
    purpose: "Connect local creators",
    description: "An evening exhibition and networking session.",
    proposed_date_times: ["2026-11-20T02:00:00Z"],
    expected_attendance: 125,
    venue_requirements: "Hall with movable seating",
    accessibility_needs: "Step-free access",
    equipment_requirements: "Projector and two microphones",
    registration_needs: "Online registration desk",
  };

  render(<RequestDetails request={request} coordinatorAssigned />);

  for (const value of [
    "Neighbourhood Showcase",
    "Connect local creators",
    "An evening exhibition and networking session.",
    "125",
    "Hall with movable seating",
    "Step-free access",
    "Projector and two microphones",
    "Online registration desk",
  ]) {
    expect(screen.getByText(value)).toBeDefined();
  }
  expect(screen.getByText(/20 Nov 2026/)).toBeDefined();
  expect(screen.queryByRole("textbox")).toBeNull();
  expect(screen.queryByRole("button", { name: /save|submit|delete/i })).toBeNull();
});

// Purpose: A history outage is visible instead of being mistaken for an empty review record.
test("shows an accessible error when review activity is unavailable", () => {
  render(<ReviewDecisionHistory decisions={[]} unavailable />);

  expect(
    screen.getByRole("alert", { name: "Review activity unavailable" }).textContent,
  ).toMatch(/could not be loaded/i);
});

// Purpose: A final decision must not erase the clarification exchange that informed it.
test("keeps clarification and organiser response visible beside the final decision", () => {
  render(
    <ReviewDecisionHistory
      decisions={[
        {
          id: 2,
          event_request_id: "request-1",
          coordinator_id: "coordinator-1",
          decision_status: "Approved",
          reason: null,
          decided_at: "2026-09-25T11:00:00Z",
          organiser_response: null,
          responded_at: null,
        },
        {
          id: 1,
          event_request_id: "request-1",
          coordinator_id: "coordinator-1",
          decision_status: "Changes Requested",
          reason: "Clarify the equipment requirements.",
          decided_at: "2026-09-25T10:00:00Z",
          organiser_response: "Two wireless microphones are required.",
          responded_at: "2026-09-25T10:30:00Z",
        },
      ]}
    />,
  );

  expect(screen.getByText("Approved")).toBeDefined();
  expect(screen.getByText("Clarify the equipment requirements.")).toBeDefined();
  expect(screen.getByText("Two wireless microphones are required.")).toBeDefined();
});
