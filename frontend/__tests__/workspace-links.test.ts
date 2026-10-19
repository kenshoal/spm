import { expect, test, vi } from "vitest";

vi.mock("@/app/auth/actions", () => ({ logout: vi.fn() }));

import { workspaceLinks } from "@/app/components/app-shell";

const notifications = { href: "/notifications", label: "Notifications" };

// AC5-X9 (cross-cutting): SCRUM-64 adds the staff review workspace while preserving SCRUM-27 role-specific navigation.
test("links each role to its own workspace", () => {
  expect(workspaceLinks(["event_operations_manager"])).toEqual([
    { href: "/operations/assignments", label: "Assignments" },
    notifications,
  ]);
  expect(workspaceLinks(["technical_support"])).toEqual([
    { href: "/equipment", label: "Equipment" },
    { href: "/arrangement-reviews", label: "Arrangement reviews" },
    notifications,
  ]);
  expect(workspaceLinks(["venue_staff"])).toEqual([
    { href: "/venues", label: "Venues" },
    { href: "/booking-requests", label: "Booking requests" },
    { href: "/venue-blocks", label: "Venue blocks" },
    { href: "/venues/search", label: "Venue search" },
    { href: "/arrangement-reviews", label: "Arrangement reviews" },
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

// AC5-X9 (cross-cutting): the approved review workspace appears once alongside all SCRUM-27 multi-role workspaces.
test("gives a multi-role user one link per workspace", () => {
  expect(workspaceLinks(["event_coordinator", "venue_staff"])).toEqual([
    { href: "/coordination/requests", label: "Coordination" },
    { href: "/venues", label: "Venues" },
    { href: "/booking-requests", label: "Booking requests" },
    { href: "/venue-blocks", label: "Venue blocks" },
    { href: "/venues/search", label: "Venue search" },
    { href: "/arrangement-reviews", label: "Arrangement reviews" },
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

// AC1-X4 (cross-cutting): only Venue Staff get the Booking requests workspace link
test("offers the Booking requests link to Venue Staff only", () => {
  const hasLink = (roles: string[]) => workspaceLinks(roles).some((link) => link.href === "/booking-requests");

  expect(hasLink(["venue_staff"])).toBe(true);
  for (const role of ["event_coordinator", "event_organiser", "event_operations_manager", "technical_support", "attendee"]) {
    expect(hasLink([role])).toBe(false);
  }
});
