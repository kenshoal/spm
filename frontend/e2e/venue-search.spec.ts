import { expect, test } from "@playwright/test";

const VENUE_API = "http://127.0.0.1:8105";

// Purpose: SCRUM-9 AC2–AC4 — results match every filter, never fall below the
// requested capacity, and exclude blocked venues.
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
test("organisers cannot open venue search", async ({ page }) => {
  await page.context().addCookies([{ name: "cs_access_token", value: "test-session", url: "http://127.0.0.1:3100" }]);
  await page.goto("/venues/search");
  await expect(page).toHaveURL(/\/unauthorised$/);
});
