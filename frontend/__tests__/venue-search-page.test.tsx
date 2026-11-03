import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const auth = vi.hoisted(() => ({ requireAnyRole: vi.fn() }));
const data = vi.hoisted(() => ({ searchVenues: vi.fn() }));
vi.mock("@/lib/auth", () => ({
  requireAnyRole: auth.requireAnyRole,
  requireAccessToken: async () => "token",
}));
vi.mock("@/lib/venues", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/venues")>()),
  searchVenues: data.searchVenues,
}));
vi.mock("@/app/auth/actions", () => ({ logout: vi.fn() }));

import VenueSearchPage from "@/app/venues/search/page";

afterEach(cleanup);
beforeEach(() => {
  auth.requireAnyRole.mockReset();
  data.searchVenues.mockReset();
  auth.requireAnyRole.mockResolvedValue({ id: "s1", email: "s@example.com", role: "safety_officer", roles: ["safety_officer"] });
  data.searchVenues.mockResolvedValue([]);
});

async function openPage(params: Record<string, string> = {}) {
  render(await VenueSearchPage({ searchParams: Promise.resolve(params) }));
}

// SCRUM-9 AC6-X1 (cross-cutting): coordinators, venue staff and safety officers can open the search
test("the search page is open to coordinators, venue staff and safety officers", async () => {
  await openPage({ required_capacity: "50" });

  expect(auth.requireAnyRole).toHaveBeenCalledWith(["event_coordinator", "venue_staff", "safety_officer"]);
  expect(data.searchVenues).toHaveBeenCalledTimes(1);
});

// SCRUM-9 AC6-N1 (negative): a refused role never reaches the search
test("a refused role searches nothing", async () => {
  auth.requireAnyRole.mockRejectedValue(new Error("NEXT_REDIRECT"));

  await expect(openPage({ required_capacity: "50" })).rejects.toThrow("NEXT_REDIRECT");

  expect(data.searchVenues).not.toHaveBeenCalled();
});
