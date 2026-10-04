import { expect, test } from "@playwright/test";

// Purpose: SCRUM-45 AC1–AC3 — technical support add equipment, see its
// attributes, and update the owned quantity.
test("technical support add equipment and update its quantity", async ({ page }) => {
  await page.goto("/auth");
  await page.getByLabel("Email").fill("tech@example.com");
  await page.getByLabel("Password").fill("test-password-123");
  await page.getByRole("button", { name: "Log in", exact: true }).last().click();
  await expect(page).toHaveURL(/\/equipment$/);

  await page.getByRole("link", { name: "+ Add equipment" }).click();
  await page.getByLabel("Equipment type").fill("Catalogue Projector");
  await page.getByLabel("Home location").fill("Store A");
  await page.getByLabel("Total owned quantity").fill("4");
  await page.getByLabel("Description").fill("4K laser projector");
  await page.getByRole("button", { name: "Add equipment" }).click();

  await expect(page.getByRole("heading", { name: "Catalogue Projector" })).toBeVisible();
  await expect(page.getByText("4K laser projector")).toBeVisible();

  await page.getByLabel("Total owned quantity").fill("-1");
  await page.getByRole("button", { name: "Update quantity" }).click();
  await expect(page.getByText("Enter a whole number of zero or more.")).toBeVisible();

  await page.getByLabel("Total owned quantity").fill("6");
  await page.getByRole("button", { name: "Update quantity" }).click();
  await expect(page.getByText("Quantity updated.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Total owned quantity")).toHaveValue("6");
});

// Purpose: SCRUM-27 — the equipment workspace is closed to other roles.
test("organisers cannot open the equipment workspace", async ({ page }) => {
  await page.context().addCookies([{ name: "cs_access_token", value: "test-session", url: "http://127.0.0.1:3100" }]);
  await page.goto("/equipment");
  await expect(page).toHaveURL(/\/unauthorised$/);
});
