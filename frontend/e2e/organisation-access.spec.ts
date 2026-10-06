import { expect, test } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";

// AC2-X2 (cross-cutting): a same-organisation colleague sees a shared request read-only
test("colleague in the same organisation views a shared request without editing it", async ({
  page,
  request,
}) => {
  const seeded = await request.post(`${EVENT_API}/__seed`, {
    data: {
      status: "Changes Requested",
      organiser_id: "playwright-user",
      coordinator_id: "playwright-coordinator",
      event_name: "SCRUM-39 Shared Acme Forum",
      review_decision: {
        decision_status: "Changes Requested",
        reason: "Confirm the expected attendance",
      },
    },
  });
  expect(seeded.status()).toBe(201);
  const event = await seeded.json();

  await page.context().addCookies([
    { name: "cs_access_token", value: "colleague-session", url: "http://127.0.0.1:3100" },
  ]);
  await page.goto("/event-requests");
  await page.getByRole("link", { name: /^All \(/ }).click();
  await expect(page.getByText("SCRUM-39 Shared Acme Forum")).toBeVisible();

  await page.goto(`/event-requests/${event.id}/edit`);
  await expect(page.getByText("SCRUM-39 Shared Acme Forum")).toBeVisible();
  await expect(page.getByText("Confirm the expected attendance")).toBeVisible();
  await expect(page.getByText(/shared by another organiser in your organisation/i)).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /send|respond|save|submit|delete/i })).toHaveCount(0);
});
