import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("@/lib/auth", () => ({
  requireAccessToken: async () => "valid-token",
  requireAnyRole: async () => ({ id: "coord-1", email: "c@example.com", role: "event_coordinator", roles: ["event_coordinator"] }),
}));

import { checkVenueSuitability } from "@/app/venues/search/actions";
import { SuitabilityVerdict } from "@/app/venues/search/suitability-check";
import { VenueResults } from "@/app/venues/search/venue-results";
import { buildSuitabilityRequest, type SuitabilityResult } from "@/lib/venue-suitability";
import type { Venue } from "@/lib/venues";

afterEach(cleanup);
beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
});

function form(fields: Record<string, string | undefined>): FormData {
  const data = new FormData();
  for (const [name, value] of Object.entries(fields)) if (value !== undefined) data.set(name, value);
  return data;
}

function respond(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const notSuitable: SuitabilityResult = {
  venue_id: "v1",
  suitable: false,
  mismatches: [
    { attribute: "capacity", reason: "Expected attendance 500 exceeds the venue's maximum capacity of 120." },
    { attribute: "facilities", reason: "Missing required facility: Stage." },
  ],
};

// AC1-N3 to AC1-N6 (negative): a non-positive or non-whole attendance is
// reported and no request is built.
test.each([
  ["AC1-N3", "0"],
  ["AC1-N4", "abc"],
  ["AC1-N5", "2.5"],
  ["AC1-N6", "-1"],
])("%s rejects attendance %j", (_id, value) => {
  expect(buildSuitabilityRequest({ expected_attendance: value })).toEqual({
    payload: null,
    errors: { expected_attendance: "Enter a whole number greater than zero." },
  });
});

// AC1-N3 (negative): the action reports the error and sends nothing.
test("an invalid attendance sends no request", async () => {
  const fetchMock = respond(200, notSuitable);

  const state = await checkVenueSuitability("v1", {}, form({ expected_attendance: "0" }));

  expect(state.errors).toEqual({ expected_attendance: "Enter a whole number greater than zero." });
  expect(state.result).toBeUndefined();
  expect(fetchMock).not.toHaveBeenCalled();
});

// AC3-H2 (happy): only the filled-in requirements are sent, lists split on commas.
test("sends the filled-in requirements to the suitability endpoint", async () => {
  const fetchMock = respond(200, notSuitable);

  await checkVenueSuitability("v1", {}, form({
    expected_attendance: " 100 ",
    required_layout: "theatre",
    required_slot: "PM",
    required_facilities: "Projector, Stage",
    required_accessibility: "Ramp access",
  }));

  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0];
  expect(String(url)).toMatch(/\/venues\/v1\/suitability$/);
  expect(init.method).toBe("POST");
  expect(JSON.parse(init.body)).toEqual({
    expected_attendance: 100,
    required_layout: "theatre",
    required_slot: "PM",
    required_facilities: ["Projector", "Stage"],
    required_accessibility: ["Ramp access"],
  });
});

// AC3-H2 (happy): requirements left blank are omitted, not sent as empty values.
test("omits requirements that were left blank", async () => {
  const fetchMock = respond(200, { venue_id: "v1", suitable: true, mismatches: [] });

  await checkVenueSuitability("v1", {}, form({ expected_attendance: "10", required_layout: "", required_facilities: "" }));

  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ expected_attendance: 10 });
});

// AC3-P12 (partition): values outside the backend enums are dropped, not sent.
test("drops a layout and a slot outside the enums", async () => {
  const fetchMock = respond(200, { venue_id: "v1", suitable: true, mismatches: [] });

  await checkVenueSuitability("v1", {}, form({ expected_attendance: "10", required_layout: "ballroom", required_slot: "MIDNIGHT" }));

  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ expected_attendance: 10 });
});

// AC4-H4 (happy): the action returns the service's verdict unchanged.
test("returns the result from the service", async () => {
  respond(200, notSuitable);

  const state = await checkVenueSuitability("v1", {}, form({ expected_attendance: "500" }));

  expect(state.result).toEqual(notSuitable);
  expect(state.message).toBeUndefined();
});

// AC3-N4 (negative): an unknown venue is reported and no verdict is shown.
test("reports a venue that no longer exists", async () => {
  respond(404, { detail: "Venue not found" });

  const state = await checkVenueSuitability("v1", {}, form({ expected_attendance: "10" }));

  expect(state.message).toBe("This venue no longer exists.");
  expect(state.result).toBeUndefined();
});

// AC3-N5 (negative): an expired session goes to sign-in.
test("redirects to sign-in when the session has expired", async () => {
  respond(401, { detail: "Authentication required" });
  navigation.redirect.mockImplementation(() => { throw new Error("NEXT_REDIRECT"); });

  await expect(checkVenueSuitability("v1", {}, form({ expected_attendance: "10" }))).rejects.toThrow("NEXT_REDIRECT");

  expect(navigation.redirect).toHaveBeenCalledWith("/auth");
});

// AC3-N6 (negative): a failure is never shown as a verdict.
test.each([
  ["a 500 response", () => respond(500, { detail: "boom" })],
  ["a network error", () => vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")))],
])("reports %s as could not be checked", async (_name, arrange) => {
  arrange();

  const state = await checkVenueSuitability("v1", {}, form({ expected_attendance: "10" }));

  expect(state.message).toBe("The suitability check could not be completed. Please try again.");
  expect(state.result).toBeUndefined();
});

// AC5-X2 (cross-cutting): the check makes one POST to the suitability path and nothing else.
test("makes no call other than the suitability POST", async () => {
  const fetchMock = respond(200, notSuitable);

  await checkVenueSuitability("v1", {}, form({ expected_attendance: "500" }));

  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][1].method).toBe("POST");
  expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/venues\/v1\/suitability$/);
});

// AC4-H4 (happy): the verdict is written in words, with one line per mismatch.
test("shows Not suitable with each mismatch's attribute and reason", () => {
  render(<SuitabilityVerdict result={notSuitable} />);

  expect(screen.getByRole("status").textContent).toContain("Not suitable");
  const items = screen.getAllByRole("listitem");
  expect(items).toHaveLength(2);
  expect(within(items[0]).getByText("Capacity")).toBeDefined();
  expect(within(items[0]).getByText(/500 exceeds the venue's maximum capacity of 120/)).toBeDefined();
  expect(within(items[1]).getByText("Facilities")).toBeDefined();
  expect(within(items[1]).getByText(/Missing required facility: Stage/)).toBeDefined();
});

// AC4-H5 (happy): a suitable venue shows the verdict and no list.
test("shows Suitable with no mismatch list", () => {
  render(<SuitabilityVerdict result={{ venue_id: "v1", suitable: true, mismatches: [] }} />);

  expect(screen.getByRole("status").textContent).toContain("Suitable");
  expect(screen.getByRole("status").textContent).not.toContain("Not suitable");
  expect(screen.queryAllByRole("listitem")).toHaveLength(0);
});

const venue: Venue = {
  id: "v1", name: "Riverside Hall", location: "East Wing", max_capacity: 120,
  facilities: ["Projector"], accessibility_features: [], supported_layouts: ["theatre"],
  operating_slots: ["AM", "PM"], status: "available", created_at: "2026-09-13T03:00:00Z", updated_at: "2026-09-13T03:00:00Z",
};

// AC3-H3 (happy): the check form starts from what the coordinator searched for.
test("pre-fills each result's check form from the search filters", () => {
  render(
    <VenueResults
      venues={[venue]}
      requirements={{ expected_attendance: "80", required_layout: "theatre", required_slot: "PM", required_facilities: "Projector", required_accessibility: "" }}
    />,
  );

  const card = screen.getByRole("article", { name: "Riverside Hall" });
  expect((within(card).getByLabelText("Expected attendance") as HTMLInputElement).value).toBe("80");
  expect((within(card).getByLabelText("Required layout") as HTMLSelectElement).value).toBe("theatre");
  expect((within(card).getByLabelText("Required slot") as HTMLSelectElement).value).toBe("PM");
  expect((within(card).getByLabelText("Required facilities") as HTMLInputElement).value).toBe("Projector");
  expect(within(card).getByRole("button", { name: "Check this venue" })).toBeDefined();
});
