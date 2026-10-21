import { expect, test } from "@playwright/test";

const VENUE_API = "http://127.0.0.1:8105";

function sessionCookie(value: string) {
  return [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];
}

// AC1-H1, AC2-H1, AC3-H4, AC4-H1, AC6-H1 (happy): SCRUM-15 end to end — Venue Staff
// work the booking queue: a reasonless rejection is refused, an approval books the
// venue, an overlapping approval is refused as a conflict, the second request is
// rejected with a reason and alternative, the booking shows on the calendar, and
// the requesting Coordinator receives both decisions in their inbox.
test("venue staff approve and reject booking requests and the coordinator is notified", async ({ page, request }) => {
  const stamp = Date.now();
  const name = `Decision Hall ${stamp}`;
  const first = `Open day ${stamp}`;
  const second = `Workshop ${stamp}`;
  const venue = await (await request.post(`${VENUE_API}/__seed`, {
    data: { name, location: `Decision Wing ${stamp}`, max_capacity: 120, operating_slots: ["AM", "PM"] },
  })).json();
  for (const booking of [
    { event_name: first, start_date: "2026-12-10", end_date: "2026-12-11", expected_attendance: 80 },
    { event_name: second, start_date: "2026-12-11", end_date: "2026-12-12", expected_attendance: 30 },
  ]) {
    const seeded = await request.post(`${VENUE_API}/__seed_booking`, {
      data: { ...booking, venue_id: venue.id, requested_by: "playwright-coordinator", slots: ["AM"] },
    });
    expect(seeded.ok()).toBeTruthy();
  }

  await page.context().addCookies(sessionCookie("venue-session"));
  await page.goto("/venues");
  await page.getByRole("navigation", { name: "Workspaces" }).getByRole("link", { name: "Booking requests" }).click();
  await expect(page).toHaveURL(/\/booking-requests$/);

  const firstCard = page.getByRole("article", { name: first });
  await expect(firstCard).toContainText(name);
  await expect(firstCard).toContainText("10 Dec 2026 – 11 Dec 2026");
  await expect(firstCard).toContainText("80 attendees");

  // A rejection without a reason never reaches the API.
  await firstCard.getByRole("button", { name: "Reject" }).click();
  await expect(firstCard.getByText("Enter a reason for rejecting.")).toBeVisible();

  await firstCard.getByRole("button", { name: "Approve" }).click();
  await expect(page).toHaveURL(/decided=approved/);
  await expect(page.getByRole("status")).toHaveText("Booking approved. The requesting Coordinator has been notified.");
  await expect(page.getByRole("article", { name: first })).toHaveCount(0);

  // The second request overlaps on 11 Dec AM, so approval is refused and recorded.
  const secondCard = page.getByRole("article", { name: second });
  await secondCard.getByRole("button", { name: "Approve" }).click();
  await expect(secondCard.getByRole("alert")).toContainText("Approval refused.");
  await expect(secondCard.getByRole("alert")).toContainText("Another approved booking, including the venue's setup and turnaround time, already holds part of this period.");

  await secondCard.getByLabel("Reason for rejecting").fill("Already booked on 11 Dec");
  await secondCard.getByLabel(/Suggested alternative/).fill("Try 13 Dec");
  await secondCard.getByRole("button", { name: "Reject" }).click();
  await expect(page).toHaveURL(/decided=rejected/);

  await page.getByRole("link", { name: "Approved" }).click();
  await expect(page.getByRole("article", { name: first })).toContainText("Approved on");
  await page.getByRole("link", { name: "Rejected" }).click();
  const rejected = page.getByRole("article", { name: second });
  await expect(rejected).toContainText("Reason: Already booked on 11 Dec");
  await expect(rejected).toContainText("Suggested alternative: Try 13 Dec");

  // The approved booking now shows on the venue calendar.
  await page.goto(`/venue-blocks?venue=${venue.id}&month=2026-12`);
  const booked = page.getByRole("table", { name: `${name} availability, December 2026` }).getByRole("row", { name: /Thu 10 Dec/ });
  await expect(booked.getByText(`Booked — ${first}`)).toBeVisible();

  // The requesting Coordinator receives both decisions.
  await page.context().clearCookies();
  await page.context().addCookies(sessionCookie("coordinator-session"));
  await page.goto("/notifications");
  await expect(page.getByRole("article", { name: `Your venue booking for ${first} was approved.` })).toBeVisible();
  const rejection = page.getByRole("article", { name: `Your venue booking request for ${second} was rejected.` });
  await expect(rejection).toContainText("Reason: Already booked on 11 Dec. Suggested alternative: Try 13 Dec");
});

// AC1-X3 (cross-cutting): only Venue Staff can open the booking queue
test("coordinators cannot open the booking request queue", async ({ page }) => {
  await page.context().addCookies(sessionCookie("coordinator-session"));
  await page.goto("/booking-requests");
  await expect(page).toHaveURL(/\/unauthorised$/);
});
