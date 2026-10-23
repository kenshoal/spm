import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { RegistrationInfoPanel } from "@/app/components/registration-info";
import { getRegistrationInfo } from "@/lib/registration-info";

vi.mock("@/lib/registration-info", () => ({ getRegistrationInfo: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

const eventId = "34000000-0000-4000-8000-000000000001";
const attendeeA = "34000000-0000-4000-8000-0000000000a1";
const attendeeB = "34000000-0000-4000-8000-0000000000b2";

// AC3-X2 (cross-cutting): the panel shows the counts and each registration's attendee, status and date
test("panel shows counts and every registration", async () => {
  vi.mocked(getRegistrationInfo).mockResolvedValueOnce({
    event_request_id: eventId, registration_capacity: 10, registered: 1, withdrawn: 1, places_available: 9,
    registrations: [
      { id: "r1", attendee_id: attendeeA, status: "Registered", created_at: "2026-10-20T09:00:00Z" },
      { id: "r2", attendee_id: attendeeB, status: "Withdrawn", created_at: "2026-10-21T09:00:00Z" },
    ],
  });
  render(await RegistrationInfoPanel({ eventRequestId: eventId }));
  const panel = screen.getByRole("region", { name: "Registrations" });
  const counts = within(panel).getAllByRole("definition").map((node) => node.textContent);
  expect(counts).toEqual(["1", "1", "9"]);
  const rows = within(panel).getAllByRole("row").slice(1).map((row) => row.textContent);
  expect(rows[0]).toContain(attendeeA);
  expect(rows[0]).toContain("Registered");
  expect(rows[1]).toContain(attendeeB);
  expect(rows[1]).toContain("Withdrawn");
  expect(Array.from(panel.querySelectorAll("time")).map((node) => node.getAttribute("datetime")))
    .toEqual(["2026-10-20T09:00:00Z", "2026-10-21T09:00:00Z"]);
  expect(getRegistrationInfo).toHaveBeenCalledExactlyOnceWith(eventId);
});

// AC3-H2 (happy): an event with no registrations and no capacity is an honest empty result
test("empty event shows zero counts, unset capacity and an empty message", async () => {
  vi.mocked(getRegistrationInfo).mockResolvedValueOnce({
    event_request_id: eventId, registration_capacity: null, registered: 0, withdrawn: 0, places_available: null, registrations: [],
  });
  render(await RegistrationInfoPanel({ eventRequestId: eventId }));
  const panel = screen.getByRole("region", { name: "Registrations" });
  expect(within(panel).getAllByRole("definition").map((node) => node.textContent)).toEqual(["0", "0", "Not set"]);
  expect(within(panel).getByText("No one has registered yet.")).toBeDefined();
  expect(within(panel).queryByRole("table")).toBeNull();
  expect(within(panel).queryByRole("alert")).toBeNull();
});

// AC4-N4 (negative): a failed lookup is reported, never shown as an empty event
test("failed lookup shows an alert instead of empty counts", async () => {
  vi.mocked(getRegistrationInfo).mockRejectedValueOnce(new Error("private storage failure"));
  render(await RegistrationInfoPanel({ eventRequestId: eventId }));
  expect(screen.getByRole("alert").textContent).toMatch(/temporarily unavailable/i);
  expect(screen.queryByText("No one has registered yet.")).toBeNull();
  expect(screen.queryByText(/private storage failure/)).toBeNull();
});
