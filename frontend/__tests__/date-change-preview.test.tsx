import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { ChangeRequestPanel } from "@/app/coordination/requests/[id]/change-request-panel";
import { previewEventChangeDatePlan } from "@/app/coordination/actions";
import type { EventChangeRequest } from "@/lib/event-requests";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/coordination/actions", () => ({ decideEventChangeRequest: vi.fn(), previewEventChangeDatePlan: vi.fn(), loadEventChangeBookingPlan: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const pending: EventChangeRequest = {
  id: "35000000-0000-4000-8000-000000000030", event_request_id: "35000000-0000-4000-8000-000000000020", organiser_id: "organiser-1",
  status: "Pending", explanation: "Move the agreed event dates.", proposed_changes: { proposed_date_times: ["2026-11-22T02:00:00Z"] },
  base_event_updated_at: "2026-10-22T01:00:00Z", created_at: "2026-10-22T01:01:00Z", coordinator_id: null, decision_reason: null, decided_at: null,
};
const plan = { event_request_id: pending.event_request_id, change_request_id: pending.id, advisory: true as const, bookings: [{
  booking_id: "35000000-0000-4000-8000-000000000001", venue_id: "35000000-0000-4000-8000-000000000101", status: "pending" as const,
  current_start_date: "2026-11-19", current_end_date: "2026-11-20", proposed_start_date: "2026-11-21", proposed_end_date: "2026-11-22", start_minute: 600, end_minute: 720,
}] };

// AC3-X10 (cross-cutting): an advisory is loaded only on demand, cannot appear as approval, and remains distinguishable across pending, failed, empty and concrete results.
test("previews dates with recoverable loading and honest empty/success states", async () => {
  let finish!: (value: { message: string }) => void;
  vi.mocked(previewEventChangeDatePlan).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  render(<ChangeRequestPanel requests={[pending]} eventStatus="Approved" />);
  const button = screen.getByRole("button", { name: "Preview date changes" }) as HTMLButtonElement;
  expect(previewEventChangeDatePlan).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Approve change" })).toBeNull();
  expect(screen.getByText(/Preview only.*No changes have been made.*complete booking plan/i)).toBeDefined();
  fireEvent.click(button);
  await waitFor(() => expect(previewEventChangeDatePlan).toHaveBeenCalledTimes(1));
  expect(vi.mocked(previewEventChangeDatePlan).mock.calls[0].slice(0, 2)).toEqual([pending.event_request_id, pending.id]);
  expect(button.disabled).toBe(true);
  await act(async () => finish({ message: "Date change plan unavailable" }));
  expect(screen.getByRole("alert").textContent).toContain("Date change plan unavailable");
  expect((screen.getByRole("button", { name: "Preview date changes" }) as HTMLButtonElement).disabled).toBe(false);
  vi.mocked(previewEventChangeDatePlan).mockResolvedValueOnce({ plan: { ...plan, bookings: [] } });
  fireEvent.click(screen.getByRole("button", { name: "Preview date changes" }));
  await waitFor(() => expect(screen.getByText("No pending or approved venue bookings to move.")).toBeDefined());
  expect(screen.queryByRole("alert")).toBeNull();
  vi.mocked(previewEventChangeDatePlan).mockResolvedValueOnce({ plan });
  fireEvent.click(screen.getByRole("button", { name: "Preview date changes" }));
  const region = await screen.findByRole("region", { name: "Date change preview" });
  await waitFor(() => expect(region.textContent).toContain(plan.bookings[0].booking_id));
  for (const day of ["19", "20", "21", "22"]) expect(region.textContent).toMatch(new RegExp(`${day} Nov 2026|2026-11-${day}`));
  expect(region.textContent).toMatch(/10:00/);
  expect(region.textContent).toMatch(/12:00/);
  expect(screen.queryByRole("button", { name: "Approve change" })).toBeNull();
  expect(previewEventChangeDatePlan).toHaveBeenCalledTimes(3);
});
