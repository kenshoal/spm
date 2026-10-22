import { expect, test } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";
const cookie = (value: string) => [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];

// AC4-X4, AC1-H1, AC1-X1, AC1-X2, AC1-X3, AC2-X1 (cross-cutting): coordinator rejection survives reload and reaches organiser history/inbox while the original plan and lifecycle history remain unchanged
test("organiser requests a change and reads the coordinator rejection from history and inbox", async ({ page, request }) => {
  await page.setViewportSize({ width: 969, height: 930 });
  const seeded = await request.post(`${EVENT_API}/__seed`, {
    data: {
      status: "Approved",
      organiser_id: "playwright-change-request-owner",
      coordinator_id: "playwright-coordinator",
      event_name: "SCRUM-35 Community Forum",
      purpose: "Community engagement",
      description: "An approved event awaiting planning.",
      proposed_date_times: ["2026-11-20T02:00:00Z"],
      expected_attendance: 40,
      venue_requirements: "Seminar room",
      accessibility_needs: "Step-free access",
      equipment_requirements: "Projector",
      registration_needs: "Online registration",
    },
  });
  expect(seeded.status()).toBe(201);
  const event = await seeded.json();

  // Keep received notices isolated from parallel inbox specifications using the shared default organiser.

  await page.context().addCookies(cookie("change-request-owner-session"));
  await page.goto("/event-requests");
  await page.locator(`a[href="/event-requests/${event.id}/edit"]`)
    .filter({ hasText: "Change requests" }).click();
  await expect(page.getByRole("dialog", { name: "Request a change" })).toHaveCount(0);
  const eventHeading = page.getByRole("heading", { name: event.event_name });
  await expect(eventHeading.locator("..").getByRole("button", { name: "Request a change" })).toBeVisible();
  await page.getByRole("button", { name: "Request a change" }).click();
  const changeDialog = page.getByRole("dialog", { name: "Request a change" });
  await expect(changeDialog).toBeVisible();
  const dialogBounds = await changeDialog.boundingBox();
  expect(dialogBounds).not.toBeNull();
  expect(Math.abs(dialogBounds!.x + dialogBounds!.width / 2 - 969 / 2)).toBeLessThan(10);
  expect(Math.abs(dialogBounds!.y + dialogBounds!.height / 2 - 930 / 2)).toBeLessThan(10);
  await changeDialog.getByRole("button", { name: "Close" }).click();
  await expect(changeDialog).not.toBeVisible();
  const beforeSubmission = await request.get(`${EVENT_API}/event-requests/${event.id}/change-requests`, {
    headers: { Authorization: "Bearer change-request-owner-session" },
  });
  expect(beforeSubmission.status()).toBe(200);
  expect(await beforeSubmission.json()).toEqual([]);
  await page.getByRole("button", { name: "Request a change" }).click();
  await changeDialog.getByLabel("Reason for change").fill("Registrations exceeded the initial estimate.");
  await changeDialog.getByLabel("Proposed attendance").fill("80");
  await changeDialog.getByRole("button", { name: "Request change" }).click();
  await expect(page.getByText(/saved for the assigned coordinator/i)).toBeVisible();
  await expect(page.getByRole("region", { name: "Change request history" }).getByText("Pending", { exact: true })).toBeVisible();

  await page.context().addCookies(cookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);
  await expect(page.getByText("Registrations exceeded the initial estimate.")).toBeVisible();
  await expect(page.getByText("80", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve change" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reject change" })).toBeVisible();
  const beforeHistory = await request.get(`${EVENT_API}/event-requests/${event.id}/status-history`, {
    headers: { Authorization: "Bearer coordinator-session" },
  });
  expect(beforeHistory.status()).toBe(200);
  const lifecycle = await beforeHistory.json();
  expect(lifecycle.length).toBeGreaterThan(0);
  const reason = "The current booking cannot accommodate the proposed attendance increase.";
  await page.getByRole("textbox", { name: /reason/i }).fill(reason);
  await page.getByRole("button", { name: "Reject change" }).click();
  const proposal = page.getByRole("article").filter({ hasText: "Registrations exceeded the initial estimate." });
  await expect(proposal.getByText("Rejected", { exact: true })).toBeVisible();
  await expect(proposal.getByText(reason, { exact: false })).toBeVisible();
  await page.reload();
  await expect(proposal.getByText("Rejected", { exact: true })).toBeVisible();
  await expect(proposal.getByRole("button", { name: "Reject change" })).toHaveCount(0);
  const changes = await request.get(`${EVENT_API}/event-requests/${event.id}/change-requests`, {
    headers: { Authorization: "Bearer coordinator-session" },
  });
  expect(changes.status()).toBe(200);
  const saved = await changes.json();
  expect(saved).toHaveLength(1);
  expect(saved[0]).toMatchObject({ status: "Rejected", coordinator_id: "playwright-coordinator", decision_reason: reason });
  expect(Number.isNaN(Date.parse(saved[0].decided_at))).toBe(false);
  const deniedApproval = await request.post(`${EVENT_API}/event-requests/${event.id}/change-requests/${saved[0].id}/decision`, {
    headers: { Authorization: "Bearer coordinator-session" }, data: { decision: "Approved" },
  });
  expect(deniedApproval.status()).toBe(409);
  expect((await deniedApproval.json()).detail).toBe("The change cannot be decided in its current state");
  const unchanged = await request.get(`${EVENT_API}/event-requests/${event.id}`, {
    headers: { Authorization: "Bearer coordinator-session" },
  });
  expect(unchanged.status()).toBe(200);
  expect(await unchanged.json()).toEqual(event);
  const afterHistory = await request.get(`${EVENT_API}/event-requests/${event.id}/status-history`, {
    headers: { Authorization: "Bearer coordinator-session" },
  });
  expect(await afterHistory.json()).toEqual(lifecycle);

  // Seed the received inbox contract; actual producer HTTP/persistence are proved separately, not by this mock.
  const notice = await request.post("http://127.0.0.1:8107/__seed", { data: {
    event_type: "event_change_rejected", recipient_id: "playwright-change-request-owner",
    payload: { event_request_id: event.id, change_request_id: saved[0].id, reason },
  } });
  expect(notice.status()).toBe(201);
  await page.context().addCookies(cookie("change-request-owner-session"));
  await page.goto("/notifications");
  const noticeCard = page.getByRole("article").filter({ hasText: reason });
  await expect(noticeCard).toBeVisible();
  await noticeCard.getByRole("link").click();
  await expect(page).toHaveURL(`/event-requests/${event.id}/edit`);
  const ownerHistory = page.getByRole("region", { name: "Change request history" });
  await expect(ownerHistory.getByText("Rejected", { exact: true })).toBeVisible();
  await expect(ownerHistory.getByText(reason, { exact: false })).toBeVisible();
  await expect(ownerHistory.getByText(/playwright-coordinator/)).toBeVisible();
  const decisionTime = new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Singapore",
  }).format(new Date(saved[0].decided_at));
  await expect(ownerHistory.locator(`time[datetime="${saved[0].decided_at}"]`)).toHaveText(decisionTime);
  await page.reload();
  await expect(ownerHistory.getByText("Rejected", { exact: true })).toBeVisible();
  await expect(ownerHistory.getByText(reason, { exact: false })).toBeVisible();
  await expect(page.getByText("40", { exact: true })).toBeVisible();

});

// AC2-N5 (negative): shared event access does not expose another organiser's change workflow
test("a colleague views the event without change controls or a misleading history error", async ({ page, request }) => {
  const seeded = await request.post(`${EVENT_API}/__seed`, {
    data: { status: "Approved", organiser_id: "playwright-user", coordinator_id: "playwright-coordinator", event_name: "SCRUM-35 Shared View" },
  });
  expect(seeded.status()).toBe(201);
  const event = await seeded.json();
  await page.context().addCookies(cookie("colleague-session"));
  await page.goto(`/event-requests/${event.id}/edit`);
  await expect(page.getByRole("heading", { name: event.event_name })).toBeVisible();
  await expect(page.getByText(/shared by another organiser/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "Request a change" })).toHaveCount(0);
  await expect(page.getByText("Change request history is temporarily unavailable.")).toHaveCount(0);
});

// AC3-X6 (cross-cutting): non-date approval updates the visible plan, preserves lifecycle and survives organiser history/inbox reload; API/Auth are canned.
test("organiser reads the applied non-date approval and its retained audit", async ({ page, request }) => {
  const seeded = await request.post(`${EVENT_API}/__seed`, { data: {
    status: "Planning", organiser_id: "playwright-change-request-owner", coordinator_id: "playwright-coordinator",
    event_name: "SCRUM-35 Non-date Approval", purpose: "Community engagement", description: "Keep the booked date and lifecycle.",
    proposed_date_times: ["2026-11-20T02:00:00Z"], expected_attendance: 25, venue_requirements: "Seminar room",
    equipment_requirements: "Microphone", registration_needs: "Online registration",
  } });
  expect(seeded.status()).toBe(201);
  const event = await seeded.json();
  await page.context().addCookies(cookie("change-request-owner-session"));
  await page.goto(`/event-requests/${event.id}/edit`);
  await page.getByRole("button", { name: "Request a change" }).click();
  const dialog = page.getByRole("dialog", { name: "Request a change" });
  await dialog.getByLabel("Reason for change").fill("Use the agreed larger non-date plan.");
  await dialog.getByLabel("Proposed attendance").fill("80");
  await dialog.getByLabel("Proposed venue requirements").fill("Auditorium");
  await dialog.getByLabel("Proposed equipment requirements").fill("Projector");
  await dialog.getByRole("button", { name: "Request change" }).click();
  await expect(page.getByRole("region", { name: "Change request history" }).getByText("Pending", { exact: true })).toBeVisible();
  const headers = { Authorization: "Bearer coordinator-session" };
  const beforeHistory = await request.get(`${EVENT_API}/event-requests/${event.id}/status-history`, { headers });
  expect(beforeHistory.status()).toBe(200);
  const lifecycle = await beforeHistory.json();
  expect(lifecycle.length).toBeGreaterThan(0);
  await page.context().addCookies(cookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);
  await page.getByRole("button", { name: "Approve change" }).click();
  const proposal = page.getByRole("article").filter({ hasText: "Use the agreed larger non-date plan." });
  await expect(proposal.getByText("Approved", { exact: true })).toBeVisible();
  await expect(proposal.getByRole("button", { name: "Approve change" })).toHaveCount(0);
  await page.reload();
  await expect(proposal.getByText("Approved", { exact: true })).toBeVisible();
  const changesResponse = await request.get(`${EVENT_API}/event-requests/${event.id}/change-requests`, { headers });
  expect(changesResponse.status()).toBe(200);
  const changes = await changesResponse.json();
  expect(changes).toHaveLength(1);
  const saved = changes[0];
  expect(saved).toMatchObject({ status: "Approved", coordinator_id: "playwright-coordinator", decision_reason: null });
  expect(Number.isNaN(Date.parse(saved.decided_at))).toBe(false);
  const currentResponse = await request.get(`${EVENT_API}/event-requests/${event.id}`, { headers });
  expect(currentResponse.status()).toBe(200);
  const current = await currentResponse.json();
  expect(current).toEqual({ ...event, expected_attendance: 80, venue_requirements: "Auditorium", equipment_requirements: "Projector", updated_at: current.updated_at });
  const afterHistory = await request.get(`${EVENT_API}/event-requests/${event.id}/status-history`, { headers });
  expect(await afterHistory.json()).toEqual(lifecycle);
  // Received inbox fixture; the actual producer HTTP202/postcommit boundary is tested independently.
  const notice = await request.post("http://127.0.0.1:8107/__seed", { data: {
    event_type: "event_change_approved", recipient_id: "playwright-change-request-owner",
    payload: { event_request_id: event.id, change_request_id: saved.id, reason: null },
  } });
  expect(notice.status()).toBe(201);
  await page.context().addCookies(cookie("change-request-owner-session"));
  await page.goto("/notifications");
  const noticeCard = page.getByRole("article").filter({ has: page.locator(`a[href="/event-requests/${event.id}/edit"]`) });
  await expect(noticeCard).toContainText(/change.*approved/i);
  await noticeCard.getByRole("link").click();
  await expect(page).toHaveURL(`/event-requests/${event.id}/edit`);
  const history = page.getByRole("region", { name: "Change request history" });
  await expect(history.getByText("Approved", { exact: true })).toBeVisible();
  await expect(history.getByText(/playwright-coordinator/)).toBeVisible();
  const decisionTime = new Intl.DateTimeFormat("en-SG", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Singapore" }).format(new Date(saved.decided_at));
  await expect(history.locator(`time[datetime="${saved.decided_at}"]`)).toHaveText(decisionTime);
  await page.reload();
  await expect(history.getByText("Approved", { exact: true })).toBeVisible();
  await expect(page.getByText("80", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Auditorium", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Projector", { exact: true }).first()).toBeVisible();
});

// AC3-X11 (cross-cutting): a coordinator can inspect the prepared date preview across reload without applying or approving its Pending proposal.
test("coordinator previews date-only booking ranges without changing the event", async ({ page, request }) => {
  const prepared = [{ booking_id: "35000000-0000-4000-8000-000000000001", venue_id: "35000000-0000-4000-8000-000000000101", status: "pending",
    current_start_date: "2026-11-19", current_end_date: "2026-11-20", proposed_start_date: "2026-11-21", proposed_end_date: "2026-11-22", start_minute: 600, end_minute: 720 }];
  const seeded = await request.post(`${EVENT_API}/__seed`, { data: {
    status: "Planning", organiser_id: "playwright-change-request-owner", coordinator_id: "playwright-coordinator",
    event_name: "SCRUM-35 Advisory Date Preview", proposed_date_times: ["2026-11-20T02:00:00Z"],
    expected_attendance: 25, venue_requirements: "Retain booked room", date_plan_bookings: prepared,
  } });
  expect(seeded.status()).toBe(201);
  const event = await seeded.json();
  const created = await request.post(`${EVENT_API}/event-requests/${event.id}/change-requests`, {
    headers: { Authorization: "Bearer change-request-owner-session" }, data: { explanation: "Move the dates only.", proposed_date_times: ["2026-11-22T02:00:00Z"] },
  });
  expect(created.status()).toBe(201);
  const pending = await created.json();
  const headers = { Authorization: "Bearer coordinator-session" };
  const lifecycleResponse = await request.get(`${EVENT_API}/event-requests/${event.id}/status-history`, { headers });
  expect(lifecycleResponse.status()).toBe(200);
  const lifecycle = await lifecycleResponse.json();
  expect(lifecycle.length).toBeGreaterThan(0);
  const reviewsResponse = await request.get(`${EVENT_API}/event-requests/${event.id}/arrangement-reviews`, { headers });
  expect(reviewsResponse.status()).toBe(200);
  const reviews = await reviewsResponse.json();
  await page.context().addCookies(cookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);
  await expect(page.getByRole("button", { name: "Approve change" })).toHaveCount(0);
  await expect(page.getByText(/Preview only.*No changes have been made.*complete booking plan/i)).toBeVisible();
  await page.getByRole("button", { name: "Preview date changes" }).click();
  const region = page.getByRole("region", { name: "Date change preview" });
  await expect(region).toContainText(prepared[0].booking_id);
  for (const day of ["19", "20", "21", "22"]) await expect(region).toContainText(new RegExp(`${day} Nov 2026|2026-11-${day}`));
  await expect(region).toContainText(/10:00/);
  await expect(region).toContainText(/12:00/);
  await page.reload();
  await expect(page.getByRole("button", { name: "Approve change" })).toHaveCount(0);
  await page.getByRole("button", { name: "Preview date changes" }).click();
  await expect(region).toContainText(prepared[0].booking_id);
  const current = await request.get(`${EVENT_API}/event-requests/${event.id}`, { headers });
  expect(current.status()).toBe(200);
  expect(await current.json()).toEqual(event);
  const changes = await request.get(`${EVENT_API}/event-requests/${event.id}/change-requests`, { headers });
  expect(changes.status()).toBe(200);
  expect(await changes.json()).toEqual([pending]);
  const historyAfter = await request.get(`${EVENT_API}/event-requests/${event.id}/status-history`, { headers });
  expect(await historyAfter.json()).toEqual(lifecycle);
  const reviewsAfter = await request.get(`${EVENT_API}/event-requests/${event.id}/arrangement-reviews`, { headers });
  expect(await reviewsAfter.json()).toEqual(reviews);
});


// AC3-X20, AC3-X18, AC3-X19 (cross-cutting): both real Next pages use retained registration evidence, and coordinator acknowledgement refreshes the organiser's read-only state; Auth/API are canned.
test("coordinator acknowledgement reaches organiser registration history without changing the event", async ({ page, request }) => {
  const older = {
    id: "35000000-0000-4000-8000-000000000311", event_updated_at: "2026-10-22T10:00:00Z",
    changed_fields: ["expected_attendance"], reason: "Registration review: attendance changed from 25 to 40.",
    raised_at: "2026-10-22T10:00:01Z", cleared_at: null, cleared_by: null,
  };
  const newer = { ...older, id: "35000000-0000-4000-8000-000000000312", event_updated_at: "2026-10-22T10:10:00Z",
    changed_fields: ["registration_needs"], reason: "Registration review: an accessible online form is required.", raised_at: "2026-10-22T10:10:01Z" };
  const acknowledged = { ...older, cleared_at: "2026-10-22T11:00:00Z", cleared_by: "playwright-coordinator" };
  const seeded = await request.post(`${EVENT_API}/__seed`, { data: {
    status: "Planning", organiser_id: "playwright-change-request-owner", coordinator_id: "playwright-coordinator",
    event_name: "SCRUM-35 Registration Review Wiring", purpose: "Prepared registration-review integration",
    description: "Evidence remains attached to its exact event and version.", expected_attendance: 40,
    proposed_date_times: ["2026-11-20T02:00:00Z"], venue_requirements: "Seminar room", equipment_requirements: "Microphone",
    registration_needs: "Accessible online form", registration_reviews: [newer, older], registration_acknowledgements: [acknowledged],
  } });
  expect(seeded.status()).toBe(201);
  const event = await seeded.json();
  const headers = { Authorization: "Bearer coordinator-session" };
  const beforeHistory = await request.get(`${EVENT_API}/event-requests/${event.id}/status-history`, { headers });
  expect(beforeHistory.status()).toBe(200);
  const history = await beforeHistory.json();

  await page.context().addCookies(cookie("change-request-owner-session"));
  await page.goto(`/event-requests/${event.id}/edit`);
  const ownerPanel = page.getByRole("region", { name: "Registration reviews" });
  await expect(ownerPanel.getByText(older.reason, { exact: true })).toBeVisible();
  await expect(ownerPanel.getByText(newer.reason, { exact: true })).toBeVisible();
  await expect(ownerPanel.getByRole("checkbox")).toHaveCount(0);

  await page.context().addCookies(cookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);
  const panel = page.getByRole("region", { name: "Registration reviews" });
  const target = panel.getByRole("article").filter({ hasText: older.reason });
  await target.getByRole("checkbox", { name: "I have checked the registration arrangements against this change" }).check();
  await target.getByRole("button", { name: "Acknowledge registration review" }).click();
  await expect(target.getByText("Acknowledged", { exact: true })).toBeVisible();
  const latest = panel.getByRole("article").filter({ hasText: newer.reason });
  await expect(latest.getByText("Outstanding", { exact: true })).toBeVisible();
  await page.reload();
  await expect(target.getByText("Acknowledged", { exact: true })).toBeVisible();

  await page.context().addCookies(cookie("change-request-owner-session"));
  await page.goto(`/event-requests/${event.id}/edit`);
  await page.reload();
  const retained = ownerPanel.getByRole("article").filter({ hasText: older.reason });
  await expect(retained.getByText("Acknowledged", { exact: true })).toBeVisible();
  await expect(retained).toContainText("playwright-coordinator");
  await expect(retained.locator(`time[datetime="${acknowledged.cleared_at}"]`)).toBeVisible();
  await expect(ownerPanel.getByRole("article").filter({ hasText: newer.reason }).getByText("Outstanding", { exact: true })).toBeVisible();
  await expect(ownerPanel.getByRole("button", { name: "Acknowledge registration review" })).toHaveCount(0);
  const after = await request.get(`${EVENT_API}/event-requests/${event.id}`, { headers });
  expect(await after.json()).toEqual(event);
  const afterHistory = await request.get(`${EVENT_API}/event-requests/${event.id}/status-history`, { headers });
  expect(await afterHistory.json()).toEqual(history);
});

// AC3-X32, AC1-X4 (cross-cutting): the organiser retains both requested dates and the coordinator's exact complete chosen ranges survive owner reload; real Next/Chromium use static Auth/API outcomes, not a date-writer substitute.
test("organiser and coordinator retain a complete explicit date approval across reload", async ({ page, request }) => {
  const originalDates = ["2026-11-20T02:00:00Z", "2026-11-21T07:00:00Z"];
  const proposedDates = ["2026-11-22T03:00:00.000Z", "2026-11-24T08:00:00.000Z"];
  const seeded = await request.post(`${EVENT_API}/__seed`, { data: {
    status: "Planning", organiser_id: "playwright-change-request-owner", coordinator_id: "playwright-coordinator",
    event_name: "SCRUM-35 Explicit Date Approval", purpose: "Two programme sessions", description: "Preserve the full applied booking decision.",
    proposed_date_times: originalDates, expected_attendance: 25, venue_requirements: "Seminar room", equipment_requirements: "Microphone", registration_needs: "Online form",
  } });
  expect(seeded.status()).toBe(201);
  const event = await seeded.json();
  await page.context().addCookies(cookie("change-request-owner-session"));
  await page.goto(`/event-requests/${event.id}/edit`);
  await page.getByRole("button", { name: "Request a change" }).click();
  const dialog = page.getByRole("dialog", { name: "Request a change" });
  await dialog.getByLabel("Reason for change").fill("Move both sessions with explicit venue ranges.");
  await dialog.getByRole("button", { name: "Add proposed date" }).click();
  const inputs = dialog.getByLabel(/Proposed date and time/i);
  await expect(inputs).toHaveCount(2);
  await inputs.nth(0).fill("2026-11-22T11:00");
  await inputs.nth(1).fill("2026-11-24T16:00");
  await dialog.getByLabel("Proposed attendance").fill("40");
  await dialog.getByRole("button", { name: "Request change" }).click();
  await expect(page.getByRole("region", { name: "Change request history" }).getByText("Pending", { exact: true })).toBeVisible();
  const headers = { Authorization: "Bearer coordinator-session" };
  const pendingResponse = await request.get(`${EVENT_API}/event-requests/${event.id}/change-requests`, { headers });
  expect(pendingResponse.status()).toBe(200);
  const [pending] = await pendingResponse.json();
  expect(pending.proposed_changes).toEqual({ proposed_date_times: proposedDates, expected_attendance: 40 });
  const before = await request.get(`${EVENT_API}/event-requests/${event.id}`, { headers });
  expect(await before.json()).toEqual(event);
  const beforeHistory = await request.get(`${EVENT_API}/event-requests/${event.id}/status-history`, { headers });
  const lifecycle = await beforeHistory.json();
  const bookings = [
    { booking_id: "35000000-0000-4000-8000-000000000821", venue_id: "35000000-0000-4000-8000-000000000921", start_date: "2026-11-20", end_date: "2026-11-20", start_minute: 600, end_minute: 720, status: "pending" },
    { booking_id: "35000000-0000-4000-8000-000000000822", venue_id: "35000000-0000-4000-8000-000000000922", start_date: "2026-11-21", end_date: "2026-11-21", start_minute: 900, end_minute: 1080, status: "approved" },
  ];
  const plan = [
    { booking_id: bookings[0].booking_id, start_date: "2026-11-22", end_date: "2026-11-22", start_minute: 660, end_minute: 750 },
    { booking_id: bookings[1].booking_id, start_date: "2026-11-24", end_date: "2026-11-24", start_minute: 960, end_minute: 1080 },
  ];
  const saved = { ...pending, status: "Approved", coordinator_id: "playwright-coordinator", decision_reason: "Checked all venue ranges", decided_at: "2026-10-22T12:30:00Z", applied_booking_plan: plan };
  const applied = { ...event, proposed_date_times: proposedDates, expected_attendance: 40, updated_at: "2026-10-22T12:30:00Z" };
  // Prepared responses only: native tests independently prove all-or-nothing application, conflicts, flags and registration reviews.
  const prepared = await request.post(`${EVENT_API}/__prepare_change_plan`, { data: {
    event_request_id: event.id, change_request_id: pending.id,
    context: { event_request_id: event.id, change_request_id: pending.id, event_updated_at: event.updated_at, bookings, automatic_plan: null, automatic_plan_error: "unsupported_date_mapping" },
    expected_booking_plan: plan, saved_change: saved, saved_event: applied,
  } });
  expect(prepared.status()).toBe(201);
  await page.context().addCookies(cookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);
  await page.getByRole("button", { name: "Review booking plan" }).click();
  const editor = page.getByRole("region", { name: "Booking plan" });
  for (const row of plan) {
    const group = editor.getByRole("group", { name: new RegExp(row.booking_id) });
    await group.getByLabel(/Start date/i).fill(row.start_date);
    await group.getByLabel(/End date/i).fill(row.end_date);
    await group.getByLabel(/Start time/i).selectOption(String(row.start_minute));
    await group.getByLabel(/End time/i).selectOption(String(row.end_minute));
  }
  await editor.getByLabel("Coordinator note (optional)").fill(saved.decision_reason);
  await editor.getByRole("button", { name: "Approve change" }).click();
  const coordinatorHistory = page.getByRole("article").filter({ hasText: pending.explanation });
  await expect(coordinatorHistory.getByText("Approved", { exact: true })).toBeVisible();
  await page.reload();
  for (const row of plan) await expect(coordinatorHistory).toContainText(row.booking_id);
  const after = await request.get(`${EVENT_API}/event-requests/${event.id}`, { headers });
  expect(await after.json()).toEqual(applied);
  const afterHistory = await request.get(`${EVENT_API}/event-requests/${event.id}/status-history`, { headers });
  expect(await afterHistory.json()).toEqual(lifecycle);
  const decisions = await request.get(`${EVENT_API}/event-requests/${event.id}/change-requests`, { headers });
  expect(await decisions.json()).toEqual([saved]);
  await page.context().addCookies(cookie("change-request-owner-session"));
  await page.goto(`/event-requests/${event.id}/edit`);
  await page.reload();
  const history = page.getByRole("region", { name: "Change request history" });
  await expect(history.getByText("Approved", { exact: true })).toBeVisible();
  await expect(history).toContainText(saved.coordinator_id);
  await expect(history.locator(`time[datetime="${saved.decided_at}"]`)).toBeVisible();
  for (const row of plan) await expect(history).toContainText(row.booking_id);
  await expect(history).toContainText(/22 Nov 2026|2026-11-22/);
  await expect(history).toContainText(/24 Nov 2026|2026-11-24/);
  await expect(history).toContainText("11:00");
  await expect(history).toContainText("12:30");
  await expect(history).toContainText("16:00");
  await expect(history).toContainText("18:00");
});
