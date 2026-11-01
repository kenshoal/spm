import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
const auth = vi.hoisted(() => ({ requireRole: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "token", requireRole: auth.requireRole }));

import {
  offerWaitlistPlace,
  recordEquipmentRequirement,
  saveEventDetails,
  saveRegistrationSettings,
} from "@/app/coordination/requests/[id]/event-setup-actions";
import { requestVenueBooking } from "@/app/coordination/requests/[id]/venue-booking-actions";
import {
  acceptWaitlistOffer,
  joinWaitlist,
  registerForEvent,
  withdrawFromWaitlist,
  withdrawRegistration,
} from "@/app/events/actions";
import {
  checkAvailability,
  releaseReservation,
  reserveEquipment,
  updateArrangement,
} from "@/app/equipment/requests/actions";

const EVENT = "11111111-1111-4111-8111-111111111111";

function form(fields: Record<string, string | string[]>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    for (const item of Array.isArray(value) ? value : [value]) data.append(key, item);
  }
  return data;
}

function respond(status: number, body: unknown = {}) {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const sent = (fetchMock: ReturnType<typeof vi.fn>) => ({
  url: fetchMock.mock.calls[0][0] as string,
  init: fetchMock.mock.calls[0][1] as { method: string; body?: string },
  body: fetchMock.mock.calls[0][1]?.body ? JSON.parse(fetchMock.mock.calls[0][1].body) : null,
});

beforeEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  navigation.redirect.mockReset();
  navigation.revalidatePath.mockReset();
  auth.requireRole.mockReset().mockResolvedValue({ id: "user-1", roles: [] });
});

// AC4-H2 (happy, hotfix 4): registration settings go out as Singapore-time instants
test("saves the registration period and capacity in Singapore time", async () => {
  const fetchMock = respond(200);

  const state = await saveRegistrationSettings(EVENT, {}, form({
    registration_opens_at: "2026-12-01T09:00",
    registration_closes_at: "2026-12-05T18:30",
    registration_capacity: "120",
  }));

  expect(state).toEqual({ saved: true });
  const { url, init, body } = sent(fetchMock);
  expect(url).toBe(`http://127.0.0.1:8003/event-requests/${EVENT}/registration-settings`);
  expect(init.method).toBe("PUT");
  expect(body).toEqual({
    registration_opens_at: "2026-12-01T09:00:00+08:00",
    registration_closes_at: "2026-12-05T18:30:00+08:00",
    registration_capacity: 120,
  });
});

// AC4-N6, AC4-N7, AC4-N8 (negative, hotfix 4): bad input never reaches the API
test.each([
  ["no dates", { registration_capacity: "5" }, "Choose when registration opens and closes."],
  [
    "closing before opening",
    { registration_opens_at: "2026-12-05T09:00", registration_closes_at: "2026-12-05T09:00", registration_capacity: "5" },
    "Registration must close after it opens.",
  ],
  [
    "capacity zero",
    { registration_opens_at: "2026-12-01T09:00", registration_closes_at: "2026-12-05T09:00", registration_capacity: "0" },
    "Enter a capacity of at least 1.",
  ],
])("refuses registration settings with %s", async (_name, fields, message) => {
  const fetchMock = respond(200);

  expect(await saveRegistrationSettings(EVENT, {}, form(fields))).toEqual({ message });
  expect(fetchMock).not.toHaveBeenCalled();
});

// AC4-N9 (negative, hotfix 4): the API's own refusal is worded for the coordinator
test("explains a capacity below the places taken", async () => {
  respond(409, { code: "capacity_below_taken" });

  const state = await saveRegistrationSettings(EVENT, {}, form({
    registration_opens_at: "2026-12-01T09:00",
    registration_closes_at: "2026-12-05T09:00",
    registration_capacity: "1",
  }));

  expect(state.message).toBe("Capacity cannot be lower than the places already taken.");
});

// AC8-H4 (happy, hotfix 8): only the fields that changed are sent, with the version seen
test("sends only the changed details with the version the page loaded", async () => {
  const fetchMock = respond(200);

  const state = await saveEventDetails(EVENT, {}, form({
    expected_updated_at: "2026-11-01T00:00:00Z",
    purpose: "New purpose",
    original_purpose: "Old purpose",
    description: "Same",
    original_description: "Same",
    expected_attendance: "150",
    original_expected_attendance: "100",
  }));

  expect(state).toEqual({ saved: true });
  const { url, init, body } = sent(fetchMock);
  expect(url).toBe(`http://127.0.0.1:8003/event-requests/${EVENT}/details`);
  expect(init.method).toBe("PATCH");
  expect(body).toEqual({
    expected_updated_at: "2026-11-01T00:00:00Z",
    purpose: "New purpose",
    expected_attendance: 150,
  });
});

// AC8-N4, AC8-N5, AC8-N6 (negative, hotfix 8): nothing changed, blanking a field, or a stale page
test.each([
  ["nothing changed", { expected_updated_at: "x", purpose: "A", original_purpose: "A" }, "Nothing has changed."],
  ["a blanked field", { expected_updated_at: "x", purpose: " ", original_purpose: "A" }, "Details cannot be left blank."],
  ["attendance zero", { expected_updated_at: "x", expected_attendance: "0", original_expected_attendance: "5" }, "Enter an expected attendance of at least 1."],
])("refuses an edit with %s", async (_name, fields, message) => {
  const fetchMock = respond(200);

  expect(await saveEventDetails(EVENT, {}, form(fields))).toEqual({ message });
  expect(fetchMock).not.toHaveBeenCalled();
});

// AC8-N7 (negative, hotfix 8): a stale edit is refused with advice, not a generic error
test("tells the coordinator to refresh after a stale edit", async () => {
  respond(409, { code: "event_details_conflict" });

  const state = await saveEventDetails(EVENT, {}, form({
    expected_updated_at: "x", purpose: "B", original_purpose: "A",
  }));

  expect(state.message).toBe("This event changed since you opened it. Refresh and try again.");
});

// AC8-B1 (boundary, hotfix 8): dates convert to Singapore instants and at least one must stay
test("converts edited dates and keeps at least one", async () => {
  const fetchMock = respond(200);

  await saveEventDetails(EVENT, {}, form({
    expected_updated_at: "x",
    proposed_date_times: ["2026-12-09T10:00"],
    original_proposed_date_times: ["2026-12-08T10:00"],
  }));
  expect(sent(fetchMock).body.proposed_date_times).toEqual(["2026-12-09T10:00:00+08:00"]);

  expect(await saveEventDetails(EVENT, {}, form({
    expected_updated_at: "x", original_proposed_date_times: ["2026-12-08T10:00"],
  }))).toEqual({ message: "Keep at least one date and time." });
});

// AC6-H2 (happy, hotfix 6): a venue request carries the event, dates and minutes
test("requests a venue for the event and passes back a clash warning", async () => {
  const clash = { start_date: "2026-12-10", end_date: "2026-12-10", start_minute: 600, end_minute: 720 };
  const fetchMock = respond(201, { id: "b1", conflicts: [clash] });

  const state = await requestVenueBooking(EVENT, {}, form({
    venue_id: "v1", start_date: "2026-12-10", start_time: "10:00", end_time: "12:00",
  }));

  expect(state).toEqual({ submitted: true, conflicts: [clash] });
  expect(sent(fetchMock).body).toEqual({
    venue_id: "v1",
    event_request_id: EVENT,
    start_date: "2026-12-10",
    end_date: "2026-12-10",
    start_minute: 600,
    end_minute: 720,
  });
});

// AC6-N2, AC6-N3 (negative, hotfix 6): an incomplete or reversed request is not sent
test.each([
  ["no venue", { start_date: "2026-12-10", start_time: "10:00", end_time: "12:00" }, "Choose a venue and a date."],
  ["end before start", { venue_id: "v1", start_date: "2026-12-10", start_time: "12:00", end_time: "10:00" }, "Choose a start time and a later end time."],
])("does not send a venue request with %s", async (_name, fields, message) => {
  const fetchMock = respond(201);

  expect(await requestVenueBooking(EVENT, {}, form(fields))).toEqual({ message });
  expect(fetchMock).not.toHaveBeenCalled();
});

// AC6-N4 (negative, hotfix 6): a refusal by the API is explained
test("explains a venue request the API refuses", async () => {
  respond(404);

  const state = await requestVenueBooking(EVENT, {}, form({
    venue_id: "v1", start_date: "2026-12-10", start_time: "10:00", end_time: "12:00",
  }));

  expect(state.message).toContain("no longer assigned to you");
});

// AC7-H3 (happy, hotfix 7): the requirement goes to equipmentService with the event
test("records an equipment requirement for the event", async () => {
  const fetchMock = respond(201, { id: "r1" });

  const state = await recordEquipmentRequirement(EVENT, {}, form({
    equipment_type: "  Projector ", quantity: "3", technical_requirements: "HDMI",
  }));

  expect(state).toEqual({ saved: true });
  expect(sent(fetchMock).url).toBe("http://127.0.0.1:8002/equipment-requirements");
  expect(sent(fetchMock).body).toEqual({
    event_request_id: EVENT, equipment_type: "Projector", quantity: 3, technical_requirements: "HDMI",
  });
});

// AC7-N1 (negative, hotfix 7): a missing type or a zero quantity is not sent
test.each([
  [{ quantity: "2" }, "Enter the equipment type."],
  [{ equipment_type: "Mic", quantity: "0" }, "Enter a quantity of at least 1."],
])("does not record equipment %j", async (fields, message) => {
  const fetchMock = respond(201);

  expect(await recordEquipmentRequirement(EVENT, {}, form(fields))).toEqual({ message });
  expect(fetchMock).not.toHaveBeenCalled();
});

// AC3-H5 (happy, hotfix 7): the coordinator's override targets the chosen queue entry
test("offers the open place to the chosen waiting entry", async () => {
  const fetchMock = respond(200);

  expect(await offerWaitlistPlace(EVENT, "entry-1")).toEqual({ saved: true });
  expect(sent(fetchMock).url).toBe(`http://127.0.0.1:8003/event-requests/${EVENT}/waitlist/entry-1/offer`);
  expect(sent(fetchMock).init.method).toBe("POST");
});

// AC5-H2 (happy, hotfix 5): each attendee action posts to its own endpoint
test.each([
  [() => registerForEvent("e1"), "/attendee/events/e1/registrations"],
  [() => joinWaitlist("e1"), "/attendee/events/e1/waitlist"],
  [() => withdrawRegistration("r1"), "/attendee/registrations/r1/withdrawal"],
  [() => acceptWaitlistOffer("w1"), "/attendee/waitlist/w1/acceptance"],
  [() => withdrawFromWaitlist("w1"), "/attendee/waitlist/w1/withdrawal"],
])("attendee action %#", async (run, path) => {
  const fetchMock = respond(201);

  expect(await run()).toEqual({ done: true });
  expect(sent(fetchMock).url).toBe(`http://127.0.0.1:8003${path}`);
  expect(sent(fetchMock).init.method).toBe("POST");
});

// AC5-N2 (negative, hotfix 5): a coded refusal reads as a sentence the attendee can act on
test.each([
  ["event_full", "This event is full. You can join the waiting list."],
  ["registration_not_open", "Registration is not open for this event."],
  ["offer_expired", "This offer has expired. The place went to the next person."],
])("attendee refusal %s", async (code, message) => {
  respond(409, { code });

  expect(await registerForEvent("e1")).toEqual({ message });
});

// AC5-N3 (negative, hotfix 5): an unknown failure is a retry message, not a raw code
test("an unknown attendee failure asks to retry", async () => {
  respond(500, { code: "nope" });

  expect(await registerForEvent("e1")).toEqual({ message: "That could not be done. Please try again." });
});

// AC5-N4 (negative, hotfix 5): a lapsed session sends the attendee to sign in again
test("a 401 sends the attendee to sign in", async () => {
  respond(401);

  await registerForEvent("e1");

  expect(navigation.redirect).toHaveBeenCalledWith("/auth");
});

// AC7-H4 (happy, hotfix 7): an availability check sends the type, dates and venue
test("checks equipment availability and words the result", async () => {
  const fetchMock = respond(200, { Projector: { requested: 5, available: 3, shortfall: 2 } });

  const state = await checkAvailability("r1", "Projector", {}, form({
    venue_id: "v1", start_date: "2026-12-10", end_date: "2026-12-11", quantity: "5",
  }));

  expect(sent(fetchMock).body).toEqual({
    start_date: "2026-12-10",
    end_date: "2026-12-11",
    venue_id: "v1",
    items: [{ type: "Projector", quantity: 5 }],
  });
  expect(state.lines).toEqual(["Projector: 3 available, 2 short of 5."]);
});

// AC7-H5 (happy, hotfix 7): a reservation names the requirement, equipment, days and venue
test("reserves equipment against the requirement", async () => {
  const fetchMock = respond(201, { id: "res1" });

  const state = await reserveEquipment("r1", {}, form({
    equipment_id: "e1", venue_id: "v1", start_date: "2026-12-10", quantity: "2",
  }));

  expect(state).toEqual({ done: true });
  expect(sent(fetchMock).body).toEqual({
    requirement_id: "r1", equipment_id: "e1", quantity: 2, start_date: "2026-12-10", end_date: "2026-12-10", venue_id: "v1",
  });
});

// AC7-N2 (negative, hotfix 7): too much for the days is explained, and nothing is claimed
test("explains a reservation that exceeds what is free", async () => {
  respond(409);

  const state = await reserveEquipment("r1", {}, form({
    equipment_id: "e1", venue_id: "v1", start_date: "2026-12-10", quantity: "9",
  }));

  expect(state.message).toContain("not available");
  expect(state.done).toBeUndefined();
});

// AC11-H2 (happy, hotfix 11): releasing a reservation sends the reason
test("releases a reservation with its reason", async () => {
  const fetchMock = respond(200);

  expect(await releaseReservation("res1", {}, form({ reason: "Broken" }))).toEqual({ done: true });
  expect(sent(fetchMock).url).toBe("http://127.0.0.1:8002/equipment-reservations/res1/release");
  expect(sent(fetchMock).body).toEqual({ reason: "Broken" });
});

// AC11-N4 (negative, hotfix 11): releasing without a reason is not sent
test("does not release a reservation without a reason", async () => {
  const fetchMock = respond(200);

  expect(await releaseReservation("res1", {}, form({ reason: "  " }))).toEqual({ message: "Say why it is being released." });
  expect(fetchMock).not.toHaveBeenCalled();
});

// AC7-H6 (happy, hotfix 7): the arrangement update states the status the page saw
test("updates the arrangement from the status the page saw", async () => {
  const fetchMock = respond(200);

  await updateArrangement("r1", "requested", {}, form({ status: "in_progress", support_note: "Sourcing" }));

  expect(sent(fetchMock).init.method).toBe("PATCH");
  expect(sent(fetchMock).body).toEqual({ expected_status: "requested", status: "in_progress", support_note: "Sourcing" });
});

// AC7-N3 (negative, hotfix 7): a concurrent change is explained, not hidden
test("explains an arrangement changed by someone else", async () => {
  respond(409);

  const state = await updateArrangement("r1", "requested", {}, form({ status: "arranged" }));

  expect(state.message).toBe("Someone else changed this requirement. Refresh and try again.");
});
