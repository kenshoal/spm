import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

vi.mock("@/app/operations/actions", () => ({ assignCoordinator: vi.fn().mockResolvedValue({}) }));

import { AssignCoordinatorForm } from "@/app/operations/assignments/assign-coordinator-form";
import { AssignedList, AwaitingList } from "@/app/operations/assignments/assignment-lists";
import type { EventRequest } from "@/lib/event-requests";
import { coordinatorLabel, groupByCoordinator, type CoordinatorOption, type CurrentAssignment } from "@/lib/operations";

afterEach(cleanup);

const coordinators: CoordinatorOption[] = [
  { id: "coord-1", email: "alex@example.com" },
  { id: "coord-2", email: "blair@example.com" },
];

function makeRequest(id: string, name: string): EventRequest {
  return {
    id,
    organiser_id: "organiser-1",
    status: "Submitted",
    event_name: name,
    purpose: "Celebrate",
    description: null,
    proposed_date_times: ["2026-10-20T02:00:00Z"],
    expected_attendance: 80,
    venue_requirements: null,
    accessibility_needs: null,
    equipment_requirements: null,
    registration_needs: null,
    created_at: "2026-09-13T03:00:00Z",
    updated_at: "2026-09-14T03:00:00Z",
  };
}

// Purpose: SCRUM-14 AC1 — each awaiting request is listed with a way to assign it.
test("lists awaiting requests with an assign control each", () => {
  render(<AwaitingList requests={[makeRequest("r1", "Gala Dinner")]} coordinators={coordinators} />);

  const card = screen.getByRole("article", { name: "Gala Dinner" });
  expect(within(card).getByRole("combobox", { name: "Coordinator" })).toBeDefined();
  expect(within(card).getByRole("button", { name: "Assign" })).toBeDefined();
});

// Purpose: An empty queue explains itself instead of looking broken.
test("shows an empty state when nothing awaits assignment", () => {
  render(<AwaitingList requests={[]} coordinators={coordinators} />);

  expect(screen.getByText("Nothing is waiting for a coordinator.")).toBeDefined();
});

// Purpose: SCRUM-14 AC3 — an assigned request shows who is responsible.
test("shows the current coordinator of an assigned request", () => {
  render(
    <AssignedList
      assignments={[{
        event_request: { ...makeRequest("r2", "Tech Summit"), status: "Under Review" },
        assignment: { id: 7, event_request_id: "r2", coordinator_id: "coord-1", assigned_by: "ops-1", assigned_at: "2026-09-20T02:00:00Z" },
      }]}
      coordinators={coordinators}
    />,
  );

  const card = screen.getByRole("article", { name: "Tech Summit" });
  expect(within(card).getByText(/alex@example\.com/)).toBeDefined();
  expect(within(card).getByRole("button", { name: "Reassign" })).toBeDefined();
});

// Purpose: SCRUM-14 AC6 — reassignment never offers the coordinator already responsible.
test("omits the current coordinator from the reassign choices", () => {
  render(<AssignCoordinatorForm eventRequestId="r2" coordinators={coordinators} currentCoordinatorId="coord-1" />);

  const options = within(screen.getByRole("combobox", { name: "Coordinator" })).getAllByRole("option");
  expect(options.map((option) => option.textContent)).toEqual(["Choose a coordinator", "blair@example.com"]);
});

// Purpose: With no one to choose, the form explains why instead of offering an empty picker.
test("explains when no coordinator is available", () => {
  render(<AssignCoordinatorForm eventRequestId="r1" coordinators={[]} />);

  expect(screen.queryByRole("combobox")).toBeNull();
  expect(screen.getByText("No Event Coordinator is available to assign.")).toBeDefined();
});

// Purpose: When the current coordinator is the only one on file, reassignment
// has no one else to offer, so the form says so instead of showing an empty picker.
test("explains when no other coordinator is available to reassign to", () => {
  render(
    <AssignCoordinatorForm
      eventRequestId="r1"
      coordinators={[{ id: "coord-1", email: "alex@example.com" }]}
      currentCoordinatorId="coord-1"
    />,
  );

  expect(screen.queryByRole("combobox")).toBeNull();
  expect(screen.getByText("No other Event Coordinator is available.")).toBeDefined();
});

// Purpose: SCRUM-14 AC6 — the reassign form tells the action who is being replaced.
test("sends the current coordinator as a hidden field when reassigning", () => {
  const { container } = render(
    <AssignCoordinatorForm
      eventRequestId="r2"
      coordinators={coordinators}
      currentCoordinatorId="coord-1"
    />,
  );

  const hidden = container.querySelector('input[name="current_coordinator_id"]');
  expect(hidden).not.toBeNull();
  expect((hidden as HTMLInputElement).value).toBe("coord-1");
});

// Purpose: A fresh assignment has no prior coordinator to report, so no hidden field is sent.
test("omits the hidden current-coordinator field for a fresh assignment", () => {
  const { container } = render(
    <AssignCoordinatorForm eventRequestId="r1" coordinators={coordinators} />,
  );

  expect(container.querySelector('input[name="current_coordinator_id"]')).toBeNull();
});

// Purpose: A coordinator missing from the directory still shows by id rather than blank.
test("labels an unknown coordinator by id", () => {
  expect(coordinatorLabel("coord-9", coordinators)).toBe("coord-9");
  expect(coordinatorLabel("coord-2", coordinators)).toBe("blair@example.com");
});

function makeAssignment(
  requestId: string,
  name: string,
  coordinatorId: string,
  createdAt = "2026-09-13T03:00:00Z",
): CurrentAssignment {
  return {
    event_request: { ...makeRequest(requestId, name), status: "Planning", created_at: createdAt },
    assignment: { id: Number(requestId.replace(/\D/g, "")) || 1, event_request_id: requestId, coordinator_id: coordinatorId, assigned_by: "ops-1", assigned_at: "2026-09-20T02:00:00Z" },
  };
}

// AC3-H1 (happy): SCRUM-62 AC3 — the Lead sees each coordinator's active events under that coordinator, with a count
test("groups assigned events under their coordinator with a count", () => {
  render(
    <AssignedList
      assignments={[
        makeAssignment("r1", "Gala Dinner", "coord-1"),
        makeAssignment("r2", "Tech Summit", "coord-2"),
        makeAssignment("r3", "Book Fair", "coord-1"),
      ]}
      coordinators={coordinators}
    />,
  );

  const alex = screen.getByRole("region", { name: "alex@example.com (2)" });
  expect(within(alex).getAllByRole("article").map((card) => card.getAttribute("aria-labelledby"))).toEqual([
    "request-r1",
    "request-r3",
  ]);
  const blair = screen.getByRole("region", { name: "blair@example.com (1)" });
  expect(within(blair).getByRole("article", { name: "Tech Summit" })).toBeDefined();
  expect(within(blair).queryByRole("article", { name: "Gala Dinner" })).toBeNull();
});

// AC3-P1 (partition): SCRUM-62 AC3 — a coordinator with no active events still appears, so the Lead can see who is free
test("shows coordinators with no active events", () => {
  render(
    <AssignedList
      assignments={[makeAssignment("r1", "Gala Dinner", "coord-1")]}
      coordinators={[...coordinators, { id: "coord-3", email: "casey@example.com" }]}
    />,
  );

  const casey = screen.getByRole("region", { name: "casey@example.com (0)" });
  expect(within(casey).getByText("No active events")).toBeDefined();
  expect(within(casey).queryAllByRole("article")).toHaveLength(0);
  expect(screen.getByRole("region", { name: "blair@example.com (0)" })).toBeDefined();
});

// AC3-X2 (cross-cutting): SCRUM-62 AC3 — each grouped event keeps its reassign control, which never offers its own coordinator
test("keeps a reassign control on every grouped event", () => {
  render(<AssignedList assignments={[makeAssignment("r1", "Gala Dinner", "coord-1")]} coordinators={coordinators} />);

  const card = within(screen.getByRole("region", { name: "alex@example.com (1)" })).getByRole("article", { name: "Gala Dinner" });
  expect(within(card).getByRole("button", { name: "Reassign" })).toBeDefined();
  const options = within(within(card).getByRole("combobox", { name: "Coordinator" })).getAllByRole("option");
  expect(options.map((option) => option.textContent)).toEqual(["Choose a coordinator", "blair@example.com"]);
});

// AC3-P2 (partition): SCRUM-62 AC3 — an event whose coordinator is missing from the directory is grouped under the id, not dropped
test("keeps events whose coordinator is not in the directory", () => {
  const groups = groupByCoordinator([makeAssignment("r1", "Gala Dinner", "coord-z")], []);

  expect(groups.map((group) => [group.coordinatorId, group.label, group.assignments.map((a) => a.event_request.id)])).toEqual([
    ["coord-z", "coord-z", ["r1"]],
  ]);
});

// AC3-X1 (cross-cutting): SCRUM-62 AC3 — groups are sorted by name and events oldest first, whatever order they arrive in
test("orders groups by name and events oldest first", () => {
  const groups = groupByCoordinator(
    [
      makeAssignment("r2", "Second", "coord-1", "2026-09-14T03:00:00Z"),
      makeAssignment("r9", "Blair's", "coord-2"),
      makeAssignment("r1", "First", "coord-1", "2026-09-12T03:00:00Z"),
    ],
    [coordinators[1], coordinators[0]],
  );

  expect(groups.map((group) => group.label)).toEqual(["alex@example.com", "blair@example.com"]);
  expect(groups[0].assignments.map((a) => a.event_request.id)).toEqual(["r1", "r2"]);
});
