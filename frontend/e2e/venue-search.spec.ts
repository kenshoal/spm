import { expect, test } from "@playwright/test";

const VENUE_API = "http://127.0.0.1:8105";

// Purpose: SCRUM-9 AC2–AC4 — results match every filter, never fall below the
// requested capacity, and exclude blocked venues.
// SCRUM-9 AC2-X1 (cross-cutting): a coordinator's results match every filter, never fall below the capacity and exclude blocked venues
test("coordinator filters venues by capacity and facilities", async ({ page, request }) => {
  const seed = (data: object) => request.post(`${VENUE_API}/__seed`, { data });
  await seed({ name: "Search Big Hall", location: "Search Wing", max_capacity: 300, facilities: ["Projector", "Stage"], supported_layouts: ["theatre"] });
  await seed({ name: "Search Small Room", location: "Search Wing", max_capacity: 20, facilities: ["Projector"], supported_layouts: ["boardroom"] });
  await seed({ name: "Search Closed Hall", location: "Search Wing", max_capacity: 400, facilities: ["Projector", "Stage"], status: "blocked" });

  await page.context().addCookies([{ name: "cs_access_token", value: "coordinator-session", url: "http://127.0.0.1:3100" }]);
  await page.goto("/venues/search");
  await page.getByLabel("Attendees").fill("0");
  await page.getByRole("button", { name: "Search venues" }).click();
  await expect(page.getByText("Enter a whole number greater than zero.")).toBeVisible();

  await page.getByLabel("Attendees").fill("100");
  await page.getByLabel("Location").fill("Search Wing");
  await page.getByLabel("Required facilities").fill("projector, stage");
  await page.getByRole("button", { name: "Search venues" }).click();

  await expect(page.getByRole("article", { name: "Search Big Hall" })).toBeVisible();
  await expect(page.getByRole("article", { name: "Search Small Room" })).toHaveCount(0);
  await expect(page.getByRole("article", { name: "Search Closed Hall" })).toHaveCount(0);
  await expect(page.getByText("1 venue matches every filter.")).toBeVisible();
});

// Purpose: SCRUM-27 — organisers cannot search the internal venue catalogue.
// SCRUM-9 AC6-X1 (cross-cutting): an Event Organiser cannot open venue search
test("organisers cannot open venue search", async ({ page }) => {
  await page.context().addCookies([{ name: "cs_access_token", value: "test-session", url: "http://127.0.0.1:3100" }]);
  await page.goto("/venues/search");
  await expect(page).toHaveURL(/\/unauthorised$/);
});

// Purpose: An expired venue-service session goes to sign-in, not an outage banner.
// SCRUM-9 AC6-X2 (cross-cutting): an expired session goes to sign-in, not to results
test("an expired venue-service session redirects to sign-in", async ({ page }) => {
  await page.context().addCookies([{ name: "cs_access_token", value: "other-coordinator-session", url: "http://127.0.0.1:3100" }]);
  await page.goto("/venues/search?required_capacity=10");
  await expect(page).toHaveURL(/\/auth$/);
});

// Purpose: SCRUM-12 AC4-H6, AC5-X2 — a coordinator checks a search result against
// a larger, then a smaller, attendance and sees the verdict in words with the
// mismatch reason; the check leaves the venue in the results.
test("coordinator checks a venue's suitability from the search results", async ({ page, request }) => {
  await request.post(`${VENUE_API}/__seed`, {
    data: { name: "Suitability Hall", location: "Suitability Wing", max_capacity: 120, facilities: ["Projector"], supported_layouts: ["theatre"] },
  });

  await page.context().addCookies([{ name: "cs_access_token", value: "coordinator-session", url: "http://127.0.0.1:3100" }]);
  await page.goto("/venues/search?location=Suitability+Wing");
  const card = page.getByRole("article", { name: "Suitability Hall" });
  await card.getByText("Check suitability").click();

  await card.getByLabel("Expected attendance").fill("500");
  await card.getByRole("button", { name: "Check this venue" }).click();
  await expect(card.getByRole("status")).toContainText("Not suitable");
  await expect(card.getByRole("status")).toContainText("Expected attendance 500 exceeds the venue's maximum capacity of 120.");

  await card.getByLabel("Expected attendance").fill("50");
  await card.getByRole("button", { name: "Check this venue" }).click();
  await expect(card.getByRole("status")).toContainText("Suitable");
  await expect(card.getByRole("status")).not.toContainText("Not suitable");

  await page.reload();
  await expect(page.getByRole("article", { name: "Suitability Hall" })).toBeVisible();
});
