import { expect, test } from "@playwright/test";

test("home page loads its primary content", async ({ page }) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: /to get started/i }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Documentation" })).toBeVisible();
});
