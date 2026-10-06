import { expect, test, vi } from "vitest";

vi.mock("@/app/auth/actions", () => ({ logout: vi.fn() }));

import { workspaceLinks } from "@/app/components/app-shell";

const notifications = { href: "/notifications", label: "Notifications" };

// Purpose: SCRUM-27 — each staff role sees the workspace it can use.
test("links each role to its own workspace", () => {
  expect(workspaceLinks(["event_operations_manager"])).toEqual([
    { href: "/operations/assignments", label: "Assignments" },
    notifications,
  ]);
  expect(workspaceLinks(["technical_support"])).toEqual([
    { href: "/equipment", label: "Equipment" },
    notifications,
  ]);
  expect(workspaceLinks(["venue_staff"])).toEqual([
    { href: "/venues", label: "Venues" },
    { href: "/venue-blocks", label: "Venue blocks" },
    { href: "/venues/search", label: "Venue search" },
    notifications,
  ]);
  expect(workspaceLinks(["attendee"])).toEqual([]);
});

// AC6-X2 (cross-cutting): SCRUM-37 — every user with a workspace can reach their notifications,
// after their workspaces so the logo still opens their main workspace.
test("adds the notifications inbox after the workspaces", () => {
  expect(workspaceLinks(["event_organiser"])).toEqual([
    { href: "/event-requests", label: "My event requests" },
    notifications,
  ]);
  expect(workspaceLinks(["event_coordinator"])).toEqual([
    { href: "/coordination/requests", label: "Coordination" },
    { href: "/venues/search", label: "Venue search" },
    notifications,
  ]);
});

// Purpose: SCRUM-27 — a multi-role user sees every workspace, each exactly once.
test("gives a multi-role user one link per workspace", () => {
  expect(workspaceLinks(["event_coordinator", "venue_staff"])).toEqual([
    { href: "/coordination/requests", label: "Coordination" },
    { href: "/venues", label: "Venues" },
    { href: "/venue-blocks", label: "Venue blocks" },
    { href: "/venues/search", label: "Venue search" },
    notifications,
  ]);
});

// AC1-X3 (cross-cutting): only Venue Staff get the Venue blocks workspace link
test("offers the Venue blocks link to Venue Staff only", () => {
  const hasBlocks = (roles: string[]) => workspaceLinks(roles).some((link) => link.href === "/venue-blocks");

  expect(hasBlocks(["venue_staff"])).toBe(true);
  for (const role of ["event_coordinator", "event_organiser", "event_operations_manager", "technical_support", "attendee"]) {
    expect(hasBlocks([role])).toBe(false);
  }
});
