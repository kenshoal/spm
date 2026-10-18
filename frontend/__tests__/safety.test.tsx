import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

vi.mock("@/app/safety/actions", () => ({ decideSafety: vi.fn() }));

import { SafetyDecisionForm } from "@/app/safety/decision-form";
import { SafetyReviewsPanel } from "@/app/components/safety-reviews-panel";
import { workspaceLinks } from "@/app/components/app-shell";
import { workspaceForRoles } from "@/lib/auth";
import { overlappingBlocks, parseSafetyDecisionForm, type SafetyReview } from "@/lib/safety";
import type { VenueBlock } from "@/lib/venue-block-options";

afterEach(cleanup);

const BOOKING = "11111111-1111-4111-8111-111111111111";
const RESERVATION = "22222222-2222-4222-8222-222222222222";

function form(fields: [string, string][]): FormData {
  const data = new FormData();
  for (const [key, value] of fields) data.append(key, value);
  return data;
}

function block(overrides: Partial<VenueBlock>): VenueBlock {
  return {
    id: "block-1",
    venue_id: "venue-1",
    start_date: "2026-11-20",
    end_date: "2026-11-20",
    slots: ["AM"],
    reason_category: "safety",
    reason_detail: "Fire door repair",
    status: "active",
    created_by: "staff-1",
    created_at: "2026-10-01T00:00:00Z",
    ...overrides,
  };
}

// AC3-H2 (happy, SCRUM-60 increment 3): approving sends only the decision.
test("an approval sends only the decision", () => {
  expect(parseSafetyDecisionForm(form([["decision", "approved"], ["reason", "typed"], ["target", `venue_booking:${BOOKING}`]]))).toEqual({
    payload: { decision: "approved", targets: [] },
    errors: {},
  });
});

// AC4a-H3 (happy): asking for changes sends the trimmed reason and each ticked arrangement.
test("asking for changes sends the reason and chosen targets", () => {
  expect(
    parseSafetyDecisionForm(
      form([
        ["decision", "changes_requested"],
        ["reason", "  Exit routes missing  "],
        ["target", `venue_booking:${BOOKING}`],
        ["target", `equipment_reservation:${RESERVATION}`],
      ]),
    ),
  ).toEqual({
    payload: {
      decision: "changes_requested",
      reason: "Exit routes missing",
      targets: [
        { arrangement: "venue_booking", id: BOOKING },
        { arrangement: "equipment_reservation", id: RESERVATION },
      ],
    },
    errors: {},
  });
});

// AC4a-N4 (negative): asking for changes needs a reason of at most 2000 characters,
// and an unknown decision is refused before the API.
test.each([
  ["blank reason", [["decision", "changes_requested"], ["reason", "  "]], { reason: "Say what needs to change." }],
  ["2001 characters", [["decision", "changes_requested"], ["reason", "r".repeat(2001)]], { reason: "Keep the reason to 2000 characters or fewer." }],
  ["unknown decision", [["decision", "rejected"]], { decision: "Choose approve or ask for changes." }],
] as [string, [string, string][], Record<string, string>][])("refuses %s", (_label, fields, errors) => {
  expect(parseSafetyDecisionForm(form(fields)).errors).toEqual(errors);
});

// AC2-X1 (cross-cutting): only active blocks that overlap the booking's dates and
// slots are shown as restrictions.
test("shows only active blocks overlapping the booking", () => {
  const booking = { start_date: "2026-11-20", end_date: "2026-11-21", slots: ["AM" as const] };
  const overlapping = block({ id: "overlap" });
  const lifted = block({ id: "lifted", status: "lifted" });
  const otherDay = block({ id: "other-day", start_date: "2026-11-25", end_date: "2026-11-25" });
  const otherSlot = block({ id: "other-slot", slots: ["PM"] });

  expect(overlappingBlocks([overlapping, lifted, otherDay, otherSlot], booking).map((b) => b.id)).toEqual(["overlap"]);
});

// AC1-X3 (cross-cutting): a Safety Officer lands on, and is offered, the safety queue.
test("routes the Safety Officer to the safety queue", () => {
  expect(workspaceForRoles(["safety_officer"])).toBe("/safety");
  expect(workspaceLinks(["safety_officer"]).map((link) => link.href)).toContain("/safety");
  expect(workspaceLinks(["event_coordinator"]).map((link) => link.href)).not.toContain("/safety");
});

// AC4a-X2 (cross-cutting): the decision form offers each arrangement as a target
// and both decisions.
test("offers each arrangement as a target and both decisions", () => {
  render(
    <SafetyDecisionForm
      eventRequestId="event-1"
      arrangements={[
        { arrangement: "venue_booking", id: BOOKING, label: "Hall B, 20 Nov 2026" },
        { arrangement: "equipment_reservation", id: RESERVATION, label: "2 × Wireless microphone" },
      ]}
    />,
  );

  expect(screen.getByRole("checkbox", { name: "Hall B, 20 Nov 2026" })).toBeDefined();
  expect(screen.getByRole("checkbox", { name: "2 × Wireless microphone" })).toBeDefined();
  expect(screen.getByRole("button", { name: "Approve" })).toBeDefined();
  expect(screen.getByRole("button", { name: "Ask for changes" })).toBeDefined();
  expect(screen.queryByRole("button", { name: /reject/i })).toBeNull();
});

// AC4a-H4 (happy): the coordinator reads the Safety Officer's reason on the event page.
test("shows the Safety Officer's decisions to the coordinator", () => {
  const reviews: SafetyReview[] = [
    {
      id: "review-1",
      event_request_id: "event-1",
      decision: "changes_requested",
      reason: "Exit routes for 300 people are not shown for Hall B.",
      targets: [{ arrangement: "venue_booking", id: BOOKING }],
      decided_by: "officer-1",
      decided_at: "2026-10-18T09:00:00Z",
    },
  ];

  render(<SafetyReviewsPanel reviews={reviews} />);

  expect(screen.getByRole("heading", { name: "Safety check" })).toBeDefined();
  expect(screen.getByText("Changes requested")).toBeDefined();
  expect(screen.getByText("Exit routes for 300 people are not shown for Hall B.")).toBeDefined();
});

// AC4a-P2 (partition): with no decision yet, the panel says so instead of showing nothing.
test("says when there is no safety decision yet", () => {
  render(<SafetyReviewsPanel reviews={[]} />);

  expect(screen.getByText("No safety decision yet.")).toBeDefined();
});
