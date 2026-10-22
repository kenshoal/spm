import { expect, test } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";
const NOTIFICATION_API = "http://127.0.0.1:8107";

function sessionCookie(value: string) {
  return [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];
}

test.describe.serial("SCRUM-19 assign technical support", () => {
  // AC5-H3a (happy): the coordinator records an audio-visual requirement on a
  // seeded Planning event, assigns technical_support@example.com and sees the
  // assignment listed; the staff member's inbox shows the notice naming the
  // skill and the event, and keeps it across a reload. The mock event-request
  // API does not call notificationService, so the notice the real service
  // would write is seeded directly — the emission itself is proven by the
  // AC5-H1 API tests, not here.
  test("coordinator assigns support and the staff member is notified", async ({ page, request }) => {
    const seeded = await request.post(`${EVENT_API}/__seed`, {
      data: {
        event_name: "Tech Summit 2030",
        organiser_id: "playwright-user",
        status: "Planning",
        coordinator_id: "playwright-coordinator",
      },
    });
    expect(seeded.ok()).toBeTruthy();
    const event = await seeded.json();

    await page.goto("/auth");
    await page.getByLabel("Email").fill("coordinator@example.com");
    await page.getByLabel("Password").fill("test-password-123");
    await page.getByRole("button", { name: "Log in", exact: true }).last().click();
    await expect(page).toHaveURL(/\/coordination\/requests$/);

    await page.goto(`/coordination/requests/${event.id}`);
    const panel = page.getByRole("region", { name: "Technical support" });
    await expect(panel).toBeVisible();

    await panel
      .getByLabel("What support is needed?")
      .fill("Two wireless mics and a mixing-desk operator for the keynote");
    await panel.getByLabel("Skill").selectOption({ label: "Audio-visual" });
    await panel.getByRole("button", { name: "Record requirement" }).click();

    const requirement = panel.getByRole("article");
    await expect(requirement.getByRole("heading", { name: "Audio-visual support" })).toBeVisible();
    await expect(
      requirement.getByText("Two wireless mics and a mixing-desk operator for the keynote"),
    ).toBeVisible();
    await expect(requirement.getByText("Nobody assigned yet")).toBeVisible();

    const select = requirement.getByRole("combobox", { name: "Technical Support Staff" });
    await select.selectOption({ label: "technical_support@example.com" });
    await requirement.getByRole("button", { name: "Assign" }).click();

    await expect(
      requirement.getByText("technical_support@example.com").first(),
    ).toBeVisible();
    await expect(requirement.getByText("Nobody assigned yet")).toHaveCount(0);
    // The only suitable person is now on the requirement, so the select goes.
    await expect(
      requirement.getByText("Everyone suitable is already assigned."),
    ).toBeVisible();
    await expect(
      requirement.getByRole("combobox", { name: "Technical Support Staff" }),
    ).toHaveCount(0);

    // The notice notificationService would have written for the assignment.
    const seededNotice = await request.post(`${NOTIFICATION_API}/__seed`, {
      data: {
        event_type: "technical_support_assigned",
        recipient_id: "playwright-tech",
        payload: {
          event_request_id: event.id,
          event_name: "Tech Summit 2030",
          requirement_id: "aaaa0000-0000-4000-8000-000000000001",
          skill_tag: "audio_visual",
          assigned_by: "playwright-coordinator",
        },
      },
    });
    expect(seededNotice.ok()).toBeTruthy();

    await page.context().clearCookies();
    await page.context().addCookies(sessionCookie("tech-session"));
    await page.goto("/notifications");
    const notice = page.getByRole("heading", {
      name: "You've been assigned as Audio-visual support for Tech Summit 2030.",
    });
    await expect(notice).toBeVisible();

    await page.reload();
    await expect(
      page.getByRole("heading", {
        name: "You've been assigned as Audio-visual support for Tech Summit 2030.",
      }),
    ).toBeVisible();
  });
});
