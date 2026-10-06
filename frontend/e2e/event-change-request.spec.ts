import { expect, test } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";
const cookie = (value: string) => [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];

// AC1-H1, AC1-X1, AC1-X2, AC1-X3, AC2-X1, AC2-X2, AC2-N2, AC2-N4 (cross-cutting): both related actors see a Pending proposal while the original plan is retained
test("organiser creates a pending change and coordinator views it without deciding", async ({ page, request }) => {
  await page.setViewportSize({ width: 969, height: 930 });
  const seeded = await request.post(`${EVENT_API}/__seed`, {
    data: {
      status: "Approved",
      organiser_id: "playwright-user",
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

  await page.context().addCookies(cookie("test-session"));
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
    headers: { Authorization: "Bearer test-session" },
  });
  expect(beforeSubmission.status()).toBe(200);
  expect(await beforeSubmission.json()).toEqual([]);
  await page.getByRole("button", { name: "Request a change" }).click();
  await changeDialog.getByLabel("Reason for change").fill("Registrations exceeded the initial estimate.");
  await changeDialog.getByLabel("Proposed attendance").fill("80");
  await changeDialog.getByRole("button", { name: "Request change" }).click();
  await expect(page.getByText(/saved for the assigned coordinator to view/i)).toBeVisible();

  await page.context().addCookies(cookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);
  await expect(page.getByText("Registrations exceeded the initial estimate.")).toBeVisible();
  await expect(page.getByText("80", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve change" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reject change" })).toHaveCount(0);
  await expect(page.getByText(/approval and rejection are unavailable/i)).toBeVisible();
  await page.reload();
  await expect(page.getByText("Pending", { exact: true })).toBeVisible();
  const changes = await request.get(`${EVENT_API}/event-requests/${event.id}/change-requests`, {
    headers: { Authorization: "Bearer coordinator-session" },
  });
  expect(changes.status()).toBe(200);
  const saved = await changes.json();
  expect(saved).toHaveLength(1);
  for (const decision of ["Approved", "Rejected"]) {
    const denied = await request.post(`${EVENT_API}/event-requests/${event.id}/change-requests/${saved[0].id}/decision`, {
      headers: { Authorization: "Bearer coordinator-session" },
      data: { decision, reason: "Wait for arrangement assessment." },
    });
    expect(denied.status()).toBe(409);
    expect((await denied.json()).detail.code).toBe("CHANGE_DECISIONS_UNAVAILABLE");
  }
  const unchanged = await request.get(`${EVENT_API}/event-requests/${event.id}`, {
    headers: { Authorization: "Bearer coordinator-session" },
  });
  expect(unchanged.status()).toBe(200);
  expect(await unchanged.json()).toEqual(event);

  await page.context().addCookies(cookie("test-session"));
  await page.goto(`/event-requests/${event.id}/edit`);
  await expect(page.getByText("40", { exact: true })).toBeVisible();
  await expect(page.getByText("Pending", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Change request history" })).toBeVisible();
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
