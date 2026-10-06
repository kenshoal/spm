import { expect, test } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";
const cookie = (value: string) => [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];

// AC1-H1, AC1-X1, AC1-X2, AC2, AC3 (happy): organiser opens the change dialog from the list and both related roles see the applied change
test("organiser requests an approved event change and coordinator approves it", async ({ page, request }) => {
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
  await page.getByRole("button", { name: "Request a change" }).click();
  const changeDialog = page.getByRole("dialog", { name: "Request a change" });
  await expect(changeDialog).toBeVisible();
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
  await expect(page.getByText(/waiting for the assigned coordinator/i)).toBeVisible();

  await page.context().addCookies(cookie("coordinator-session"));
  await page.goto(`/coordination/requests/${event.id}`);
  await expect(page.getByText("Registrations exceeded the initial estimate.")).toBeVisible();
  await expect(page.getByText("80", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Approve change" }).click();
  const dialog = page.getByRole("dialog", { name: "Approve this change?" });
  await dialog.getByRole("button", { name: "Approve change" }).click();
  await expect(page.getByText("Approved", { exact: true }).last()).toBeVisible();

  await page.context().addCookies(cookie("test-session"));
  await page.goto(`/event-requests/${event.id}/edit`);
  await expect(page.getByText("80", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Change request history" })).toBeVisible();
});
