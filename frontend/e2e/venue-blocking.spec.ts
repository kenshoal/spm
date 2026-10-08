import { expect, test } from "@playwright/test";

const VENUE_API = "http://127.0.0.1:8105";

function sessionCookie(value: string) {
  return [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];
}

// AC1-H1, AC4-H1, AC2-H1 (happy): SCRUM-23 end to end — Venue Staff block a venue
// through the form, see the blocked slots on the calendar, and a Coordinator's
// dated search no longer offers that slot while other slots stay offered.
test("venue staff block a venue and search stops offering the blocked slot", async ({ page, request }) => {
  const name = `Block Hall ${Date.now()}`;
  const location = `Block Wing ${Date.now()}`;
  const seeded = await request.post(`${VENUE_API}/__seed`, {
    data: { name, location, max_capacity: 80, operating_slots: ["AM", "PM"] },
  });
  const venue = await seeded.json();

  await page.context().addCookies(sessionCookie("venue-session"));
  await page.goto("/venues");
  await page.getByRole("navigation", { name: "Workspaces" }).getByRole("link", { name: "Venue blocks" }).click();
  await page.getByLabel("Show availability for").selectOption({ label: name });
  await page.getByRole("button", { name: "Show" }).click();

  const form = page.getByRole("form", { name: "Block a venue" });
  await form.getByRole("button", { name: "Block venue" }).click();
  await expect(form.getByText("Choose at least one slot.")).toBeVisible();

  await form.getByLabel("Start date").fill("2026-11-20");
  await form.getByLabel("End date").fill("2026-11-21");
  await form.getByRole("checkbox", { name: "AM" }).check();
  await form.getByLabel("Reason").selectOption("maintenance");
  await form.getByLabel(/Detail/).fill("Air-con repairs");
  await form.getByRole("button", { name: "Block venue" }).click();

  await expect(page).toHaveURL(new RegExp(`venue=${venue.id}&month=2026-11&created=1`));
  await expect(page.getByRole("status")).toHaveText("Block saved.");
  const calendar = page.getByRole("table", { name: `${name} availability, November 2026` });
  const blockedDay = calendar.getByRole("row", { name: /Fri 20 Nov/ });
  await expect(blockedDay.getByText("Blocked")).toBeVisible();
  await expect(blockedDay.getByText("Maintenance — Air-con repairs")).toBeVisible();
  await expect(calendar.getByRole("row", { name: /Sun 22 Nov/ }).getByText("Blocked")).toHaveCount(0);

  await page.context().clearCookies();
  await page.context().addCookies(sessionCookie("coordinator-session"));
  await page.goto(`/venues/search?location=${encodeURIComponent(location)}&date=2026-11-20&slot=AM`);
  await expect(page.getByRole("article", { name })).toHaveCount(0);
  await page.goto(`/venues/search?location=${encodeURIComponent(location)}&date=2026-11-20&slot=PM`);
  await expect(page.getByRole("article", { name })).toBeVisible();
});

// AC1-X1 (cross-cutting): only Venue Staff can open the block page
test("coordinators cannot open the venue block page", async ({ page }) => {
  await page.context().addCookies(sessionCookie("coordinator-session"));
  await page.goto("/venue-blocks");
  await expect(page).toHaveURL(/\/unauthorised$/);
});
