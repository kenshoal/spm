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
    start_minute: 420,
    end_minute: 720,
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
  expect(parseSafetyDecisionForm(form([["decision", "approved"], ["reason", "  "]]))).toEqual({
    payload: { decision: "approved", targets: [] },
    errors: {},
  });
});

// AC3-N2 (negative, review of PR #62): Approve never silently drops a typed
// reason or ticked arrangements.
test.each([
  ["a reason", [["decision", "approved"], ["reason", "Exit routes missing"]]],
  ["a ticked arrangement", [["decision", "approved"], ["target", `venue_booking:${BOOKING}`]]],
] as [string, [string, string][]][])("refuses to approve with %s filled in", (_label, fields) => {
  expect(parseSafetyDecisionForm(form(fields)).errors).toEqual({
    decision: "You typed a reason or ticked arrangements. Clear them to approve, or choose Ask for changes.",
  });
});

// AC3-H2 (happy, hotfix 3): rejecting sends the trimmed reason and each ticked arrangement.
test("rejecting sends the reason and chosen targets", () => {
  expect(
    parseSafetyDecisionForm(
      form([
        ["decision", "rejected"],
        ["reason", "  Exits blocked  "],
        ["target", `venue_booking:${BOOKING}`],
      ]),
    ),
  ).toEqual({
    payload: {
      decision: "rejected",
      reason: "Exits blocked",
      targets: [{ arrangement: "venue_booking", id: BOOKING }],
    },
    errors: {},
  });
});

// AC3-N3 (negative, hotfix 3): rejecting without a reason asks for one and sends nothing.
test("rejecting without a reason is refused locally", () => {
  expect(parseSafetyDecisionForm(form([["decision", "rejected"], ["reason", "  "]])).errors).toEqual({
    reason: "Say why the safety arrangement is rejected.",
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
  ["unknown decision", [["decision", "maybe"]], { decision: "Choose approve, ask for changes or reject." }],
] as [string, [string, string][], Record<string, string>][])("refuses %s", (_label, fields, errors) => {
  expect(parseSafetyDecisionForm(form(fields)).errors).toEqual(errors);
});

// AC2-X1 (cross-cutting): only active blocks that overlap the booking's dates and times (SCRUM-65) are restrictions
test("shows only active blocks overlapping the booking", () => {
  const booking = { start_date: "2026-11-20", end_date: "2026-11-21", start_minute: 600, end_minute: 840 };
  const overlapping = block({ id: "overlap" });
  const lifted = block({ id: "lifted", status: "lifted" });
  const otherDay = block({ id: "other-day", start_date: "2026-11-25", end_date: "2026-11-25" });
  // Starts exactly when the booking ends, so the half-open ranges do not overlap.
  const otherSlot = block({ id: "other-slot", start_minute: 840, end_minute: 1080 });

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
test("offers each arrangement as a target and all three decisions", () => {
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
  expect(screen.getByRole("button", { name: "Reject safety arrangement" })).toBeDefined();
});

// AC2-N4 (negative, review of PR #62): when venue details or restrictions could
// not be loaded, the card says so and Approve is disabled, never "all clear".
test("blocks approval when venue details could not be loaded", () => {
  render(
    <SafetyDecisionForm
      eventRequestId="event-1"
      arrangements={[]}
      approveBlockedReason="Venue details or restrictions couldn't be loaded. Don't approve until this is fixed."
    />,
  );

  expect(screen.getByRole("alert").textContent).toContain("couldn't be loaded");
  expect((screen.getByRole("button", { name: "Approve" }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: "Ask for changes" }) as HTMLButtonElement).disabled).toBe(false);
});

// AC4a-H6 (happy, review of PR #62): the coordinator sees which arrangements the
// Safety Officer asked to recheck.
test("lists the arrangements the Safety Officer flagged", () => {
  render(
    <SafetyReviewsPanel
      reviews={[
        {
          id: "review-2",
          event_request_id: "event-1",
          decision: "changes_requested",
          reason: "Recheck the hall.",
          targets: [
            { arrangement: "venue_booking", id: BOOKING },
            { arrangement: "equipment_reservation", id: RESERVATION },
          ],
          decided_by: "officer-1",
          decided_at: "2026-10-18T09:00:00Z",
        },
      ]}
      labels={{ [BOOKING]: "Hall B, 20 Nov 2026" }}
    />,
  );

  expect(screen.getByText("To recheck:")).toBeDefined();
  expect(screen.getByText("Hall B, 20 Nov 2026")).toBeDefined();
  expect(screen.getByText("An equipment reservation")).toBeDefined();
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
