import { expect, test } from "@playwright/test";

// Purpose: Proves unfinished work survives browser navigation and remains editable without being submitted.
test("organiser can save, reopen, update, and delete a draft", async ({ page }) => {
  await page.goto("/event-requests/new");

  await expect(
    page.getByRole("heading", { name: "Create an event request" }),
  ).toBeVisible();
  await page.getByLabel("Event name").fill("Playwright community dinner");
  await page.getByLabel("Purpose").fill("Save this incomplete request");
  await expect(page.getByRole("button", { name: /submit for review/i })).toHaveCount(0);

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
