import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { ChangeRequestPanel } from "@/app/coordination/requests/[id]/change-request-panel";
import { decideEventChangeRequest } from "@/app/coordination/actions";
import type { EventChangeRequest, EventRequestStatus } from "@/lib/event-requests";

vi.mock("@/app/coordination/actions", () => ({ decideEventChangeRequest: vi.fn() }));

const pending: EventChangeRequest = {
  id: "change-1", event_request_id: "request-1", organiser_id: "organiser-1",
  status: "Pending", explanation: "Registrations exceeded the original estimate.",
  proposed_changes: { expected_attendance: 80 }, base_event_updated_at: "2026-10-19T01:00:00Z",
  coordinator_id: null, decision_reason: null, created_at: "2026-10-19T02:00:00Z", decided_at: null,
};

afterEach(() => { cleanup(); vi.resetAllMocks(); });

// AC4-X1 (cross-cutting): eligible rejection is reasoned, exact-targeted and pending-safe alongside supported non-date approval; failures stay visible.
test("rejects the named Pending proposal and keeps a failed submission recoverable", async () => {
  let finish: (value: { message: string }) => void = () => { throw new Error("Action has not started"); };
  vi.mocked(decideEventChangeRequest).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  render(<ChangeRequestPanel {...{ requests: [pending], eventStatus: "Approved" as EventRequestStatus }} />);
  const button = screen.getByRole("button", { name: "Reject change" });
  expect(screen.getByRole("button", { name: "Approve change" })).toBeDefined();
  const reason = screen.getByRole("textbox", { name: /reason/i });
  expect(reason.getAttribute("required")).not.toBeNull();
  fireEvent.change(reason, { target: { value: "The current booking cannot accommodate this increase." } });
  fireEvent.click(button);
  await waitFor(() => expect(decideEventChangeRequest).toHaveBeenCalledTimes(1));
  const args = vi.mocked(decideEventChangeRequest).mock.calls[0];
  expect(args.slice(0, 3)).toEqual(["request-1", "change-1", "Rejected"]);
  expect(args[4].get("reason")).toBe("The current booking cannot accommodate this increase.");
  expect((button as HTMLButtonElement).disabled).toBe(true);
  await act(async () => finish({ message: "The decision could not be recorded. Please try again." }));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("The decision could not be recorded"));
  expect((screen.getByRole("button", { name: "Reject change" }) as HTMLButtonElement).disabled).toBe(false);
  expect(decideEventChangeRequest).toHaveBeenCalledTimes(1);
});

// AC4-P2, AC4-P3 (partition): a still-Pending proposal cannot expose rejection after current event eligibility has changed.
test.each([
  ["AC4-P2", "Confirmed"], ["AC4-P3", "Safety Review"],
] as const)("%s keeps rejection unavailable when the stored event is %s", (_id, eventStatus) => {
  render(<ChangeRequestPanel {...{ requests: [pending], eventStatus }} />);
  expect(screen.getByText(pending.explanation)).toBeDefined();
  expect(screen.queryByRole("button", { name: "Reject change" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Approve change" })).toBeNull();
  expect(decideEventChangeRequest).not.toHaveBeenCalled();
});
