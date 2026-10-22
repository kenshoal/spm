import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ChangeRequestPanel } from "@/app/coordination/requests/[id]/change-request-panel";
import { ChangeRequestHistory } from "@/app/components/change-request-history";
import { decideEventChangeRequest } from "@/app/coordination/actions";
import type { EventChangeRequest } from "@/lib/event-requests";

vi.mock("@/app/coordination/actions", () => ({ decideEventChangeRequest: vi.fn() }));
const pending: EventChangeRequest = {
  id: "change-approval-1", event_request_id: "request-approval-1", organiser_id: "organiser-1",
  status: "Pending", explanation: "Use the updated non-date plan.",
  proposed_changes: { expected_attendance: 80, venue_requirements: "Auditorium", equipment_requirements: "Projector", registration_needs: "Accessible online form" },
  base_event_updated_at: "2026-10-20T01:00:00Z", created_at: "2026-10-20T02:00:00Z",
  coordinator_id: null, decision_reason: null, decided_at: null,
};
afterEach(() => { cleanup(); vi.resetAllMocks(); });

// AC3-X3 (cross-cutting): eligible four-field non-date approval including registration text targets the named proposal once and remains pending-safe and recoverable after a refusal.
test("offers exact non-date approval and exposes a recoverable action failure", async () => {
  let finish: (value: { message: string }) => void = () => { throw new Error("Action has not started"); };
  vi.mocked(decideEventChangeRequest).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  render(<ChangeRequestPanel requests={[pending]} eventStatus="Approved" />);
  const button = screen.getByRole("button", { name: "Approve change" });
  expect(screen.getByRole("button", { name: "Reject change" })).toBeDefined();
  fireEvent.click(button);
  await waitFor(() => expect(decideEventChangeRequest).toHaveBeenCalledTimes(1));
  const args = vi.mocked(decideEventChangeRequest).mock.calls[0];
  expect(args.slice(0, 3)).toEqual([pending.event_request_id, pending.id, "Approved"]);
  expect((button as HTMLButtonElement).disabled).toBe(true);
  await act(async () => finish({ message: "The proposal is no longer current. Please refresh." }));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("no longer current"));
  expect((screen.getByRole("button", { name: "Approve change" }) as HTMLButtonElement).disabled).toBe(false);
  expect(decideEventChangeRequest).toHaveBeenCalledTimes(1);
});

// AC3-X4 (cross-cutting): owner history retains the actual approval actor/time and accepted date ranges independently of the requested values or proposal creation time.
test("shows the retained approval audit to the organiser", () => {
  const approved = { ...pending, proposed_changes: { ...pending.proposed_changes, proposed_date_times: ["2026-11-22T03:00:00Z"] }, status: "Approved" as const, coordinator_id: "current-coordinator-35", decided_at: "2026-10-21T10:30:00Z",
    applied_booking_plan: [{ booking_id: "35000000-0000-4000-8000-000000000811", start_date: "2026-11-22", end_date: "2026-11-23", start_minute: 660, end_minute: 750 }] };
  render(<ChangeRequestHistory requests={[approved]} />);
  expect(screen.getByText("Approved", { exact: true })).toBeDefined();
  expect(screen.getByText(/current-coordinator-35/)).toBeDefined();
  expect(screen.getByText(/21 Oct 2026.*6:30 pm/i)).toBeDefined();
  const ranges = within(screen.getByRole("region", { name: "Applied booking ranges" }));
  expect(ranges.getByText(approved.applied_booking_plan[0].booking_id, { exact: false })).toBeDefined();
  expect(ranges.getByText(/2026-11-22|22 Nov 2026/)).toBeDefined();
  expect(ranges.getByText(/2026-11-23|23 Nov 2026/)).toBeDefined();
  expect(ranges.getByText(/11:00/)).toBeDefined();
  expect(ranges.getByText(/12:30/)).toBeDefined();
});
