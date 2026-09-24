import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

vi.mock("@/app/operations/actions", () => ({ assignCoordinator: vi.fn().mockResolvedValue({}) }));

import { AssignCoordinatorForm } from "@/app/operations/assignments/assign-coordinator-form";
import { AssignedList, AwaitingList } from "@/app/operations/assignments/assignment-lists";
import type { EventRequest } from "@/lib/event-requests";
import { coordinatorLabel, type CoordinatorOption } from "@/lib/operations";

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

// Purpose: A coordinator missing from the directory still shows by id rather than blank.
test("labels an unknown coordinator by id", () => {
  expect(coordinatorLabel("coord-9", coordinators)).toBe("coord-9");
  expect(coordinatorLabel("coord-2", coordinators)).toBe("blair@example.com");
});
