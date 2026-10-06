import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { ChangeRequestForm } from "@/app/event-requests/[id]/change-request-form";
import { ChangeRequestPanel } from "@/app/coordination/requests/[id]/change-request-panel";
import { RequestList } from "@/app/event-requests/request-list";
import type { EventChangeRequest, EventRequest } from "@/lib/event-requests";

vi.mock("@/app/event-requests/actions", () => ({
  createEventChangeRequest: vi.fn().mockResolvedValue({ submitted: true }),
}));
vi.mock("@/app/coordination/actions", () => ({
  decideEventChangeRequest: vi.fn().mockResolvedValue({}),
}));

import { createEventChangeRequest } from "@/app/event-requests/actions";
import { decideEventChangeRequest } from "@/app/coordination/actions";

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

// AC3-H1 (happy): the assigned coordinator sees and can approve the pending amendment
test("shows proposed values and confirms approval", async () => {
  render(<ChangeRequestPanel eventRequestId="request-1" requests={[pending]} />);
  expect(screen.getByText("80")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Approve change" }));
  const dialog = screen.getByRole("dialog", { name: "Approve this change?" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Approve change" }));

  await waitFor(() =>
    expect(decideEventChangeRequest).toHaveBeenCalledWith(
      "request-1",
      "change-1",
      "Approved",
      {},
      expect.any(FormData),
    ),
  );
});

// AC4-N1 (negative): rejection cannot be sent without a coordinator reason
test("requires a reason when rejecting a change", () => {
  render(<ChangeRequestPanel eventRequestId="request-1" requests={[pending]} />);
  fireEvent.click(screen.getByRole("button", { name: "Reject change" }));
  const dialog = screen.getByRole("dialog", { name: "Reject this change?" });
  expect(within(dialog).getByLabelText("Decision reason").hasAttribute("required")).toBe(true);
});
