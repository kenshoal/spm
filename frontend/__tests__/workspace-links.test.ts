import { expect, test, vi } from "vitest";

vi.mock("@/app/auth/actions", () => ({ logout: vi.fn() }));

import { workspaceLinks } from "@/app/components/app-shell";

// Purpose: SCRUM-27 — each staff role sees the workspace it can use.
test("links each role to its own workspace", () => {
  expect(workspaceLinks(["event_operations_manager"])).toEqual([
    { href: "/operations/assignments", label: "Assignments" },
  ]);
  expect(workspaceLinks(["technical_support"])).toEqual([
    { href: "/equipment", label: "Equipment" },
  ]);
  expect(workspaceLinks(["venue_staff"])).toEqual([
    { href: "/venues", label: "Venues" },
    { href: "/venues/search", label: "Venue search" },
  ]);
  expect(workspaceLinks(["attendee"])).toEqual([]);
});

// Purpose: SCRUM-27 — a multi-role user sees every workspace, each exactly once.
test("gives a multi-role user one link per workspace", () => {
  expect(workspaceLinks(["event_coordinator", "venue_staff"])).toEqual([
    { href: "/coordination/requests", label: "Coordination" },
    { href: "/venues", label: "Venues" },
    { href: "/venues/search", label: "Venue search" },
  ]);
});
