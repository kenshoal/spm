import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "token", requireRole: vi.fn() }));

import {
  acceptWaitlistOffer,
  joinWaitlist,
  registerForEvent,
  withdrawFromWaitlist,
  withdrawRegistration,
} from "@/app/events/actions";

function respond(status: number, body: unknown = {}) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

beforeEach(() => {
  vi.unstubAllGlobals();
  navigation.revalidatePath.mockReset();
});

// AC1-H1 (happy, SCRUM-24 UI): after joining, the event's own page (/events/[id])
// re-renders too, so "Join the waiting list" turns into "You are on the waiting list"
test.each([
  ["join the waiting list", () => joinWaitlist("e1")],
  ["register", () => registerForEvent("e1")],
  ["withdraw a registration", () => withdrawRegistration("r1")],
  ["accept an offer", () => acceptWaitlistOffer("w1")],
  ["leave the waiting list", () => withdrawFromWaitlist("w1")],
])("%s refreshes every page under /events", async (_name, run) => {
  respond(201);

  expect(await run()).toEqual({ done: true });

  expect(navigation.revalidatePath).toHaveBeenCalledWith("/events", "layout");
});

// AC1-P1, AC4-N2, AC7-N2 (SCRUM-24 UI): the waiting-list refusals the API actually
// sends (waitlist_rules.py) read as sentences, not the generic retry message
test.each([
  ["already_waitlisted", () => joinWaitlist("e1"), "You are already on the waiting list."],
  ["entry_not_found", () => acceptWaitlistOffer("w1"), "This offer is no longer available."],
  ["not_offered", () => acceptWaitlistOffer("w1"), "There is no offer to act on for this entry."],
  ["waitlist_closed", () => joinWaitlist("e1"), "The waiting list for this event has closed."],
])("waiting-list refusal %s", async (code, run, message) => {
  respond(409, { code });

  expect(await run()).toEqual({ message });
});

// AC1-B5..B7 (UI, hotfix): the event page offers "Join the waiting list" only
// before the cut-off (72 hours before the first session), when a join can stick
test.each([
  ["one second before the cut-off", "2030-02-07T09:59:59Z", true],
  ["at the cut-off", "2030-02-07T10:00:00Z", false],
  ["after the start", "2030-02-10T10:00:01Z", false],
])("the waiting list is open %s", async (_name, at, open) => {
  const { isWaitlistOpen } = await import("@/lib/attendee");
  const event = { proposed_date_times: ["2030-02-11T10:00:00Z", "2030-02-10T10:00:00Z"] };

  expect(isWaitlistOpen(event, Date.parse(at))).toBe(open);
});
