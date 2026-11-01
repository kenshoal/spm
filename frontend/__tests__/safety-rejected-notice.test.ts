import { expect, test } from "vitest";
import { describeNotification, type AppNotification } from "@/lib/notifications";

function notice(event_type: string): AppNotification {
  return {
    id: "n1",
    event_type,
    payload: { event_request_id: "event-1", reason: "Exits blocked" },
    read_at: null,
    created_at: "2026-11-01T00:00:00Z",
  } as unknown as AppNotification;
}

// AC3-H3 (happy, hotfix 3): the coordinator is told it was rejected, why, and where to act
test("describes a safety rejection with its reason and link", () => {
  expect(describeNotification(notice("safety_rejected"))).toEqual({
    message: "The Safety Officer rejected the safety arrangement. Revise the arrangements and resubmit. Exits blocked",
    href: "/coordination/requests/event-1",
  });
});

// AC3-P1 (partition, hotfix 3): asking for changes keeps its own wording
test("describes a request for changes differently", () => {
  expect(describeNotification(notice("safety_changes_requested")).message).toContain("asked for changes");
});
