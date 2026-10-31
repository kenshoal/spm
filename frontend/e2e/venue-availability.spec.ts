import { expect, test } from "@playwright/test";

const VENUE_API = "http://127.0.0.1:8105";

function sessionCookie(value: string) {
  return [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];
}

// AC1-E1 (happy): SCRUM-31 end to end in a browser — a coordinator finds a venue, opens
// its availability from the search result, sees a booked and a blocked time in words, and
// moves to the next month. The mock venue API mirrors the real rules, so this proves the
// screen and its wiring, not the real service.
test("coordinator opens a venue's availability from search and sees booked and blocked times", async ({ page, request }) => {
  const stamp = Date.now();
  const name = `Availability Hall ${stamp}`;
  const wing = `Availability Wing ${stamp}`;
  const venue = await (await request.post(`${VENUE_API}/__seed`, { data: { name, location: wing, max_capacity: 150 } })).json();
  const booking = await request.post(`${VENUE_API}/__seed_booking`, {
    data: { venue_id: venue.id, requested_by: "playwright-coordinator", start_date: "2030-03-04", end_date: "2030-03-05", start_minute: 540, end_minute: 720, status: "approved", decided_by: "venue-staff", decided_at: new Date().toISOString() },
  });
  expect(booking.ok()).toBeTruthy();
  const block = await request.post(`${VENUE_API}/venues/${venue.id}/blocks`, {
    headers: { Authorization: "Bearer venue-session" },
    data: { start_date: "2030-03-06", end_date: "2030-03-06", start_minute: 1080, end_minute: 1440, reason_category: "maintenance", reason_detail: "Private roof repair" },
  });
  expect(block.status()).toBe(201);

  await page.context().addCookies(sessionCookie("coordinator-session"));
  // The link keeps the month of the searched date, so it opens on March 2030.
  await page.goto(`/venues/search?location=${encodeURIComponent(wing)}&date=2030-03-04`);
  await page.getByRole("article", { name }).getByRole("link", { name: /View availability/ }).click();
  await expect(page).toHaveURL(new RegExp(`/venues/availability\\?venue=${venue.id}&month=2030-03`));

  const table = page.getByRole("table", { name: `${name} availability, March 2030` });
  await expect(table.getByRole("row")).toHaveCount(32);
  const fourth = table.getByRole("row").filter({ hasText: /\b4 Mar/ });
  await expect(fourth.getByRole("listitem")).toHaveText(["Booked 09:00–12:00"]);
  await expect(fourth.getByText("Available 07:00–09:00, 12:00–24:00")).toBeVisible();
  const sixth = table.getByRole("row").filter({ hasText: /\b6 Mar/ });
  await expect(sixth.getByRole("listitem")).toHaveText(["Blocked 18:00–24:00"]);
  await expect(sixth.getByText("Available 07:00–18:00")).toBeVisible();
  await expect(table.getByRole("row").filter({ hasText: /\b8 Mar/ }).getByText("Available all day")).toBeVisible();
  await expect(page.getByText("Private roof repair")).toHaveCount(0);

  await page.getByRole("link", { name: "Next month" }).click();
  await expect(page).toHaveURL(/month=2030-04/);
  await expect(page.getByRole("table", { name: `${name} availability, April 2030` }).getByRole("row")).toHaveCount(31);
});

// AC1-U5 (cross-cutting): an organiser cannot open the availability page.
test("organisers cannot open venue availability", async ({ page }) => {
  await page.context().addCookies(sessionCookie("test-session"));
  await page.goto("/venues/availability");
  await expect(page).toHaveURL(/\/unauthorised$/);
});
