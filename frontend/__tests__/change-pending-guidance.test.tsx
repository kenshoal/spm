import { cleanup, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, expect, test, vi } from "vitest";

const data = vi.hoisted(() => ({
  getEventRequestStatusView: vi.fn(),
  getCoordinatorAssignment: vi.fn(),
  listReviewDecisions: vi.fn(),
  listEventChangeRequests: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({
  requireRole: vi.fn().mockResolvedValue({ id: "organiser-1", roles: ["event_organiser"] }),
}));
vi.mock("@/lib/event-requests", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/event-requests")>(),
  ...data,
}));
vi.mock("@/app/components/app-shell", () => ({ AppShell: () => null, workspaceLinks: () => [] }));
vi.mock("@/app/components/status-history", () => ({ StatusHistory: () => null, StatusHistoryLoading: () => null }));
vi.mock("@/app/components/registration-reviews", () => ({ RegistrationReviews: () => null, RegistrationReviewsLoading: () => null }));
vi.mock("@/app/components/registration-info", () => ({ RegistrationInfoPanel: () => null, RegistrationInfoLoading: () => null }));
vi.mock("@/app/components/event-arrangements", () => ({ EventArrangementsPanel: () => null }));
vi.mock("@/app/event-requests/actions", () => ({ createEventChangeRequest: vi.fn() }));

import EditEventRequestPage from "@/app/event-requests/[id]/edit/page";

afterEach(cleanup);

// AC2-X4 (cross-cutting): the saved Pending notice preserves the unchanged-plan promise without denying supported coordinator approval.
test("pending organiser notice does not claim all approval is unavailable", async () => {
  data.getEventRequestStatusView.mockResolvedValue({
    request: {
      id: "request-1", organiser_id: "organiser-1", status: "Approved", event_name: "Community Forum",
      purpose: "Gather neighbours", description: "An approved event", proposed_date_times: ["2026-11-20T02:00:00Z"],
      expected_attendance: 40, venue_requirements: "Seminar room", equipment_requirements: "Projector",
      accessibility_needs: "Step-free access", registration_needs: "No registration",
      created_at: "2026-10-04T01:00:00Z", updated_at: "2026-10-04T02:00:00Z",
    },
    history: [], historyUnavailable: false, statusUnsettled: false,
  });
  data.getCoordinatorAssignment.mockResolvedValue({ coordinator_id: "coordinator-1" });
  data.listReviewDecisions.mockResolvedValue([]);
  data.listEventChangeRequests.mockResolvedValue([{
    id: "change-1", event_request_id: "request-1", organiser_id: "organiser-1", status: "Pending",
    explanation: "Increase attendance", proposed_changes: { expected_attendance: 80 },
    base_event_updated_at: "2026-10-04T02:00:00Z", created_at: "2026-10-04T03:00:00Z",
    coordinator_id: null, decision_reason: null, decided_at: null,
  }]);

  // Await the actual server branch before rendering; this is an isolated output check, not a Next/RSC integration claim.
  const shell = await EditEventRequestPage({ params: Promise.resolve({ id: "request-1" }) });
  const boundary = shell.props.children as ReactElement<{ children: Promise<ReactElement<{ id: string; viewerId: string }>> }>;
  const branch = await boundary.props.children;
  const renderBranch = branch.type as (props: typeof branch.props) => Promise<ReactNode>;
  render(await renderBranch(branch.props));

  const notice = screen.getByRole("status");
  expect(notice.textContent).toMatch(/saved.*assigned coordinator.*review/i);
  expect(notice.textContent).toMatch(/event plan remains unchanged/i);
  expect(notice.textContent).not.toMatch(/approval is unavailable/i);
  expect(screen.getByRole("region", { name: "Change request history" })).toBeDefined();
  expect(screen.getByText("Increase attendance")).toBeDefined();
});
