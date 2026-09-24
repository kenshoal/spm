import { expect, test } from "@playwright/test";

// Purpose: SCRUM-30 AC1–AC2 — venue staff add a venue, see its attributes, then update it.
test("venue staff add and update a venue", async ({ page }) => {
  await page.goto("/auth");
  await page.getByLabel("Email").fill("venue@example.com");
  await page.getByLabel("Password").fill("test-password-123");
  await page.getByRole("button", { name: "Log in", exact: true }).last().click();
  await expect(page).toHaveURL(/\/venues$/);

  await page.getByRole("link", { name: "+ Add venue" }).click();
  await page.getByLabel("Venue name").fill("Orchard Studio");
  await page.getByLabel("Location").fill("Level 3, North Wing");
  await page.getByLabel("Maximum capacity").fill("0");
  await page.getByRole("button", { name: "Add venue" }).click();
  await expect(page.getByText("Enter a whole number greater than zero.")).toBeVisible();

  await page.getByLabel("Maximum capacity").fill("45");
  await page.getByLabel("Facilities").fill("Projector, WiFi");
  await page.getByLabel("Accessibility features").fill("Ramp access");
  await page.getByRole("checkbox", { name: "Boardroom" }).check();
  await page.getByRole("button", { name: "Add venue" }).click();

  await expect(page).toHaveURL(/\/venues$/);
  const card = page.getByRole("article", { name: "Orchard Studio" });
  await expect(card).toContainText("up to 45 people");
  await expect(card).toContainText("Boardroom");

  await card.getByRole("link", { name: "Edit Orchard Studio" }).click();
  await page.getByLabel("Maximum capacity").fill("60");
  await page.getByLabel("Availability").selectOption("blocked");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page).toHaveURL(/\/venues$/);
  await expect(card).toContainText("up to 60 people");
  await expect(card).toContainText("Blocked");
});

// Purpose: SCRUM-27 — only Venue Staff can maintain the catalogue.
test("coordinators cannot open the venue catalogue", async ({ page }) => {
  await page.context().addCookies([{ name: "cs_access_token", value: "coordinator-session", url: "http://127.0.0.1:3100" }]);
  await page.goto("/venues/new");
  await expect(page).toHaveURL(/\/unauthorised$/);
});
