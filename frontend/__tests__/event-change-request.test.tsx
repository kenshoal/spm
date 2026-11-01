import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { ChangeRequestForm } from "@/app/event-requests/[id]/change-request-form";
import { ChangeRequestPanel } from "@/app/coordination/requests/[id]/change-request-panel";
import { RequestList } from "@/app/event-requests/request-list";
import type { EventChangeRequest, EventRequest } from "@/lib/event-requests";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/coordination/actions", () => ({ decideEventChangeRequest: vi.fn(), decideEventChangeRequestPartly: vi.fn(), loadEventChangeBookingPlan: vi.fn() }));

vi.mock("@/app/event-requests/actions", () => ({
  createEventChangeRequest: vi.fn().mockResolvedValue({ submitted: true }),
}));

import { createEventChangeRequest } from "@/app/event-requests/actions";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const pending: EventChangeRequest = {
  id: "change-1",
  event_request_id: "request-1",
  organiser_id: "organiser-1",
  status: "Pending",
  explanation: "Increase attendance after registrations.",
  proposed_changes: { expected_attendance: 80 },
  base_event_updated_at: "2026-10-04T01:00:00Z",
  coordinator_id: null,
  decision_reason: null,
  created_at: "2026-10-04T02:00:00Z",
  decided_at: null,
};

const approvedEvent: EventRequest = {
  id: "request-1",
  organiser_id: "organiser-1",
  status: "Approved",
  event_name: "Community Forum",
  purpose: "Gather neighbours",
  description: "An approved event",
  proposed_date_times: ["2026-11-20T02:00:00Z"],
  expected_attendance: 40,
  venue_requirements: "Seminar room",
  accessibility_needs: "Step-free access",
  equipment_requirements: "Projector",
  registration_needs: "Online registration",
  created_at: "2026-10-04T01:00:00Z",
  updated_at: "2026-10-04T02:00:00Z",
};

// AC1-X1 (cross-cutting): eligible events expose the change workflow from the organiser list
test("links approved and planning events to change requests", () => {
  render(<RequestList requests={[approvedEvent, { ...approvedEvent, id: "request-2", status: "Planning" }, { ...approvedEvent, id: "request-3", status: "Submitted" }]} />);

  const changeLinks = screen.getAllByRole("link", { name: "Change requests" });
  expect(changeLinks.map((link) => link.getAttribute("href"))).toEqual([
    "/event-requests/request-1/edit",
    "/event-requests/request-2/edit",
  ]);
  expect(screen.getByRole("link", { name: "View request" })).toBeDefined();
});

// AC1-H1 (happy): the organiser can submit a structured attendance amendment
test("submits an organiser change request", async () => {
  render(<ChangeRequestForm eventRequestId="request-1" />);
  fireEvent.change(screen.getByLabelText("Reason for change"), {
    target: { value: "Increase attendance after registrations." },
  });
  fireEvent.change(screen.getByLabelText("Proposed attendance"), {
    target: { value: "80" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Request change" }));

  await waitFor(() =>
    expect(createEventChangeRequest).toHaveBeenCalledWith(
      "request-1",
      {},
      expect.any(FormData),
    ),
  );
});


// AC4-X1 (cross-cutting): a mixed date proposal remains visible and rejectable while approval waits for deliberate complete-booking-plan review
test("shows mixed changes with booking review and rejection before approval", () => {
  render(<ChangeRequestPanel requests={[{ ...pending, proposed_changes: { ...pending.proposed_changes, proposed_date_times: ["2026-11-20T02:00:00Z"] } }]} eventStatus="Approved" />);
  expect(screen.getByText(pending.explanation)).toBeDefined();
  expect(screen.getByText("80")).toBeDefined();
  expect(screen.getByRole("button", { name: "Review booking plan" })).toBeDefined();
  expect(screen.queryByRole("button", { name: "Approve change" })).toBeNull();
  expect(screen.getByRole("button", { name: "Reject change" })).toBeDefined();
});


// AC2-X3 (cross-cutting): organiser guidance distinguishes routine field approval from complete booking-plan review and whole-batch conflict refusal.
test("explains supported fields and the complete plan required for date approval", () => {
  render(<ChangeRequestForm eventRequestId="request-1" />);

  expect(screen.getByText(/attendance.*venue.*equipment.*registration.*approv/i)).toBeDefined();
  expect(screen.getByText(/Date changes require.*complete.*booking plan.*entire.*refused.*conflicts/i)).toBeDefined();
  expect(screen.queryByText(/Approval is unavailable;/i)).toBeNull();
  expect(screen.getByRole("button", { name: "Request change" })).toBeDefined();
  expect(screen.getByLabelText("Reason for change")).toBeDefined();
});
