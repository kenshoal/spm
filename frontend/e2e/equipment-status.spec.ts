import { expect, test } from "@playwright/test";

// Purpose: SCRUM-16 AC1–AC3 — marking equipment damaged removes it from
// availability and records who changed it and why.
test("technical support mark equipment damaged and see the history", async ({ page }) => {
  await page.context().addCookies([{ name: "cs_access_token", value: "tech-session", url: "http://127.0.0.1:3100" }]);
  await page.goto("/equipment/new");
  await page.getByLabel("Equipment type").fill("Status Speaker");
  await page.getByLabel("Home location").fill("Store C");
  await page.getByLabel("Total owned quantity").fill("5");
  await page.getByRole("button", { name: "Add equipment" }).click();

  await expect(page.getByText("Available for events: 5 of 5.")).toBeVisible();
  await page.getByLabel("New status").selectOption("DAMAGED");
  await page.getByLabel("Reason (optional)").fill("Blown driver");
  await page.getByRole("button", { name: "Change status" }).click();

  await expect(page.getByText("Status changed to Damaged.")).toBeVisible();
  await expect(page.getByText("Not available — excluded from equipment availability until it is marked Available.")).toBeVisible();
  const latest = page.getByRole("region", { name: "Status history" }).getByRole("listitem").first();
  await expect(latest).toContainText("Available → Damaged");
  await expect(latest).toContainText("Blown driver");
  await expect(latest).toContainText("playwright-tech");
  await expect(page.getByLabel("New status").getByRole("option", { name: "Damaged" })).toHaveCount(0);
});
