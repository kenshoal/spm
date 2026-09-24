import { expect, test } from "@playwright/test";

// Purpose: Proves unfinished work survives browser navigation and remains editable without being submitted.
test("organiser can save, reopen, update, and delete a draft", async ({ page }) => {
  await page.goto("/auth");
  await page.getByLabel("Email").fill("playwright@example.com");
  await page.getByLabel("Password").fill("test-password-123");
  await page.getByRole("button", { name: "Log in", exact: true }).last().click();
  await expect(page).toHaveURL(/\/event-requests$/);
  await page.goto("/event-requests/new");

  await expect(
    page.getByRole("heading", { name: "Create an event request" }),
  ).toBeVisible();
  await page.getByLabel("Event name").fill("Playwright community dinner");
  await page.getByLabel("Purpose").fill("Save this incomplete request");
  await expect(page.getByRole("button", { name: "Submit request" })).toBeVisible();

  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page).toHaveURL(/\/event-requests$/);
  await expect(
    page.getByRole("heading", { name: "Playwright community dinner" }),
  ).toBeVisible();

  await page.getByRole("link", { name: /continue draft/i }).click();
  await expect(page.getByLabel("Event name")).toHaveValue(
    "Playwright community dinner",
  );
  await expect(page.getByLabel("Purpose")).toHaveValue(
    "Save this incomplete request",
  );

  await page.getByLabel("Purpose").fill("Updated after reopening the draft");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page).toHaveURL(/\/event-requests$/);
  await expect(page.getByText("Updated after reopening the draft")).toBeVisible();

  await page.reload();
  await expect(page.getByText("Updated after reopening the draft")).toBeVisible();

  await page.getByRole("button", { name: "Delete draft" }).click();
  const dialog = page.getByRole("alertdialog", { name: "Delete event draft?" });
  await expect(dialog).toContainText("Playwright community dinner");
  await dialog.getByRole("button", { name: "Delete draft" }).click();
  await expect(
    page.getByRole("heading", { name: "Playwright community dinner" }),
  ).toHaveCount(0);
});

// Purpose: Proves a complete new form can be submitted directly and becomes visible but read-only.
test("organiser can submit a complete new event request", async ({ page }) => {
  await page.goto("/auth");
  await page.getByLabel("Email").fill("playwright@example.com");
  await page.getByLabel("Password").fill("test-password-123");
  await page.getByRole("button", { name: "Log in", exact: true }).last().click();
  await expect(page).toHaveURL(/\/event-requests$/);
  await page.goto("/event-requests/new");

  await page.getByLabel("Event name").fill("Submitted Community Workshop");
  await page.getByLabel("Purpose").fill("Teach practical skills");
  await page.getByLabel("Description").fill("A hands-on community programme");
  await page.getByLabel("Proposed date and time 1").fill("2026-10-20T10:00");
  await page.getByLabel("Expected attendance").fill("80");
  await page.getByLabel("Venue requirements").fill("Classroom");
  await page.getByLabel("Equipment requirements").fill("Projector");
  await page.getByLabel("Accessibility needs").fill("None");
  await page.getByLabel("Registration needs").fill("Online registration");
  await page.getByRole("button", { name: "Submit request" }).click();

  const dialog = page.getByRole("alertdialog", { name: "Submit event request?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Submit request" }).click();

  await expect(page).toHaveURL(/\/event-requests\?status=submitted$/);
  const submittedCard = page.getByRole("link", {
    name: /submitted community workshop/i,
  });
  await expect(submittedCard).toBeVisible();
  await expect(
    submittedCard.getByText("Submitted", { exact: true }),
  ).toBeVisible();
  // Scope to this request's card: specs share one mock API and run in
  // parallel, so other submitted requests can be listed alongside it.
  await page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: "Submitted Community Workshop" }) })
    .getByRole("link", { name: /view request/i })
    .click();
  await expect(page.getByText("This request is read-only after submission.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete draft" })).toHaveCount(0);
});
