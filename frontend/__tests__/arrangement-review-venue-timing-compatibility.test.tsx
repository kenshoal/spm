import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { ArrangementReviewList } from "@/app/components/arrangement-review-list";
import type { ArrangementReview } from "@/lib/arrangement-reviews";
import { markArrangementReviewed } from "@/app/arrangement-reviews/actions";

vi.mock("@/app/arrangement-reviews/actions", () => ({ markArrangementReviewed: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

// AC6-X2 (cross-cutting): timing-change evidence needs a plain label while staff acknowledgement and coordinator read-only controls retain their existing boundary.
test("labels venue timing changes and preserves ordinary review controls", () => {
  const row: ArrangementReview = {
    id: "20000000-0000-4000-8000-000000000001", event_request_id: "20000000-0000-4000-8000-000000000002",
    arrangement: "venue_booking", arrangement_id: "20000000-0000-4000-8000-000000000003",
    trigger_id: "20000000-0000-4000-8000-000000000004",
    trigger_type: "venue_timing_change",
    changed_fields: ["setup_minutes", "turnaround_minutes"],
    reason: "Venue setup changed from 0 to 30 minutes; booking padding now conflicts.",
    raised_at: "2026-10-21T03:00:00Z", cleared_at: null, cleared_by: null,
  };
  const before = structuredClone(row);
  const staff = render(<ArrangementReviewList reviews={[row]} canClear />);
  expect(screen.getByText(/Venue timing change/)).toBeDefined();
  expect(screen.getByText(row.reason)).toBeDefined();
  expect(screen.getByText(`Cause reference: ${row.trigger_id}`)).toBeDefined();
  expect(screen.getByText(`Arrangement reference: ${row.arrangement_id}`)).toBeDefined();
  expect(screen.getByText(`Event reference: ${row.event_request_id}`)).toBeDefined();
  expect(staff.container.querySelector("time")?.getAttribute("datetime")).toBe(row.raised_at);
  const button = screen.getByRole("button", { name: "Mark reviewed" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  fireEvent.click(screen.getByRole("checkbox", { name: "I have checked this arrangement against the recorded change" }));
  expect(button.disabled).toBe(false);
  expect(markArrangementReviewed).not.toHaveBeenCalled();
  staff.unmount();
  render(<ArrangementReviewList reviews={[row]} />);
  expect(screen.getByText(/Venue timing change/)).toBeDefined();
  expect(screen.queryByRole("button", { name: "Mark reviewed" })).toBeNull();
  expect(screen.queryByRole("checkbox")).toBeNull();
  expect(row).toEqual(before);
});
