import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";
const VENUE_API = "http://127.0.0.1:8105";

function sessionCookie(value: string) {
  return [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];
}

// AC3-E1, AC4-E1, AC5-E1 (happy): SCRUM-63 end to end in a browser. A venue block has flagged an
// approved booking; the coordinator sees "Needs a new venue", asks for another venue, sees the
// pending replacement (and no second form); Venue Staff approve it; the old booking shows Cancelled
// and the replacement Approved. The mock APIs mirror the real rules, but the flag, the assignment
// check and the transaction are proved by the database verifier and venueService, not here.
test("coordinator replaces a flagged venue booking and staff approval cancels the old one", async ({ page, request }) => {
  const stamp = Date.now();
  const bookingId = randomUUID();
  const event = await (await request.post(`${EVENT_API}/__seed`, {
    data: {
      status: "Under Review",
      organiser_id: "playwright-user",
      coordinator_id: "playwright-coordinator",
      event_name: `Replacement Summit ${stamp}`,
      purpose: "Move to another room",
      description: "A conference whose room was blocked.",
      proposed_date_times: ["2030-03-10T02:00:00Z"],
      expected_attendance: 80,
      arrangement_reviews: [{
        id: randomUUID(), arrangement: "venue_booking", arrangement_id: bookingId, trigger_id: randomUUID(),
        trigger_type: "venue_block", changed_fields: [], reason: "Venue is blocked from 2030-03-10 to 2030-03-10, 10:00 to 11:00; this booking needs a new venue.",
        raised_at: new Date().toISOString(),
      }],
    },
  })).json();
  const blocked = await (await request.post(`${VENUE_API}/__seed`, { data: { name: `Blocked Hall ${stamp}`, location: `Wing A ${stamp}`, max_capacity: 120 } })).json();
  await request.post(`${VENUE_API}/__seed`, { data: { name: `Second Hall ${stamp}`, location: `Wing B ${stamp}`, max_capacity: 120 } });
  const seeded = await request.post(`${VENUE_API}/__seed_booking`, {
    data: {
      id: bookingId, venue_id: blocked.id, event_request_id: event.id, requested_by: "playwright-coordinator", status: "approved",
      decided_by: "venue-staff", decided_at: new Date().toISOString(), start_date: "2030-03-10", end_date: "2030-03-10", start_minute: 540, end_minute: 720,
    },
  });
  expect(seeded.ok()).toBeTruthy();

  await page.context().addCookies(sessionCookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);

  const panel = page.getByRole("region", { name: "Venue bookings" });
  // The venue-name line, so the replacement row ("Replaces the booking at Blocked Hall") is not matched.
  const original = panel.getByRole("listitem").filter({ has: page.getByText(`Blocked Hall ${stamp}`, { exact: true }) });
  await expect(original).toContainText("Needs a new venue");
  await expect(original).toContainText("this booking needs a new venue");

  await original.getByRole("combobox", { name: "Replacement venue" }).selectOption({ label: `Second Hall ${stamp}` });
  await original.getByRole("button", { name: `Request replacement for Blocked Hall ${stamp}` }).click();

  const replacement = panel.getByRole("listitem").filter({ hasText: `Replaces the booking at Blocked Hall ${stamp}` });
  await expect(replacement).toContainText(`Second Hall ${stamp}`);
  await expect(replacement).toContainText("Pending");
  await expect(original).toContainText(`Replacement requested at Second Hall ${stamp} (Pending)`);
  await expect(original.getByRole("button", { name: /Request replacement/ })).toHaveCount(0);

  const replacementId = (await (await request.get(`${VENUE_API}/booking-requests/event/${event.id}`, { headers: { Authorization: "Bearer venue-session" } })).json())
    .find((item: { replaces_booking_id: string | null }) => item.replaces_booking_id === bookingId).id;
  const decision = await request.post(`${VENUE_API}/booking-requests/${replacementId}/decision`, {
    headers: { Authorization: "Bearer venue-session" },
    data: { decision: "approved" },
  });
  expect(decision.status()).toBe(200);

  await page.reload();
  await expect(original).toContainText("Cancelled");
  await expect(original).not.toContainText("Needs a new venue");
  await expect(replacement).toContainText("Approved");
});

// AC4-E2 (negative): an organiser cannot reach the coordinator's event page to request a replacement.
test("organisers do not see the replacement form", async ({ page, request }) => {
  const event = await (await request.post(`${EVENT_API}/__seed`, {
    data: { status: "Under Review", organiser_id: "playwright-user", coordinator_id: "playwright-coordinator", event_name: `Hidden ${Date.now()}`, purpose: "x", description: "x", proposed_date_times: ["2030-03-10T02:00:00Z"], expected_attendance: 5 },
  })).json();

  await page.context().addCookies(sessionCookie("test-session"));
  await page.goto(`/coordination/requests/${event.id}`);

  await expect(page.getByRole("button", { name: /Request replacement/ })).toHaveCount(0);
});


// AC1-E1 (happy, SCRUM-67): the replacement is stored even when it overlaps an approved booking at the new
// venue; the page names the clash, in words, with dates and times only.
test("a replacement that clashes is submitted and the page names the clash", async ({ page, request }) => {
  const stamp = Date.now();
  const bookingId = randomUUID();
  const event = await (await request.post(`${EVENT_API}/__seed`, {
    data: {
      status: "Under Review", organiser_id: "playwright-user", coordinator_id: "playwright-coordinator",
      event_name: `Clash Summit ${stamp}`, purpose: "Move to a busy room", description: "x",
      proposed_date_times: ["2030-03-10T02:00:00Z"], expected_attendance: 60,
      arrangement_reviews: [{
        id: randomUUID(), arrangement: "venue_booking", arrangement_id: bookingId, trigger_id: randomUUID(),
        trigger_type: "venue_block", changed_fields: [], reason: "Venue is blocked; this booking needs a new venue.", raised_at: new Date().toISOString(),
      }],
    },
  })).json();
  const blocked = await (await request.post(`${VENUE_API}/__seed`, { data: { name: `Blocked Hall ${stamp}`, location: `Wing A ${stamp}`, max_capacity: 120 } })).json();
  const busy = await (await request.post(`${VENUE_API}/__seed`, { data: { name: `Busy Hall ${stamp}`, location: `Wing B ${stamp}`, max_capacity: 120 } })).json();
  await request.post(`${VENUE_API}/__seed_booking`, {
    data: { id: bookingId, venue_id: blocked.id, event_request_id: event.id, requested_by: "playwright-coordinator", status: "approved", decided_by: "venue-staff", decided_at: new Date().toISOString(), start_date: "2030-03-10", end_date: "2030-03-10", start_minute: 540, end_minute: 720 },
  });
  await request.post(`${VENUE_API}/__seed_booking`, {
    data: { venue_id: busy.id, event_request_id: randomUUID(), event_name: "Secret Other Gala", requested_by: "someone-else", status: "approved", decided_by: "venue-staff", decided_at: new Date().toISOString(), start_date: "2030-03-10", end_date: "2030-03-10", start_minute: 600, end_minute: 660 },
  });

  await page.context().addCookies(sessionCookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);
  const panel = page.getByRole("region", { name: "Venue bookings" });
  const original = panel.getByRole("listitem").filter({ has: page.getByText(`Blocked Hall ${stamp}`, { exact: true }) });
  await original.getByRole("combobox", { name: "Replacement venue" }).selectOption({ label: `Busy Hall ${stamp}` });
  await original.getByRole("button", { name: `Request replacement for Blocked Hall ${stamp}` }).click();

  await expect(original).toContainText(`Replacement requested at Busy Hall ${stamp} (Pending)`);
  const warning = original.getByRole("status");
  await expect(warning).toContainText(`Busy Hall ${stamp} already has an approved booking that overlaps this request`);
  await expect(warning).toContainText("10 Mar 2030, 10:00–11:00");
  await expect(warning).toContainText("still been submitted");
  await expect(page.getByText("Secret Other Gala")).toHaveCount(0);
});
