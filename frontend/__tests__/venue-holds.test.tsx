import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
const auth = vi.hoisted(() => ({ requireRole: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "valid-token", requireRole: auth.requireRole }));

import { placeVenueHold, releaseVenueHold } from "@/app/coordination/requests/[id]/venue-hold-actions";
import { VenueHoldsList } from "@/app/coordination/requests/[id]/venue-holds-panel";
import { AvailabilityCalendarTable } from "@/app/venues/availability/availability-calendar";
import { VenueResults } from "@/app/venues/search/venue-results";
import { refusalMessages } from "@/lib/booking-decision-form";
import { describeNotification } from "@/lib/notifications";
import { parsePlaceHoldForm, type VenueHold } from "@/lib/venue-hold-form";
import type { VenueSearchResult } from "@/lib/venues";

// SCRUM-18: tentative venue holds on the coordinator's event page, the
// availability calendar and notifications. Case IDs match scrum_18_testcases.md.

const NOW = new Date("2026-11-01T02:00:00Z"); // 10:00 in Singapore

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

function respond(status: number, body?: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

const validFields = {
  venue_id: "v1",
  start_date: "2026-11-10",
  end_date: "2026-11-10",
  start_time: "10:00",
  end_time: "12:00",
  expires_at: "2026-11-03T18:00",
};

function hold(overrides: Partial<VenueHold> = {}): VenueHold {
  return {
    id: "h1", venue_id: "v1", event_request_id: "e1", start_date: "2026-11-10", end_date: "2026-11-10",
    start_minute: 600, end_minute: 720, expires_at: "2026-11-03T10:00:00Z", status: "active",
    booking_request_id: null, placed_by: "c1", placed_at: "2026-11-01T01:00:00Z", closed_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
  navigation.revalidatePath.mockReset();
  auth.requireRole.mockReset();
  auth.requireRole.mockResolvedValue({ id: "c1", email: "c@example.com", role: "event_coordinator", roles: ["event_coordinator"] });
});
afterEach(cleanup);

// AC1-H2 (happy): the form sends the times in minutes and the expiry as Singapore time
test("parses a hold with a Singapore expiry", () => {
  expect(parsePlaceHoldForm(form(validFields), "e1", NOW)).toEqual({
    venueId: "v1",
    payload: {
      event_request_id: "e1", start_date: "2026-11-10", end_date: "2026-11-10",
      start_minute: 600, end_minute: 720, expires_at: "2026-11-03T18:00:00+08:00",
    },
    errors: {},
  });
});

// AC1-B2 (boundary): the expiry must be in the future and at most 7 days ahead; a venue is required
test.each([
  [{ expires_at: "2026-11-01T09:45" }, "expires_at", "The hold must expire in the future."],
  [{ expires_at: "2026-11-08T10:15" }, "expires_at", "A hold can last at most 7 days."],
  [{ venue_id: "" }, "venue_id", "Choose a venue."],
  [{ end_date: "2026-11-09" }, "end_date", "The end date must be on or after the start date."],
])("refuses invalid hold fields %#", (change, field, message) => {
  expect(parsePlaceHoldForm(form({ ...validFields, ...change }), "e1", NOW).errors[field]).toBe(message);
});

// AC2-H5 (happy): a clash is explained with the booking refusal wording, including holds
test("explains a hold clash", async () => {
  vi.useFakeTimers({ now: NOW, toFake: ["Date"] });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(409, { detail: { refusal_codes: ["hold_conflict"] } })));
  const state = await placeVenueHold("e1", {}, form(validFields));
  vi.useRealTimers();
  expect(state.message).toBe(
    "The venue could not be held. A tentative hold, including the venue's setup and turnaround time, already covers part of this period.",
  );
  expect(refusalMessages(["hold_conflict"])).toHaveLength(1);
});

// AC1-H3 (happy): a placed hold posts once to the venue and refreshes the event page
test("places a hold and refreshes the event", async () => {
  vi.useFakeTimers({ now: NOW, toFake: ["Date"] });
  const fetchMock = vi.fn().mockResolvedValue(respond(201, hold()));
  vi.stubGlobal("fetch", fetchMock);
  expect(await placeVenueHold("e1", {}, form(validFields))).toEqual({});
  vi.useRealTimers();
  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8004/venues/v1/holds");
  expect(navigation.revalidatePath).toHaveBeenCalledWith("/coordination/requests/e1");
});

// AC5-N2 (negative): a hold that ended is explained, not silently ignored
test("explains a release of an ended hold", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(409)));
  const state = await releaseVenueHold({}, form({ hold_id: "h1", event_request_id: "e1" }));
  expect(state.message).toBe("This hold has ended or expired, or its booking request is still pending.");
});

// AC5-H4 (happy): an active hold offers Request booking and Release; a requested one only Release
test("lists holds with their actions", () => {
  render(
    <VenueHoldsList
      holds={[hold(), hold({ id: "h2", booking_request_id: "b1" })]}
      venueNames={new Map([["v1", "Riverside Hall"]])}
      eventRequestId="e1"
      now={NOW}
    />,
  );
  expect(screen.getAllByRole("button", { name: "Request booking for hold at Riverside Hall" })).toHaveLength(1);
  expect(screen.getAllByRole("button", { name: "Release hold at Riverside Hall" })).toHaveLength(2);
  expect(screen.getByText(/Booking requested; held until Venue Staff decide or/)).toBeTruthy();
});

// AC3-B2 (boundary): a hold past its expiry shows as Expired with no actions, before the sweep runs
test("shows a hold past its expiry as expired", () => {
  render(
    <VenueHoldsList
      holds={[hold({ expires_at: "2026-11-01T02:00:00Z" })]}
      venueNames={new Map([["v1", "Riverside Hall"]])}
      eventRequestId="e1"
      now={NOW}
    />,
  );
  expect(screen.getByText("Expired")).toBeTruthy();
  expect(screen.queryByRole("button")).toBeNull();
});

// AC6-H3 (happy): the calendar writes out a tentative hold, distinct from a booking
test("shows a tentatively held time on the calendar", () => {
  render(
    <AvailabilityCalendarTable
      calendar={{
        venue_id: "v1",
        month: "2026-11",
        days: [{
          date: "2026-11-10", unavailable: false,
          entries: [{ state: "booked", start_minute: 570, end_minute: 765 }, { state: "held", start_minute: 765, end_minute: 885 }],
          free: [{ start_minute: 420, end_minute: 570 }, { start_minute: 885, end_minute: 1440 }],
        }],
      }}
      venueId="v1"
      venueName="Riverside Hall"
    />,
  );
  expect(screen.getByText("Tentatively held 12:45–14:45")).toBeTruthy();
  expect(screen.getByText("Booked 09:30–12:45")).toBeTruthy();
});

// AC6-H4 (happy): search marks a venue that is free except for a hold as tentatively held
test("marks a tentatively held venue in search results", () => {
  const base: VenueSearchResult = {
    id: "v1", name: "Riverside Hall", location: "East Wing", max_capacity: 120,
    facilities: [], accessibility_features: [], supported_layouts: ["theatre"],
    operating_slots: ["AM", "PM"], setup_minutes: 30, turnaround_minutes: 45, operating_start_minute: 420, operating_end_minute: 1440,
    status: "available", created_at: "2026-09-13T03:00:00Z", updated_at: "2026-09-13T03:00:00Z",
  };
  render(
    <VenueResults venues={[
      { ...base, tentatively_held: true },
      { ...base, id: "v2", name: "Lakeside Room", tentatively_held: false },
    ]} />,
  );
  expect(within(screen.getByRole("article", { name: "Riverside Hall" })).getByText("Tentatively held")).toBeTruthy();
  expect(within(screen.getByRole("article", { name: "Lakeside Room" })).queryByText("Tentatively held")).toBeNull();
  expect(screen.getByText("2 venues match every filter.")).toBeTruthy();
});

// AC4-H3 (happy): the hold notices read plainly and link to the event
test("describes hold notices", () => {
  const payload = {
    event_request_id: "e1", event_name: "Open day", venue_name: "Riverside Hall",
    start_date: "2026-11-10", end_date: "2026-11-10", start_minute: 600, end_minute: 720,
    expires_at: "2026-11-03T10:00:00Z",
  };
  const base = { id: "n1", read_at: null, created_at: "2026-11-02T10:00:00Z" };
  const expiring = describeNotification({ ...base, event_type: "venue_hold_expiring", payload });
  expect(expiring.message).toBe("Your hold on Riverside Hall for Open day expires soon.");
  expect(expiring.href).toBe("/coordination/requests/e1");
  expect(expiring.detail).toContain("Request the booking or release the hold.");
  const expired = describeNotification({ ...base, event_type: "venue_hold_expired", payload });
  expect(expired.message).toBe("Your hold on Riverside Hall for Open day has expired and the time is free again.");
});
