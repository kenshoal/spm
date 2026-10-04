import { expect, test } from "@playwright/test";

const NOTIFICATION_API = "http://127.0.0.1:8107";

function sessionCookie(value: string) {
  return [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];
}

test.describe.serial("SCRUM-37 notifications inbox", () => {
  // AC1-H1, AC6-H2 (happy): AC1 end to end — the Organiser reaches the inbox from the navigation,
  // sees their submission confirmation linked to the request, and marks it read.
  // Another user's notification never appears (relevance rule, C-1b).
  test("organiser reads a submission confirmation and marks it read", async ({ page, request }) => {
    const seeds = [
      {
        recipient_id: "playwright-user",
        event_type: "event_request_submitted",
        payload: { event_request_id: "e2e-request-1", organiser_id: "playwright-user", status: "Submitted" },
      },
      {
        recipient_id: "playwright-coordinator",
        event_type: "coordinator_assigned",
        payload: { event_request_id: "e2e-request-1", coordinator_id: "playwright-coordinator", assigned_by: "playwright-ops" },
      },
    ];
    for (const data of seeds) {
      expect((await request.post(`${NOTIFICATION_API}/__seed`, { data })).ok()).toBeTruthy();
    }

    await page.context().addCookies(sessionCookie("test-session"));
    await page.goto("/event-requests");
    await page.getByRole("navigation", { name: "Workspaces" }).getByRole("link", { name: "Notifications" }).click();
    await expect(page).toHaveURL(/\/notifications$/);
    await expect(page.getByText("1 unread")).toBeVisible();

    const card = page.getByRole("article", { name: "Your event request was submitted." });
    await expect(card.getByText("Unread")).toBeVisible();
    await expect(card.getByRole("link", { name: "View request" })).toHaveAttribute("href", "/event-requests/e2e-request-1/edit");
    await expect(page.getByRole("article", { name: "You've been assigned an event request." })).toHaveCount(0);

    await card.getByRole("button", { name: "Mark as read" }).click();
    await expect(page.getByText("You're all caught up.")).toBeVisible();
    await expect(card.getByRole("button", { name: "Mark as read" })).toHaveCount(0);
    await expect(card.getByText("Unread")).toHaveCount(0);
  });

  // AC2-H1 (happy): AC2 — the assigned Coordinator sees their notification, linked to the coordination view.
  test("coordinator sees their assignment notification", async ({ page }) => {
    await page.context().addCookies(sessionCookie("coordinator-session"));
    await page.goto("/notifications");

    const card = page.getByRole("article", { name: "You've been assigned an event request." });
    await expect(card.getByRole("link", { name: "View request" })).toHaveAttribute("href", "/coordination/requests/e2e-request-1");
  });
});
