import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { ChangeRequestHistory } from "@/app/components/change-request-history";
import type { EventChangeRequest } from "@/lib/event-requests";

afterEach(cleanup);

// AC4-X4 (cross-cutting): the organiser reads the actual rejection actor and decision time, not merely the earlier proposal creation time.
test("shows the retained rejection audit to the organiser", () => {
  const rejected: EventChangeRequest = {
    id: "change-1", event_request_id: "request-1", organiser_id: "organiser-1",
    status: "Rejected", explanation: "Increase attendance.", proposed_changes: { expected_attendance: 80 },
    base_event_updated_at: "2026-10-18T01:00:00Z", created_at: "2026-10-18T02:00:00Z",
    coordinator_id: "current-coordinator-35", decision_reason: "The existing booking has insufficient capacity.",
    decided_at: "2026-10-20T10:30:00Z",
  };
  render(<ChangeRequestHistory requests={[rejected]} />);
  expect(screen.getByText("Rejected", { exact: true })).toBeDefined();
  expect(screen.getByText(rejected.decision_reason!, { exact: false })).toBeDefined();
  expect(screen.getByText(/current-coordinator-35/)).toBeDefined();
  expect(screen.getByText(/20 Oct 2026.*6:30 pm/i)).toBeDefined();
});
