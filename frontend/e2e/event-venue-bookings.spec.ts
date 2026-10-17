import { expect, test } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";
const VENUE_API = "http://127.0.0.1:8105";

function sessionCookie(value: string) {
  return [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];
}

// AC3-E1, AC4-E1 (happy): SCRUM-61 end to end in a browser — a coordinator opens an
// event with two venue bookings, sees both and where each stands, cancels one, and
// the other is left exactly as it was. The mock venue API does not check the event's
// assignment, so this proves the screen, not the real service's access rule.
test("coordinator sees an event's venue bookings and cancels one without touching the other", async ({ page, request }) => {
  const stamp = Date.now();
  const event = await (await request.post(`${EVENT_API}/__seed`, {
    data: {
      status: "Under Review",
      organiser_id: "playwright-user",
      coordinator_id: "playwright-coordinator",
      event_name: `Multi-venue Summit ${stamp}`,
      purpose: "Use several rooms at once",
      description: "A conference with a main hall and a breakout room.",
      proposed_date_times: ["2026-11-20T02:00:00Z"],
      expected_attendance: 200,
    },
  })).json();
  const main = await (await request.post(`${VENUE_API}/__seed`, { data: { name: `Main Hall ${stamp}`, location: `Wing A ${stamp}`, max_capacity: 300 } })).json();
  const breakout = await (await request.post(`${VENUE_API}/__seed`, { data: { name: `Breakout Room ${stamp}`, location: `Wing B ${stamp}`, max_capacity: 40 } })).json();
  for (const booking of [
    { venue_id: main.id, status: "approved", decided_by: "venue-staff", decided_at: new Date().toISOString(), start_date: "2026-11-20", end_date: "2026-11-21", slots: ["AM", "PM"] },
    { venue_id: breakout.id, status: "pending", start_date: "2026-11-20", end_date: "2026-11-20", slots: ["PM"] },
  ]) {
    const seeded = await request.post(`${VENUE_API}/__seed_booking`, {
      data: { ...booking, event_request_id: event.id, requested_by: "playwright-coordinator" },
    });
    expect(seeded.ok()).toBeTruthy();
  }

  await page.context().addCookies(sessionCookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);

  const panel = page.getByRole("region", { name: "Venue bookings" });
  const rows = panel.getByRole("listitem");
  await expect(rows).toHaveCount(2);
  const mainRow = rows.filter({ hasText: `Main Hall ${stamp}` });
  const breakoutRow = rows.filter({ hasText: `Breakout Room ${stamp}` });
  await expect(mainRow).toContainText("20 Nov 2026 – 21 Nov 2026");
  await expect(mainRow).toContainText("Approved");
  await expect(breakoutRow).toContainText("Pending");

  page.once("dialog", (dialog) => dialog.accept());
  await breakoutRow.getByRole("button", { name: `Cancel booking at Breakout Room ${stamp}` }).click();

  await expect(breakoutRow).toContainText("Cancelled");
  await expect(breakoutRow.getByRole("button")).toHaveCount(0);
  await expect(mainRow).toContainText("Approved");
  await expect(mainRow.getByRole("button", { name: /Cancel booking/ })).toBeVisible();
});

// AC4-E1 (negative): declining the confirmation cancels nothing.
test("declining the confirmation leaves the booking as it was", async ({ page, request }) => {
  const stamp = Date.now();
  const event = await (await request.post(`${EVENT_API}/__seed`, {
    data: { status: "Under Review", organiser_id: "playwright-user", coordinator_id: "playwright-coordinator", event_name: `Keep Booking ${stamp}`, purpose: "Check the confirmation", description: "x", proposed_date_times: ["2026-11-20T02:00:00Z"], expected_attendance: 20 },
  })).json();
  const venue = await (await request.post(`${VENUE_API}/__seed`, { data: { name: `Keep Hall ${stamp}`, location: `Wing C ${stamp}`, max_capacity: 50 } })).json();
  await request.post(`${VENUE_API}/__seed_booking`, {
    data: { venue_id: venue.id, event_request_id: event.id, requested_by: "playwright-coordinator", start_date: "2026-11-22", end_date: "2026-11-22", slots: ["AM"] },
  });

  await page.context().addCookies(sessionCookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: `Cancel booking at Keep Hall ${stamp}` }).click();

  const row = page.getByRole("region", { name: "Venue bookings" }).getByRole("listitem");
  await expect(row).toContainText("Pending");
  await expect(row.getByRole("button", { name: /Cancel booking/ })).toBeVisible();
});
