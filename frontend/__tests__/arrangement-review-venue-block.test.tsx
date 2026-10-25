import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { ArrangementReviewList } from "@/app/components/arrangement-review-list";
import type { ArrangementReview } from "@/lib/arrangement-reviews";

vi.mock("@/app/arrangement-reviews/actions", () => ({ markArrangementReviewed: vi.fn() }));
afterEach(cleanup);

// AC3-X3 (cross-cutting): a flag raised by a venue block is named in words, with its reason, and keeps the ordinary review boundary.
test("labels a venue block and keeps the reason and references", () => {
  const row: ArrangementReview = {
    id: "30000000-0000-4000-8000-000000000001", event_request_id: "30000000-0000-4000-8000-000000000002",
    arrangement: "venue_booking", arrangement_id: "30000000-0000-4000-8000-000000000003",
    trigger_id: "30000000-0000-4000-8000-000000000004",
    trigger_type: "venue_block",
    changed_fields: [],
    reason: "Venue Main Hall is blocked on 2030-03-10, 10:00 to 11:00; this booking needs a new venue.",
    raised_at: "2026-10-24T03:00:00Z", cleared_at: null, cleared_by: null,
  };
  const before = structuredClone(row);
  render(<ArrangementReviewList reviews={[row]} />);
  expect(screen.getByText(/Venue blocked/)).toBeDefined();
  expect(screen.getByText(row.reason)).toBeDefined();
  expect(screen.getByText(`Cause reference: ${row.trigger_id}`)).toBeDefined();
  expect(screen.getByText(`Arrangement reference: ${row.arrangement_id}`)).toBeDefined();
  expect(screen.queryByRole("button", { name: "Mark reviewed" })).toBeNull();
  expect(row).toEqual(before);
});
