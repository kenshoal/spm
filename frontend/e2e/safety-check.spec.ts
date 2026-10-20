import { expect, test, type APIRequestContext } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";
const VENUE_API = "http://127.0.0.1:8105";
const EQUIPMENT_API = "http://127.0.0.1:8106";

function sessionCookie(value: string) {
  return [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];
}

// One event waiting for its safety check, with a venue booking, an overlapping
// venue block and one equipment requirement with its reservation.
async function seedWaitingEvent(request: APIRequestContext, stamp: number) {
  const name = `Gala ${stamp}`;
  const event = await (await request.post(`${EVENT_API}/__seed`, {
    data: {
      event_name: name, status: "Safety Review", expected_attendance: 300,
      accessibility_needs: "Step-free access", coordinator_id: "playwright-coordinator",
    },
  })).json();
  const venue = await (await request.post(`${VENUE_API}/__seed`, {
    data: { name: `Hall ${stamp}`, location: `Wing ${stamp}`, max_capacity: 250, accessibility_features: ["Ramp"], supported_layouts: ["theatre"] },
  })).json();
  const booking = await (await request.post(`${VENUE_API}/__seed_booking`, {
    data: {
      venue_id: venue.id, event_request_id: event.id, requested_by: "playwright-coordinator",
      start_date: "2026-12-20", end_date: "2026-12-20", slots: ["AM"], status: "approved",
    },
  })).json();
  await request.post(`${EQUIPMENT_API}/__seed_requirement`, {
    data: { id: `req-${stamp}`, event_request_id: event.id, equipment_type: "Wireless microphone", quantity: 2 },
  });
  await request.post(`${EQUIPMENT_API}/__seed_reservation`, {
    data: {
      event_request_id: event.id, requirement_id: `req-${stamp}`, equipment_id: "mic-1", quantity: 2,
      collection_date: "2026-12-19", return_date: "2026-12-21",
    },
  });
  return { name, event, venue, booking };
}

// AC2-H5, AC4a-H5, AC4b-X1 (happy): SCRUM-60 end to end. The Safety Officer sees the
// waiting event with its venue, restrictions and equipment, asks for changes on the
// booking with a reason, and the coordinator reads that reason on the event page.
test("the Safety Officer asks for changes and the coordinator sees why", async ({ page, request }) => {
  const stamp = Date.now();
  const { name, event, venue } = await seedWaitingEvent(request, stamp);
  // A safety block on the booked date is shown as a restriction.
  await page.context().addCookies(sessionCookie("venue-session"));
  const blocked = await page.request.post(`${VENUE_API}/venues/${venue.id}/blocks`, {
    headers: { Authorization: "Bearer venue-session" },
    data: { start_date: "2026-12-20", end_date: "2026-12-20", start_minute: 420, end_minute: 720, reason_category: "safety", reason_detail: "Fire door repair" },
  });
  expect(blocked.ok()).toBeTruthy();

  await page.context().clearCookies();
  await page.context().addCookies(sessionCookie("safety-session"));
  await page.goto("/");
  await page.getByRole("navigation", { name: "Workspaces" }).getByRole("link", { name: "Safety checks" }).click();
  await expect(page).toHaveURL(/\/safety$/);

  const card = page.getByRole("article", { name });
  await expect(card).toContainText("300");
  await expect(card).toContainText("Step-free access");
  await expect(card).toContainText("Capacity 250 (below expected attendance)");
  await expect(card).toContainText("Restriction: Safety (Fire door repair)");
  await expect(card).toContainText("2 × Wireless microphone · 2 reserved");

  // Asking for changes without a reason is refused before anything is sent.
  await card.getByRole("button", { name: "Ask for changes" }).click();
  await expect(card.getByText("Say what needs to change.")).toBeVisible();

  await card.getByLabel("What needs to change").fill("Hall holds 250; the event expects 300.");
  await card.getByRole("checkbox", { name: new RegExp(`Hall ${stamp}`) }).check();
  await card.getByRole("button", { name: "Ask for changes" }).click();
  await expect(page).toHaveURL(/\/safety\?decided=changes_requested$/);
  await expect(page.getByRole("status")).toContainText("back in Planning");
  await expect(page.getByRole("article", { name })).toHaveCount(0);

  await page.context().clearCookies();
  await page.context().addCookies(sessionCookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);
  const panel = page.getByRole("region", { name: "Safety check" });
  await expect(panel).toContainText("Changes requested");
  await expect(panel).toContainText("Hall holds 250; the event expects 300.");
});

// AC3-H4 (happy): approving confirms the event and it leaves the queue.
test("the Safety Officer approves an event", async ({ page, request }) => {
  const stamp = Date.now();
  const { name } = await seedWaitingEvent(request, stamp);

  await page.context().addCookies(sessionCookie("safety-session"));
  await page.goto("/safety");
  await page.getByRole("article", { name }).getByRole("button", { name: "Approve" }).click();

  await expect(page).toHaveURL(/\/safety\?decided=approved$/);
  await expect(page.getByRole("status")).toContainText("Confirmed");
  await expect(page.getByRole("article", { name })).toHaveCount(0);
});
