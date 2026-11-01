import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
const auth = vi.hoisted(() => ({ requireRole: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect, unstable_rethrow: vi.fn() }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "token", requireRole: auth.requireRole }));

import {
  decideEventChangeRequestPartly,
  withdrawEventRequest,
} from "@/app/coordination/actions";
import {
  changeOrganiser,
  postponeEvent,
  resumeEvent,
  setRequirementEssential,
} from "@/app/coordination/requests/[id]/event-setup-actions";

const EVENT = "11111111-1111-4111-8111-111111111111";
const CHANGE = "22222222-2222-4222-8222-222222222222";
const REQUIREMENT = "33333333-3333-4333-8333-333333333333";
const FIELDS = ["expected_attendance", "venue_requirements", "equipment_requirements"];

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
  auth.requireRole.mockReset().mockResolvedValue({ id: "coord-1", roles: [] });
});

// AC20-H1 (happy, hotfix 20): the accepted fields and a reason for each refused one are posted
test("sends a partial decision with the accepted fields and each refusal's reason", async () => {
  const fetchMock = respond(200);

  const state = await decideEventChangeRequestPartly(EVENT, CHANGE, FIELDS, {}, form({
    accept: ["expected_attendance"],
    reason__venue_requirements: "No bigger room is free",
    reason__equipment_requirements: "Not available that day",
    reason: "Only the numbers can change",
  }));

  expect(state).toEqual({});
  const { url, init, body } = sent(fetchMock);
  expect(url).toBe(`http://127.0.0.1:8003/event-requests/${EVENT}/change-requests/${CHANGE}/decision`);
  expect(init.method).toBe("POST");
  expect(body).toEqual({
    decision: "Approved",
    reason: "Only the numbers can change",
    accepted_fields: ["expected_attendance"],
    rejected_reasons: {
      venue_requirements: "No bigger room is free",
      equipment_requirements: "Not available that day",
    },
  });
  expect(navigation.revalidatePath).toHaveBeenCalledWith(`/coordination/requests/${EVENT}`);
});

// AC20-N1 (negative, hotfix 20): a refused field without a reason is caught before anything is sent
test("does not send a partial decision with a missing reason", async () => {
  const fetchMock = respond(200);

  const state = await decideEventChangeRequestPartly(EVENT, CHANGE, FIELDS, {}, form({
    accept: ["expected_attendance"],
    reason__venue_requirements: "   ",
    reason__equipment_requirements: "Not available",
  }));

  expect(state.message).toMatch(/reason for every field/i);
  expect(state.fieldErrors).toEqual({ venue_requirements: "Say why this is not accepted." });
  expect(fetchMock).not.toHaveBeenCalled();
});

// AC20-N2 (negative, hotfix 20): each server refusal reads differently to the Coordinator
test.each([
  [403, /Only the coordinator currently assigned/],
  [409, /already decided/],
  [422, /every refused field has a reason/],
  [500, /could not be recorded/],
])("a %s answer to a partial decision gets its own message", async (status, message) => {
  respond(status);

  const state = await decideEventChangeRequestPartly(EVENT, CHANGE, FIELDS, {}, form({
    accept: ["expected_attendance"],
    reason__venue_requirements: "No",
    reason__equipment_requirements: "No",
  }));

  expect(state.message).toMatch(message);
});

// AC21-H1 (happy, hotfix 21): recording a withdrawal posts to the withdrawal route
test("records a withdrawal", async () => {
  const fetchMock = respond(200);

  const state = await withdrawEventRequest(EVENT, {}, new FormData());

  expect(state).toEqual({});
  expect(sent(fetchMock).url).toBe(`http://127.0.0.1:8003/event-requests/${EVENT}/withdrawal`);
  expect(sent(fetchMock).init.method).toBe("POST");
});

// AC21-N1 (negative, hotfix 21): a request past review answers 409 and says the status changed
test("a withdrawal past review is explained", async () => {
  respond(409);

  const state = await withdrawEventRequest(EVENT, {}, new FormData());

  expect(state.message).toMatch(/status has already changed/);
});

// AC22-H1 (happy, hotfix 22): a postponement sends its reason
test("postpones with a reason", async () => {
  const fetchMock = respond(200);

  const state = await postponeEvent(EVENT, {}, form({ reason: "  Venue closed that week  " }));

  expect(state).toEqual({ saved: true });
  const { url, body } = sent(fetchMock);
  expect(url).toBe(`http://127.0.0.1:8003/event-requests/${EVENT}/postponement`);
  expect(body).toEqual({ reason: "Venue closed that week" });
});

// AC22-N1 (negative, hotfix 22): no reason, nothing sent
test("does not postpone without a reason", async () => {
  const fetchMock = respond(200);

  const state = await postponeEvent(EVENT, {}, form({ reason: "   " }));

  expect(state.message).toMatch(/why the event is being postponed/i);
  expect(fetchMock).not.toHaveBeenCalled();
});

// AC22-H2 (happy, hotfix 22): the new date goes out as a Singapore-time instant
test("sets the new date of a postponed event in Singapore time", async () => {
  vi.setSystemTime(new Date("2030-01-01T00:00:00Z"));
  const fetchMock = respond(200);

  const state = await resumeEvent(EVENT, {}, form({ new_date: "2030-03-04T09:30" }));

  expect(state).toEqual({ saved: true });
  const { url, body } = sent(fetchMock);
  expect(url).toBe(`http://127.0.0.1:8003/event-requests/${EVENT}/resumption`);
  expect(body).toEqual({ proposed_date_times: ["2030-03-04T09:30:00+08:00"] });
  vi.useRealTimers();
});

// AC22-B1 (boundary, hotfix 22): a date in the past, or none, is refused before sending
test.each([
  ["a past date", "2020-01-01T09:00", /in the future/],
  ["no date", "", /Choose the new date/],
])("does not resume with %s", async (_name, value, message) => {
  const fetchMock = respond(200);

  const state = await resumeEvent(EVENT, {}, form({ new_date: value }));

  expect(state.message).toMatch(message);
  expect(fetchMock).not.toHaveBeenCalled();
});

// AC24-H1 (happy, hotfix 24): the new organiser's email and the reason are posted
test("changes the event organiser", async () => {
  const fetchMock = respond(200);

  const state = await changeOrganiser(EVENT, {}, form({
    organiser_email: " new@client.example ", reason: "Left the company",
  }));

  expect(state).toEqual({ saved: true });
  const { url, body } = sent(fetchMock);
  expect(url).toBe(`http://127.0.0.1:8003/event-requests/${EVENT}/organiser`);
  expect(body).toEqual({ organiser_email: "new@client.example", reason: "Left the company" });
});

// AC24-N1 (negative, hotfix 24): the server's own sentence is shown for a 422 or 409
test.each([422, 409])("shows the server's explanation for a %s organiser refusal", async (status) => {
  respond(status, { detail: "No Event Organiser account has that email address." });

  const state = await changeOrganiser(EVENT, {}, form({ organiser_email: "x@y.test", reason: "Left" }));

  expect(state.message).toBe("No Event Organiser account has that email address.");
});

// AC24-N2 (negative, hotfix 24): a missing email or reason is caught before sending
test.each([
  [{ organiser_email: "", reason: "Left" }, /email address/],
  [{ organiser_email: "a@b.test", reason: "" }, /why the Event Organiser/],
])("does not change the organiser with %j", async (fields, message) => {
  const fetchMock = respond(200);

  const state = await changeOrganiser(EVENT, {}, form(fields));

  expect(state.message).toMatch(message);
  expect(fetchMock).not.toHaveBeenCalled();
});

// AC25-H1 (happy, hotfix 25): not essential goes to the equipment service with its note
test("marks a requirement not essential with a note", async () => {
  const fetchMock = respond(200);

  const state = await setRequirementEssential(EVENT, REQUIREMENT, {}, form({
    essential: "false", note: "Support will bring one",
  }));

  expect(state).toEqual({ saved: true });
  const { url, init, body } = sent(fetchMock);
  expect(url).toBe(`http://127.0.0.1:8002/equipment-requirements/${REQUIREMENT}/essential`);
  expect(init.method).toBe("PATCH");
  expect(body).toEqual({ essential: false, note: "Support will bring one" });
});

// AC25-H2 (happy, hotfix 25): marking it essential again sends no note
test("marks a requirement essential again without a note", async () => {
  const fetchMock = respond(200);

  await setRequirementEssential(EVENT, REQUIREMENT, {}, form({ essential: "true", note: "ignored" }));

  expect(sent(fetchMock).body).toEqual({ essential: true, note: null });
});

// AC25-N1 (negative, hotfix 25): not essential without a note is caught before sending
test("does not mark a requirement not essential without a note", async () => {
  const fetchMock = respond(200);

  const state = await setRequirementEssential(EVENT, REQUIREMENT, {}, form({ essential: "false", note: " " }));

  expect(state.message).toMatch(/agreed with Technical Support/);
  expect(fetchMock).not.toHaveBeenCalled();
});

// AC25-N2 (negative, hotfix 25): a closed event answers 409 and says so
test("a closed event's requirement cannot be changed", async () => {
  respond(409);

  const state = await setRequirementEssential(EVENT, REQUIREMENT, {}, form({ essential: "false", note: "x" }));

  expect(state.message).toMatch(/event is closed/);
});
