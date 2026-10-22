import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ChangeRequestPanel } from "@/app/coordination/requests/[id]/change-request-panel";
import { decideEventChangeRequest, loadEventChangeBookingPlan } from "@/app/coordination/actions";
import type { EventChangeBookingPlan, EventChangeRequest } from "@/lib/event-requests";

const refresh = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("@/app/coordination/actions", () => ({ decideEventChangeRequest: vi.fn(), loadEventChangeBookingPlan: vi.fn(), previewEventChangeDatePlan: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const pending: EventChangeRequest = {
  id: "35000000-0000-4000-8000-000000000031", event_request_id: "35000000-0000-4000-8000-000000000021", organiser_id: "organiser-1",
  status: "Pending", explanation: "Move both sessions and update attendance.",
  proposed_changes: { proposed_date_times: ["2026-11-22T03:00:00Z", "2026-11-24T08:00:00Z"], expected_attendance: 40 },
  base_event_updated_at: "2026-10-22T01:00:00Z", created_at: "2026-10-22T01:01:00Z", coordinator_id: null, decision_reason: null, decided_at: null,
};
const context: EventChangeBookingPlan = {
  event_request_id: pending.event_request_id, change_request_id: pending.id, event_updated_at: pending.base_event_updated_at,
  automatic_plan: null, automatic_plan_error: "unsupported_date_mapping",
  bookings: [
    { booking_id: "35000000-0000-4000-8000-000000000001", venue_id: "35000000-0000-4000-8000-000000000101", start_date: "2026-11-20", end_date: "2026-11-20", start_minute: 600, end_minute: 720, status: "pending" as const },
    { booking_id: "35000000-0000-4000-8000-000000000002", venue_id: "35000000-0000-4000-8000-000000000102", start_date: "2026-11-21", end_date: "2026-11-21", start_minute: 900, end_minute: 1080, status: "approved" as const },
  ],
};

// AC3-X26 (cross-cutting): the actual pending panel edits the whole current booking batch, preserves choices after a conflict and refreshes only after a successful exact proposal decision.
test("reviews complete manual booking ranges with loading, conflict recovery and exact approval", async () => {
  let finish!: (value: { message: string }) => void;
  vi.mocked(loadEventChangeBookingPlan).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  render(<ChangeRequestPanel requests={[pending]} eventStatus="Planning" />);
  const load = screen.getByRole("button", { name: "Review booking plan" }) as HTMLButtonElement;
  expect(loadEventChangeBookingPlan).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Approve change" })).toBeNull();
  fireEvent.click(load);
  await waitFor(() => expect(loadEventChangeBookingPlan).toHaveBeenCalledTimes(1));
  expect(vi.mocked(loadEventChangeBookingPlan).mock.calls[0].slice(0, 2)).toEqual([pending.event_request_id, pending.id]);
  expect(load.disabled).toBe(true);
  await act(async () => finish({ message: "Booking plan unavailable. Try again." }));
  expect(screen.getByRole("alert").textContent).toContain("Booking plan unavailable");
  expect(refresh).not.toHaveBeenCalled();
  vi.mocked(loadEventChangeBookingPlan).mockResolvedValueOnce({ plan: context });
  fireEvent.click(screen.getByRole("button", { name: "Review booking plan" }));
  const region = await screen.findByRole("region", { name: "Booking plan" });
  expect(region.textContent).toContain(context.bookings[0].venue_id);
  expect(region.textContent).toContain(context.bookings[1].venue_id);
  const expected = [
    { booking_id: context.bookings[0].booking_id, start_date: "2026-11-22", end_date: "2026-11-22", start_minute: 660, end_minute: 750 },
    { booking_id: context.bookings[1].booking_id, start_date: "2026-11-24", end_date: "2026-11-24", start_minute: 1320, end_minute: 1440 },
  ];
  for (const row of expected) {
    const group = within(region).getByRole("group", { name: new RegExp(row.booking_id) });
    fireEvent.change(within(group).getByLabelText(/Start date/i), { target: { value: row.start_date } });
    fireEvent.change(within(group).getByLabelText(/End date/i), { target: { value: row.end_date } });
    fireEvent.change(within(group).getByLabelText(/Start time/i), { target: { value: String(row.start_minute) } });
    fireEvent.change(within(group).getByLabelText(/End time/i), { target: { value: String(row.end_minute) } });
  }
  expect(within(region).getAllByRole("option", { name: "24:00" }).length).toBeGreaterThan(0);
  vi.mocked(decideEventChangeRequest).mockResolvedValueOnce({ message: "Booking conflict. Review the selected ranges.", bookingConflicts: [{ booking_id: expected[0].booking_id, refusal_codes: ["active_block"], conflicting_booking_ids: [], conflicting_block_ids: ["35000000-0000-4000-8000-000000000999"] }] });
  fireEvent.click(screen.getByRole("button", { name: "Approve change" }));
  await waitFor(() => expect(decideEventChangeRequest).toHaveBeenCalledTimes(1));
  expect(screen.getByRole("alert").textContent).toContain(expected[0].booking_id);
  expect(refresh).not.toHaveBeenCalled();
  const args = vi.mocked(decideEventChangeRequest).mock.calls[0];
  expect(args.slice(0, 3)).toEqual([pending.event_request_id, pending.id, "Approved"]);
  expect(JSON.parse((args[4] as FormData).get("booking_plan") as string)).toEqual(expected);
  for (const row of expected) {
    const group = within(region).getByRole("group", { name: new RegExp(row.booking_id) });
    expect((within(group).getByLabelText(/Start date/i) as HTMLInputElement).value).toBe(row.start_date);
    expect((within(group).getByLabelText(/End time/i) as HTMLSelectElement).value).toBe(String(row.end_minute));
  }
  await waitFor(() => expect((screen.getByRole("button", { name: "Approve change" }) as HTMLButtonElement).disabled).toBe(false));
  vi.mocked(decideEventChangeRequest).mockResolvedValueOnce({});
  fireEvent.click(screen.getByRole("button", { name: "Approve change" }));
  await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
  expect(JSON.parse(vi.mocked(decideEventChangeRequest).mock.calls[1][4].get("booking_plan") as string)).toEqual(expected);
  expect(loadEventChangeBookingPlan).toHaveBeenCalledTimes(2);
});
