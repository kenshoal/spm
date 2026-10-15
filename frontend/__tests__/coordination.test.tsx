import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { CoordinationRequestList } from "@/app/coordination/requests/coordination-request-list";
import { TransitionButton } from "@/app/coordination/requests/[id]/transition-buttons";
import { ReviewDecisionPanel } from "@/app/coordination/requests/[id]/review-decision-panel";
import {
  coordinatorActions,
  EVENT_REQUEST_STATUSES,
  type EventRequest,
  type EventRequestStatus,
} from "@/lib/event-requests";

afterEach(cleanup);

vi.mock("@/app/coordination/actions", () => ({
  startEventRequestReview: vi.fn().mockResolvedValue({}),
  startEventPlanning: vi.fn().mockResolvedValue({}),
  cancelEventRequest: vi.fn().mockResolvedValue({}),
  completeEventRequest: vi.fn().mockResolvedValue({}),
  resumeEventRequestReview: vi.fn().mockResolvedValue({}),
  decideEventRequest: vi.fn().mockResolvedValue({}),
}));

import {
  cancelEventRequest,
  completeEventRequest,
  decideEventRequest,
  resumeEventRequestReview,
  startEventPlanning,
  startEventRequestReview,
} from "@/app/coordination/actions";

function makeRequest(status: EventRequestStatus): EventRequest {
  return {
    id: `request-${status.replace(" ", "-").toLowerCase()}`,
    organiser_id: "organiser-1",
    status,
    event_name: `${status} event`,
    purpose: "Mark the anniversary",
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

// Purpose: The coordinator's action buttons mirror the backend transition windows per status.
test("offers only the actions each status allows", () => {
  expect(coordinatorActions("Draft")).toEqual(["cancellation"]);
  expect(coordinatorActions("Submitted")).toEqual(["review", "cancellation"]);
  expect(coordinatorActions("Under Review")).toEqual(["cancellation"]);
  expect(coordinatorActions("Changes Requested")).toEqual(["cancellation"]);
  expect(coordinatorActions("Approved")).toEqual(["planning", "cancellation"]);
  expect(coordinatorActions("Planning")).toEqual(["cancellation"]);
  expect(coordinatorActions("Confirmed")).toEqual(["completion", "cancellation"]);
  expect(coordinatorActions("Completed")).toEqual([]);
  expect(coordinatorActions("Cancelled")).toEqual([]);
  expect(coordinatorActions("Rejected")).toEqual([]);
  for (const status of EVENT_REQUEST_STATUSES) {
    expect(coordinatorActions(status)).toBeDefined();
  }
});

// Purpose: An empty assigned queue explains itself instead of looking broken.
test("shows an empty state when nothing is assigned", () => {
  render(<CoordinationRequestList requests={[]} />);

  expect(screen.getByText("No assigned requests")).toBeDefined();
  expect(screen.getByText(/assigned to you for coordination/i)).toBeDefined();
});

// Purpose: Queue cards open the coordinator's read-only detail route, not the organiser's.
test("links each assigned request to its coordination detail page", () => {
  render(<CoordinationRequestList requests={[makeRequest("Under Review")]} />);

  const links = screen.getAllByRole("link", { name: /under review event/i });
  for (const link of links) {
    expect(link.getAttribute("href")).toBe("/coordination/requests/request-under-review");
  }
});

// Purpose: Starting review is a single deliberate click with no confirmation round trip.
test("starts review immediately without a confirmation dialog", async () => {
  render(<TransitionButton eventRequestId="request-1" kind="review" />);

  expect(screen.queryByRole("alertdialog")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Start review" }));

  await waitFor(() =>
    expect(startEventRequestReview).toHaveBeenCalledWith("request-1", {}, expect.anything()),
  );
});

// Purpose: A returned request can re-enter review after the organiser has responded.
test("continues review through the dedicated transition", async () => {
  render(<TransitionButton eventRequestId="request-1" kind="resume-review" />);

  fireEvent.click(screen.getByRole("button", { name: "Continue review" }));

  await waitFor(() =>
    expect(resumeEventRequestReview).toHaveBeenCalledWith("request-1", {}, expect.anything()),
  );
});

// Purpose: Cancelling an event always requires explicit confirmation first.
test("asks for confirmation before cancelling and acts only once confirmed", async () => {
  render(<TransitionButton eventRequestId="request-2" kind="cancellation" />);

  fireEvent.click(screen.getByRole("button", { name: "Cancel event" }));

  const dialog = screen.getByRole("alertdialog", { name: "Cancel this event?" });
  expect(cancelEventRequest).not.toHaveBeenCalled();

  fireEvent.click(within(dialog).getByRole("button", { name: "Cancel event" }));
  await waitFor(() => expect(cancelEventRequest).toHaveBeenCalled());
});

// Purpose: Marking an event complete also requires explicit confirmation.
test("asks for confirmation before completing", async () => {
  render(<TransitionButton eventRequestId="request-3" kind="completion" />);

  fireEvent.click(screen.getByRole("button", { name: "Mark complete" }));

  const dialog = screen.getByRole("alertdialog", {
    name: "Mark this event complete?",
  });
  expect(completeEventRequest).not.toHaveBeenCalled();

  fireEvent.click(within(dialog).getByRole("button", { name: "Mark complete" }));
  await waitFor(() => expect(completeEventRequest).toHaveBeenCalled());
});

// Purpose: Review controls expose every SCRUM-17 outcome without hiding rejection.
test("offers approve, request clarification and reject decisions", () => {
  render(<ReviewDecisionPanel eventRequestId="request-4" />);

  expect(screen.getByRole("button", { name: "Approve request" })).toBeDefined();
  expect(screen.getByRole("button", { name: "Request clarification" })).toBeDefined();
  expect(screen.getByRole("button", { name: "Reject request" })).toBeDefined();
});

// Purpose: The clarification dialog collects guidance before sending the decision.
test("submits the reason supplied for requested clarification", async () => {
  render(<ReviewDecisionPanel eventRequestId="request-4" />);
  fireEvent.click(screen.getByRole("button", { name: "Request clarification" }));

  const dialog = screen.getByRole("dialog", {
    name: "Request clarification from the organiser",
  });
  fireEvent.change(within(dialog).getByRole("textbox"), {
    target: { value: "Clarify the equipment requirements." },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Request clarification" }));

  await waitFor(() =>
    expect(decideEventRequest).toHaveBeenCalledWith(
      "request-4",
      "Changes Requested",
      {},
      expect.any(FormData),
    ),
  );
});

// AC1-P9 (partition): the planning action is offered for Approved events and for no other status
test("offers start planning only on approved events", () => {
  for (const status of EVENT_REQUEST_STATUSES) {
    expect(coordinatorActions(status).includes("planning")).toBe(status === "Approved");
  }
  expect(coordinatorActions("Approved")[0]).toBe("planning");
});

// AC1-H2 (happy): the coordinator starts planning with one click and no confirmation dialog
test("starts planning immediately without a confirmation dialog", async () => {
  render(<TransitionButton eventRequestId="request-6" kind="planning" />);

  expect(screen.queryByRole("alertdialog")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Start planning" }));

  await waitFor(() =>
    expect(startEventPlanning).toHaveBeenCalledWith("request-6", {}, expect.anything()),
  );
});
