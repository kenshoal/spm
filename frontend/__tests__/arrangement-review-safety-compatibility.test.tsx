import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { StatusProgress } from "@/app/components/status-progress";
import {
  EVENT_REQUEST_STATUSES,
  groupRequests,
  type EventRequest,
  type EventRequestStatus,
} from "@/lib/event-requests";

afterEach(cleanup);

// AC5-X8 (cross-cutting): the deployed Safety Review state stays in progress and retains the full ordered coordinator journey.
test("recognises Safety Review and retains its full ordered tracker", () => {
  // Represents the external approved API value, including before its local union is corrected.
  const status = "Safety Review" as EventRequestStatus;
  const request: EventRequest = {
    id: "safety-review-compatibility",
    organiser_id: "organiser-1",
    status,
    event_name: "Safety review arrangement fixture",
    purpose: null,
    description: null,
    proposed_date_times: [],
    expected_attendance: null,
    venue_requirements: null,
    accessibility_needs: null,
    equipment_requirements: null,
    registration_needs: null,
    created_at: "2026-10-16T01:00:00Z",
    updated_at: "2026-10-16T01:00:00Z",
  };
  expect(EVENT_REQUEST_STATUSES).toContain(status);
  expect(groupRequests([request])["in-progress"]).toEqual([request]);
  render(<StatusProgress status={status} />);
  const journey = screen.getByRole("list", { name: "Full event journey" });
  const stages = within(journey).getAllByRole("listitem");
  expect(stages.map((item) => item.textContent?.replace(/^(Completed stage: |Current stage: |Not reached yet: )/, "").replace(/✓$/, ""))).toEqual([
    "Draft", "Submitted", "Under Review", "Approved", "Planning", "Safety Review", "Confirmed", "Completed",
  ]);
  expect(within(journey).getByRole("listitem", { current: "step" }).textContent).toContain("Safety Review");
  expect(stages[4].textContent).toContain("Completed stage: Planning");
  expect(stages[6].textContent).toContain("Not reached yet: Confirmed");
});
