import { expect, test } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";
const cookie = (value: string) => [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];

// AC1-H1, AC2, AC3 (happy): an organiser amendment is reviewed, applied and visible to both related roles
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
  await page.goto(`/event-requests/${event.id}/edit`);
  await page.getByLabel("Reason for change").fill("Registrations exceeded the initial estimate.");
  await page.getByLabel("Proposed attendance").fill("80");
  await page.getByRole("button", { name: "Request change" }).click();
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
