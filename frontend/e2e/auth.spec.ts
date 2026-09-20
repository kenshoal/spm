import { expect, test } from "@playwright/test";

test("protected pages require a valid session", async ({ page }) => {
  await page.goto("/event-requests");
  await expect(page).toHaveURL(/\/auth$/);

  await page.context().addCookies([{
    name: "cs_access_token",
    value: "expired",
    url: "http://127.0.0.1:3100",
  }]);
  await page.goto("/event-requests");
  await expect(page).toHaveURL(/\/auth$/);

  await page.getByLabel("Email").fill("playwright@example.com");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Log in", exact: true }).last().click();
  await expect(page.getByText("Invalid credentials or email confirmation is required.")).toBeVisible();
  await expect(page).toHaveURL(/\/auth$/);

  await page.getByLabel("Email").fill("playwright@example.com");
  await page.getByLabel("Password").fill("test-password-123");
  await page.getByRole("button", { name: "Log in", exact: true }).last().click();
  await expect(page).toHaveURL(/\/event-requests$/);
  await expect(page.getByRole("heading", { name: "Your event requests" })).toBeVisible();

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/auth$/);
  await page.goto("/event-requests");
  await expect(page).toHaveURL(/\/auth$/);
});

test("event-request pages require the Event Organiser role", async ({ page }) => {
  await page.context().addCookies([{
    name: "cs_access_token",
    value: "non-organiser-session",
    url: "http://127.0.0.1:3100",
  }]);

  await page.goto("/event-requests");

  await expect(page).toHaveURL(/\/unauthorised$/);
  await expect(page.getByRole("heading", { name: "Event Organiser access required" })).toBeVisible();
});
