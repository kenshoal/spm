import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, vi } from "vitest";

vi.mock("@/app/auth/actions", () => ({ logout: vi.fn() }));

import { workspaceLinks } from "@/app/components/app-shell";
import { workspaceForRoles } from "@/lib/auth";

const links = (roles: string[]) => workspaceLinks(roles).map((link) => link.href);

// SCRUM-27 AC1-X2 (cross-cutting): each of the seven roles (organiser, coordinator, lead, venue staff, technical
// support, safety officer, attendee) is offered its own workspace and nothing that belongs to another role
test.each([
  ["event_organiser", ["/event-requests", "/notifications"]],
  ["event_coordinator", ["/coordination/requests", "/venues/search", "/notifications"]],
  ["event_operations_manager", ["/operations/assignments", "/notifications"]],
  ["venue_staff", ["/venues", "/booking-requests", "/venue-blocks", "/venues/search", "/arrangement-reviews", "/notifications"]],
  ["technical_support", ["/equipment", "/equipment/requests", "/arrangement-reviews", "/notifications"]],
  ["safety_officer", ["/venues/search", "/safety", "/notifications"]],
  ["attendee", ["/events", "/notifications"]],
])("%s is offered only its own links", (role, expected) => {
  expect(links([role])).toEqual(expected);
});

// SCRUM-27 AC1-N3 (negative): an unknown role (admin, ghost), or no role at all, is offered nothing
test.each([[["admin"]], [["ghost"]], [[]]])("offers no workspace to %j", (roles) => {
  expect(workspaceLinks(roles)).toEqual([]);
});

// SCRUM-27 AC2-X2 (cross-cutting): the Event Coordinator Lead's own workspace has no coordinator, venue or equipment links
test("the Event Coordinator Lead is not offered another role's workspace", () => {
  const lead = links(["event_operations_manager"]);

  for (const other of ["/coordination/requests", "/venues", "/booking-requests", "/equipment", "/safety", "/event-requests"]) {
    expect(lead).not.toContain(other);
  }
});

// SCRUM-27 AC3-P4 (partition): a person with two roles gets both workspaces, and each role's own links only once
test("a Lead who is also an Organiser is offered both workspaces", () => {
  expect(links(["event_operations_manager", "event_organiser"])).toEqual([
    "/event-requests",
    "/operations/assignments",
    "/notifications",
  ]);
});

// SCRUM-27 AC3-P5 (partition): the order the roles are listed in does not change what is offered
test("the order of a person's roles does not change their links", () => {
  const forward = links(["event_coordinator", "venue_staff", "safety_officer"]);
  const backward = links(["safety_officer", "venue_staff", "event_coordinator"]);

  expect(backward).toEqual(forward);
});

// SCRUM-27 AC3-P6 (partition): a person with several roles lands in the first workspace in a fixed order
test.each([
  [["event_coordinator", "event_organiser"], "/event-requests"],
  [["venue_staff", "event_operations_manager"], "/operations/assignments"],
  [["attendee", "technical_support"], "/equipment"],
  [["attendee", "safety_officer"], "/safety"],
  [["ghost"], "/unauthorised"],
])("%j land in %s", (roles, expected) => {
  expect(workspaceForRoles(roles)).toBe(expected);
});

const PUBLIC_PAGES = ["auth/page.tsx", "unauthorised/page.tsx"];

function pages(directory: string, base = directory): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return pages(path, base);
    return entry.name === "page.tsx" ? [path.slice(base.length + 1)] : [];
  });
}

// SCRUM-27 AC1-X3 (cross-cutting): every page except sign-in and the refusal page checks the session or the role
test("no page is left without a session or role check", () => {
  const root = join(process.cwd(), "app");
  const guard = /require(Role|AnyRole|Organiser|AuthenticatedUser|AccessToken|EventOrganiser)\b/;

  const unguarded = pages(root).filter(
    (page) => !PUBLIC_PAGES.includes(page) && !guard.test(readFileSync(join(root, page), "utf8")),
  );

  expect(pages(root).length).toBeGreaterThan(20);
  expect(unguarded).toEqual([]);
});

// SCRUM-27 AC1-N4 (negative): the two public pages are the only exceptions, so a new page needs a check or an entry here
test("the public pages are exactly sign-in and the refusal page", () => {
  const root = join(process.cwd(), "app");
  const without = pages(root).filter((page) => !/require[A-Z]/.test(readFileSync(join(root, page), "utf8")));

  expect(without.sort()).toEqual([...PUBLIC_PAGES].sort());
});
