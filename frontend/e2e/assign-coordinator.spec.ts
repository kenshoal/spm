import { expect, test } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";

function sessionCookie(value: string) {
  return [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];
}

test.describe.serial("SCRUM-14 coordinator assignment", () => {
  // Purpose: Covers AC1, AC2, AC3 and AC6 end to end — the manager finds an
  // unassigned submission, assigns it, the coordinator sees it, then the
  // manager reassigns it and the first coordinator loses it.
  test("manager assigns and reassigns a submitted request", async ({ page, request }) => {
    const seeded = await request.post(`${EVENT_API}/__seed`, {
      data: { event_name: "Harbour Lights Gala", organiser_id: "playwright-user", status: "Submitted", purpose: "Annual fundraiser" },
    });
    expect(seeded.ok()).toBeTruthy();

    await page.goto("/auth");
    await page.getByLabel("Email").fill("ops@example.com");
    await page.getByLabel("Password").fill("test-password-123");
    await page.getByRole("button", { name: "Log in", exact: true }).last().click();
    await expect(page).toHaveURL(/\/operations\/assignments$/);

    const awaitingCard = page.getByRole("article", { name: "Harbour Lights Gala" });
    await expect(awaitingCard).toBeVisible();
    await awaitingCard.getByRole("button", { name: "Assign" }).click();
    await expect(awaitingCard.getByRole("alert")).toHaveText("Choose a coordinator to assign.");

    await awaitingCard.getByLabel("Coordinator").selectOption({ label: "coordinator@example.com" });
    await awaitingCard.getByRole("button", { name: "Assign" }).click();

    const assignedCard = page.locator("section", { has: page.getByRole("heading", { name: /^Assigned/ }) })
      .getByRole("article", { name: "Harbour Lights Gala" });
    await expect(assignedCard).toContainText("coordinator@example.com");
    await expect(assignedCard).toContainText("Submitted");

    await page.context().clearCookies();
    await page.context().addCookies(sessionCookie("coordinator-session"));
    await page.goto("/coordination/requests");
    await expect(page.getByRole("heading", { name: "Harbour Lights Gala" })).toBeVisible();

    await page.context().clearCookies();
    await page.context().addCookies(sessionCookie("ops-session"));
    await page.goto("/operations/assignments");
    const card = page.locator("section", { has: page.getByRole("heading", { name: /^Assigned/ }) })
      .getByRole("article", { name: "Harbour Lights Gala" });
    const picker = card.getByLabel("Coordinator");
    await expect(picker.getByRole("option", { name: "coordinator@example.com", exact: true })).toHaveCount(0);
    await picker.selectOption({ label: "other.coordinator@example.com" });
    await card.getByRole("button", { name: "Reassign" }).click();
    await expect(card).toContainText("other.coordinator@example.com");

    await page.context().clearCookies();
    await page.context().addCookies(sessionCookie("coordinator-session"));
    await page.goto("/coordination/requests");
    await expect(page.getByRole("heading", { name: "Harbour Lights Gala" })).toHaveCount(0);
  });

  // Purpose: SCRUM-27 — the assignment workspace is closed to other roles.
  test("organisers cannot open the assignment workspace", async ({ page }) => {
    await page.context().addCookies(sessionCookie("test-session"));
    await page.goto("/operations/assignments");
    await expect(page).toHaveURL(/\/unauthorised$/);
  });
});
